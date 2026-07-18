# zataone document builder

"""
Build a unified DocumentSignal from raw extractor signals and asset fields.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from zataone.schemas.document import DocumentModality, DocumentSignal, DocumentSpan, TimelineEntry

_LINE_Y_TOLERANCE_PX = 12


def normalize_document_text(text: str) -> str:
    """NFC unicode normalization, whitespace cleanup (deterministic)."""
    if not text:
        return ""
    t = unicodedata.normalize("NFC", text)
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _signal_id(signal: Any) -> str:
    sid = getattr(signal, "signal_id", None)
    return str(sid) if sid is not None else ""


def _raw_data(signal: Any) -> dict[str, Any]:
    rd = getattr(signal, "raw_data", None)
    if rd is None:
        val = getattr(signal, "value", None)
        if isinstance(val, dict):
            return val
        return {}
    return dict(rd) if hasattr(rd, "copy") else (rd if isinstance(rd, dict) else {})


def _is_ocr_signal(rd: dict[str, Any], signal: Any) -> bool:
    if rd.get("type") == "ocr_text":
        return True
    st = getattr(signal, "signal_type", None)
    if st is not None:
        val = getattr(st, "value", str(st))
        if str(val).lower() in ("text", "ocr_keyword", "ocr_percentage_claim", "ocr_time_claim"):
            text = rd.get("text") or rd.get("value")
            if text and (rd.get("source") == "image" or rd.get("bbox") is not None):
                return True
    return False


def _is_asr_signal(rd: dict[str, Any]) -> bool:
    return rd.get("type") == "asr_text"


def _is_vision_object(rd: dict[str, Any]) -> bool:
    return rd.get("type") == "vision_object"


def _is_vlm_claims(rd: dict[str, Any]) -> bool:
    return rd.get("type") == "vlm_claims_text"


def _is_timeline_signal(rd: dict[str, Any]) -> bool:
    return rd.get("type") in ("timeline_text", "video_timeline")


def _bbox_top_left(signal: Any, rd: dict[str, Any]) -> tuple[float, float]:
    bb = getattr(signal, "bounding_box", None) or rd.get("bbox")
    if isinstance(bb, dict):
        return float(bb.get("y", bb.get("top", 0))), float(bb.get("x", bb.get("left", 0)))
    if isinstance(bb, (list, tuple)) and len(bb) >= 2:
        return float(bb[1]), float(bb[0])
    return 0.0, 0.0


def _aggregate_ocr_signals(
    ocr_signals: list[tuple[Any, dict[str, Any]]],
) -> tuple[str, list[DocumentSpan]]:
    """Sort OCR tokens into lines (reading order) and join with character spans."""
    if not ocr_signals:
        return "", []

    entries: list[dict[str, Any]] = []
    for signal, rd in ocr_signals:
        text = (rd.get("text") or rd.get("value") or "").strip()
        if not text:
            continue
        top, left = _bbox_top_left(signal, rd)
        entries.append(
            {"signal": signal, "rd": rd, "text": text, "top": top, "left": left}
        )

    if not entries:
        return "", []

    entries.sort(key=lambda e: (e["top"], e["left"]))

    lines: list[list[dict[str, Any]]] = []
    for entry in entries:
        placed = False
        for line in lines:
            if abs(entry["top"] - line[0]["top"]) <= _LINE_Y_TOLERANCE_PX:
                line.append(entry)
                placed = True
                break
        if not placed:
            lines.append([entry])

    for line in lines:
        line.sort(key=lambda e: e["left"])

    parts: list[str] = []
    spans: list[DocumentSpan] = []
    offset = 0

    for line_idx, line in enumerate(lines):
        if line_idx > 0:
            parts.append("\n")
            offset += 1
        for word_idx, entry in enumerate(line):
            if word_idx > 0:
                parts.append(" ")
                offset += 1
            word = entry["text"]
            start = offset
            parts.append(word)
            offset += len(word)
            bb = entry["rd"].get("bbox")
            if bb is None:
                bb = getattr(entry["signal"], "bounding_box", None)
            spans.append(
                DocumentSpan(
                    start=start,
                    end=offset,
                    text=word,
                    source_signal_id=_signal_id(entry["signal"]),
                    source_type="ocr",
                    bbox=bb,
                )
            )

    return "".join(parts), spans


def _build_scene_descriptions(
    vision_signals: list[tuple[Any, dict[str, Any]]],
) -> list[str]:
    if not vision_signals:
        return []
    parts: list[str] = []
    for signal, rd in vision_signals:
        label = str(rd.get("label", "")).strip()
        if not label:
            continue
        conf = rd.get("confidence", getattr(signal, "confidence", None))
        if conf is not None:
            parts.append(f"{label} ({float(conf):.2f})")
        else:
            parts.append(label)
    if not parts:
        return []
    return [f"Image contains: {', '.join(parts)}."]


def _build_timeline(
    timeline_signals: list[tuple[Any, dict[str, Any]]],
) -> list[TimelineEntry]:
    entries: list[TimelineEntry] = []
    for signal, rd in timeline_signals:
        ts = float(rd.get("timestamp_sec", rd.get("time_sec", 0.0)))
        text = str(rd.get("text", "")).strip()
        if not text:
            continue
        sid = _signal_id(signal)
        entries.append(
            TimelineEntry(
                timestamp_sec=ts,
                text=text,
                source_signal_ids=[sid] if sid else [],
            )
        )
    entries.sort(key=lambda e: e.timestamp_sec)
    return entries


def _format_timeline_text(timeline: list[TimelineEntry]) -> str:
    lines: list[str] = []
    for entry in timeline:
        mm = int(entry.timestamp_sec // 60)
        ss = int(entry.timestamp_sec % 60)
        lines.append(f"[{mm:02d}:{ss:02d}] {entry.text}")
    return "\n".join(lines)


class DocumentBuilder:
    """Construct DocumentSignal from an asset and extractor signals."""

    @classmethod
    def build(cls, asset: Any, signals: list[Any]) -> DocumentSignal:
        modality = cls._asset_modality(asset)
        asset_id = cls._asset_id(asset)

        ocr_pairs: list[tuple[Any, dict[str, Any]]] = []
        claims_texts: list[tuple[str, str]] = []
        asr_texts: list[tuple[str, str]] = []
        vision_pairs: list[tuple[Any, dict[str, Any]]] = []
        timeline_pairs: list[tuple[Any, dict[str, Any]]] = []
        source_ids: list[str] = []

        for signal in signals:
            rd = _raw_data(signal)
            sid = _signal_id(signal)
            if sid:
                source_ids.append(sid)
            if _is_vlm_claims(rd):
                text = (rd.get("text") or "").strip()
                if text:
                    claims_texts.append((text, sid))
            elif _is_ocr_signal(rd, signal):
                ocr_pairs.append((signal, rd))
            elif _is_asr_signal(rd):
                text = (rd.get("text") or "").strip()
                if text:
                    asr_texts.append((text, sid))
            elif _is_vision_object(rd):
                vision_pairs.append((signal, rd))
            elif _is_timeline_signal(rd):
                timeline_pairs.append((signal, rd))

        body_parts: list[str] = []
        spans: list[DocumentSpan] = []
        offset = 0

        def _append_section(text: str, section_spans: list[DocumentSpan]) -> None:
            nonlocal offset
            if not text:
                return
            if body_parts:
                body_parts.append("\n\n")
                offset += 2
            body_parts.append(text)
            for sp in section_spans:
                spans.append(
                    DocumentSpan(
                        start=offset + sp.start,
                        end=offset + sp.end,
                        text=sp.text,
                        source_signal_id=sp.source_signal_id,
                        source_type=sp.source_type,
                        bbox=sp.bbox,
                    )
                )
            offset += len(text)

        if modality == "text":
            content = normalize_document_text(cls._asset_text_content(asset))
            if content:
                text_span = [
                    DocumentSpan(
                        start=0,
                        end=len(content),
                        text=content,
                        source_signal_id=source_ids[0] if source_ids else "",
                        source_type="text",
                        bbox=None,
                    )
                ]
                _append_section(content, text_span)

        ocr_text, ocr_spans = _aggregate_ocr_signals(ocr_pairs)
        if ocr_text:
            _append_section(ocr_text, ocr_spans)

        # High-signal ad claims from Gemini VLM — preferred for lexical matching
        if claims_texts:
            claims_body = normalize_document_text(
                "\n".join(t for t, _ in claims_texts)
            )
            if claims_body:
                claims_block = f"Ad claims:\n{claims_body}"
                sid0 = claims_texts[0][1]
                claims_span = [
                    DocumentSpan(
                        start=0,
                        end=len(claims_block),
                        text=claims_block,
                        source_signal_id=sid0,
                        source_type="vlm_claims",
                        bbox=None,
                    )
                ]
                _append_section(claims_block, claims_span)

        if asr_texts:
            asr_texts.sort(key=lambda t: len(t[0]), reverse=True)
            transcript = normalize_document_text(asr_texts[0][0])
            asr_sid = asr_texts[0][1]
            if transcript:
                asr_span = [
                    DocumentSpan(
                        start=0,
                        end=len(transcript),
                        text=transcript,
                        source_signal_id=asr_sid,
                        source_type="asr",
                        bbox=None,
                    )
                ]
                _append_section(transcript, asr_span)

        scene_descriptions = _build_scene_descriptions(vision_pairs)
        timeline = _build_timeline(timeline_pairs)

        if timeline:
            tl_text = normalize_document_text(_format_timeline_text(timeline))
            if tl_text:
                _append_section(tl_text, [])

        normalized_body = "".join(body_parts)
        normalized_body = normalize_document_text(normalized_body)

        if scene_descriptions:
            scene_block = "\n\n".join(scene_descriptions)
            if normalized_body:
                normalized = normalize_document_text(f"{normalized_body}\n\n{scene_block}")
            else:
                normalized = scene_block
        else:
            normalized = normalized_body

        return DocumentSignal(
            asset_id=asset_id,
            modality=modality,
            normalized_text=normalized,
            source_signal_ids=list(dict.fromkeys(source_ids)),
            spans=spans,
            scene_descriptions=scene_descriptions,
            timeline=timeline,
            metadata={
                "ocr_token_count": len(ocr_pairs),
                "vlm_claims_count": len(claims_texts),
                "vision_object_count": len(vision_pairs),
                "asr_segment_count": len(asr_texts),
                "document_centric_flag": False,
                "builder_version": "1.1",
            },
        )

    @staticmethod
    def _asset_modality(asset: Any) -> DocumentModality:
        t = asset.get("type") if isinstance(asset, dict) else getattr(asset, "type", None)
        if t in ("text", "image", "audio", "video"):
            return t
        if getattr(asset, "image_data", None) is not None:
            return "image"
        if getattr(asset, "audio_data", None) is not None:
            return "audio"
        return "unknown"

    @staticmethod
    def _asset_id(asset: Any) -> str | None:
        aid = asset.get("asset_id") if isinstance(asset, dict) else getattr(asset, "asset_id", None)
        if aid is None:
            aid = getattr(asset, "image_id", None)
        return str(aid) if aid is not None else None

    @staticmethod
    def _asset_text_content(asset: Any) -> str:
        content = asset.get("content", "") if isinstance(asset, dict) else getattr(asset, "content", "")
        if content is None:
            return ""
        return str(content)
