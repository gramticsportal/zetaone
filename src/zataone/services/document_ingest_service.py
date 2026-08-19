# zataone document ingestion — file → per-page text assets

"""
Convert uploaded document files (.txt/.pdf/.docx) into per-page text pages
for the existing text pipeline. Ingestion-layer only: no signals, no verdicts.

Granularity contract: page = unit of judgment (one pipeline run per page),
sentence = unit of evidence (DSL match spans and semantic-extractor sentence
scores already carry character offsets within the page).

File kind is sniffed from magic bytes, never trusted from the filename.
PDF/DOCX parsing degrades gracefully: a clear error names the missing library.
"""

from __future__ import annotations

import io
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# Absolute ceiling on pages per document; sync pipeline runs must stay bounded.
MAX_PAGES = 50

# Conservative default while document support is new; raise via env when ready.
DEFAULT_MAX_PAGES = 2


def max_pages() -> int:
    """Effective page cap: ZATAONE_DOC_MAX_PAGES env (default 2), clamped to [1, MAX_PAGES]."""
    raw = (os.environ.get("ZATAONE_DOC_MAX_PAGES") or "").strip()
    try:
        value = int(raw) if raw else DEFAULT_MAX_PAGES
    except ValueError:
        value = DEFAULT_MAX_PAGES
    return max(1, min(value, MAX_PAGES))

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"

# Severity ordering for the document-level rollup (worst page wins)
_STATUS_RANK = {
    "COMPLIANT": 0,
    "PENDING_ADVISORY": 1,
    "REVIEW_REQUIRED": 2,
    "NON_COMPLIANT": 3,
    "REJECTED": 3,
}


class UnsupportedDocumentError(ValueError):
    """Uploaded bytes are not a supported document type."""


class DocumentParserUnavailableError(RuntimeError):
    """The library needed to parse this document type is not installed."""


def sniff_document_kind(data: bytes, filename: str | None = None) -> str:
    """
    Detect document kind from magic bytes: "pdf", "docx", or "txt".

    The filename is only a tiebreaker for zip containers (docx vs other
    office formats); content decides everything else.
    """
    if not data:
        raise UnsupportedDocumentError("Empty file")

    if data[:5] == _PDF_MAGIC:
        return "pdf"

    if data[:4] == _ZIP_MAGIC:
        # docx is a zip; confirm by looking for the word/ package structure
        if b"word/" in data[:4096] or b"[Content_Types].xml" in data[:4096]:
            return "docx"
        if filename and filename.lower().endswith(".docx"):
            return "docx"
        raise UnsupportedDocumentError(
            "Zip container is not a .docx document (xlsx/pptx/zip not supported)"
        )

    try:
        data.decode("utf-8")
        return "txt"
    except UnicodeDecodeError:
        pass
    try:
        data.decode("latin-1")
        return "txt"
    except UnicodeDecodeError as exc:
        raise UnsupportedDocumentError(
            "Unsupported file type; expected .txt, .pdf, or .docx"
        ) from exc


def extract_pages(data: bytes, kind: str, max_pages_limit: int | None = None) -> list[str]:
    """
    Extract text per page. Returns a non-empty list of page strings
    (pages with no extractable text become empty strings, preserving
    page numbering). Documents over the page cap are rejected.
    """
    if kind == "txt":
        pages = _extract_txt_pages(data)
    elif kind == "pdf":
        pages = _extract_pdf_pages(data)
    elif kind == "docx":
        pages = _extract_docx_pages(data)
    else:
        raise UnsupportedDocumentError(f"Unknown document kind: {kind}")

    limit = max_pages_limit if max_pages_limit is not None else max_pages()
    if len(pages) > limit:
        raise UnsupportedDocumentError(
            f"Document has {len(pages)} pages; maximum is {limit} "
            "(raise via ZATAONE_DOC_MAX_PAGES)"
        )
    return pages or [""]


def _extract_txt_pages(data: bytes) -> list[str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    # Form feed is the plain-text page separator; without one it is one page.
    if "\f" in text:
        return [p.strip() for p in text.split("\f")]
    return [text.strip()]


def _extract_pdf_pages(data: bytes) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentParserUnavailableError(
            "PDF support requires pypdf. Fix: pip install pypdf"
        ) from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        return [(page.extract_text() or "").strip() for page in reader.pages]
    except DocumentParserUnavailableError:
        raise
    except Exception as exc:
        raise UnsupportedDocumentError(f"Could not parse PDF: {exc}") from exc


def _extract_docx_pages(data: bytes) -> list[str]:
    try:
        import docx  # python-docx
    except ImportError as exc:
        raise DocumentParserUnavailableError(
            "DOCX support requires python-docx. Fix: pip install python-docx"
        ) from exc
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise UnsupportedDocumentError(f"Could not parse DOCX: {exc}") from exc

    # DOCX has no fixed pages until rendered; split on explicit page breaks,
    # else the whole document is one page.
    pages: list[str] = []
    current: list[str] = []
    for para in document.paragraphs:
        if _para_has_page_break(para) and current:
            pages.append("\n".join(current).strip())
            current = []
        if para.text:
            current.append(para.text)
    pages.append("\n".join(current).strip())
    return pages


def _para_has_page_break(para: Any) -> bool:
    xml = getattr(getattr(para, "_p", None), "xml", "") or ""
    return 'w:br w:type="page"' in xml or "lastRenderedPageBreak" in xml


_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]?")


def aggregate_page_verdicts(page_results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Roll per-page verdicts up to one document verdict: worst page status,
    max risk score. page_results items need "status" and "risk_score".
    """
    worst_status = "COMPLIANT"
    worst_rank = -1
    max_risk = 0.0
    flagged_pages: list[int] = []
    for result in page_results:
        status = str(result.get("status") or "COMPLIANT")
        rank = _STATUS_RANK.get(status, 1)
        if rank > worst_rank:
            worst_rank = rank
            worst_status = status
        risk = float(result.get("risk_score") or 0.0)
        max_risk = max(max_risk, risk)
        if rank >= _STATUS_RANK["REVIEW_REQUIRED"]:
            flagged_pages.append(int(result.get("page_number") or 0))

    return {
        "status": worst_status,
        "risk_score": round(max_risk, 4),
        "page_count": len(page_results),
        "flagged_pages": flagged_pages,
    }
