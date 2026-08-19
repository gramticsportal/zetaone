"""
Unit tests for document_ingest_service: magic-byte sniffing, per-page text
extraction, and the document-level verdict rollup.
"""

import sys
from pathlib import Path

# Ensure src is first for correct zataone import
src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

import pytest

from zataone.services.document_ingest_service import (
    DEFAULT_MAX_PAGES,
    MAX_PAGES,
    UnsupportedDocumentError,
    aggregate_page_verdicts,
    extract_pages,
    max_pages,
    sniff_document_kind,
)


# ── Sniffing ──────────────────────────────────────────────────────────────────


def test_sniff_pdf_magic_bytes():
    assert sniff_document_kind(b"%PDF-1.7 rest of file") == "pdf"


def test_sniff_docx_zip_with_word_marker():
    data = b"PK\x03\x04" + b"filler [Content_Types].xml word/document.xml"
    assert sniff_document_kind(data) == "docx"


def test_sniff_plain_text():
    assert sniff_document_kind("Guaranteed results!".encode("utf-8")) == "txt"


def test_sniff_rejects_plain_zip():
    with pytest.raises(UnsupportedDocumentError):
        sniff_document_kind(b"PK\x03\x04" + b"\x00" * 100, filename="archive.zip")


def test_sniff_rejects_empty():
    with pytest.raises(UnsupportedDocumentError):
        sniff_document_kind(b"")


def test_sniff_ignores_lying_filename():
    # Content decides: a text file named .pdf is still text
    assert sniff_document_kind(b"just words", filename="fake.pdf") == "txt"


# ── TXT page extraction ───────────────────────────────────────────────────────


def test_txt_single_page_without_form_feed():
    pages = extract_pages(b"One page of ad copy.", "txt")
    assert pages == ["One page of ad copy."]


def test_txt_form_feed_splits_pages():
    pages = extract_pages(
        b"Page one text.\fPage two text.\fPage three.", "txt", max_pages_limit=10
    )
    assert len(pages) == 3
    assert pages[1] == "Page two text."


def test_default_page_cap_is_two():
    assert DEFAULT_MAX_PAGES == 2
    data = b"Page one.\fPage two.\fPage three."
    with pytest.raises(UnsupportedDocumentError):
        extract_pages(data, "txt")  # 3 pages > default cap of 2


def test_page_cap_env_override(monkeypatch):
    monkeypatch.setenv("ZATAONE_DOC_MAX_PAGES", "5")
    assert max_pages() == 5
    pages = extract_pages(b"P1.\fP2.\fP3.", "txt")
    assert len(pages) == 3


def test_page_cap_clamped_to_absolute_max(monkeypatch):
    monkeypatch.setenv("ZATAONE_DOC_MAX_PAGES", "9999")
    assert max_pages() == MAX_PAGES
    monkeypatch.setenv("ZATAONE_DOC_MAX_PAGES", "0")
    assert max_pages() == 1
    monkeypatch.setenv("ZATAONE_DOC_MAX_PAGES", "junk")
    assert max_pages() == DEFAULT_MAX_PAGES


def test_explicit_limit_overrides_env(monkeypatch):
    monkeypatch.setenv("ZATAONE_DOC_MAX_PAGES", "1")
    pages = extract_pages(b"P1.\fP2.", "txt", max_pages_limit=10)
    assert len(pages) == 2


def test_empty_pages_preserve_numbering():
    pages = extract_pages(b"Page one.\f\fPage three.", "txt", max_pages_limit=10)
    assert len(pages) == 3
    assert pages[1] == ""


# ── Rollup ────────────────────────────────────────────────────────────────────


def test_rollup_worst_page_wins():
    rollup = aggregate_page_verdicts(
        [
            {"page_number": 1, "status": "COMPLIANT", "risk_score": 0.0},
            {"page_number": 2, "status": "NON_COMPLIANT", "risk_score": 0.9},
            {"page_number": 3, "status": "REVIEW_REQUIRED", "risk_score": 0.4},
        ]
    )
    assert rollup["status"] == "NON_COMPLIANT"
    assert rollup["risk_score"] == 0.9
    assert rollup["page_count"] == 3
    assert rollup["flagged_pages"] == [2, 3]


def test_rollup_all_compliant():
    rollup = aggregate_page_verdicts(
        [
            {"page_number": 1, "status": "COMPLIANT", "risk_score": 0.0},
            {"page_number": 2, "status": "COMPLIANT", "risk_score": 0.0},
        ]
    )
    assert rollup["status"] == "COMPLIANT"
    assert rollup["flagged_pages"] == []


# ── PDF/DOCX (skipped when parser libs absent) ───────────────────────────────


def test_pdf_extraction_real_lib():
    import io

    try:
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.add_blank_page(width=200, height=200)
        buf = io.BytesIO()
        writer.write(buf)
    except (ImportError, AttributeError) as exc:
        pytest.skip(f"pypdf environment incompatible: {exc}")
    pages = extract_pages(buf.getvalue(), "pdf")
    assert len(pages) == 2  # blank pages extract as empty strings


def test_docx_extraction_real_lib():
    docx = pytest.importorskip("docx")
    import io

    document = docx.Document()
    document.add_paragraph("Guaranteed results on page one!")
    document.add_page_break()
    document.add_paragraph("Page two is clean.")
    buf = io.BytesIO()
    document.save(buf)
    pages = extract_pages(buf.getvalue(), "docx")
    assert len(pages) == 2
    assert "Guaranteed" in pages[0]
    assert "clean" in pages[1]
