# zataone video extractor

"""
VideoExtractor — compliance signal extraction from video assets.

Strategy:
  1. Audio track  → ffmpeg → temp WAV → faster-whisper ASR → asr_text signal
  2. Key frames   → ffmpeg (0.5 fps, max 20 frames) → pytesseract OCR → ocr_frame_text signals

Graceful degradation:
  - ffmpeg absent  : logs a warning, returns empty list
  - faster-whisper absent : skips ASR, still does frame OCR
  - pytesseract absent    : skips frame OCR, still does ASR

Video bytes are accepted via:
  - asset.video_data  (raw bytes)
  - asset.content     (base64-encoded string)
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from typing import Any

from zataone.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

_FFMPEG: str | None = None


def _ffmpeg_path() -> str | None:
    global _FFMPEG
    if _FFMPEG is None:
        _FFMPEG = shutil.which("ffmpeg") or ""
    return _FFMPEG or None


# ── Signal dataclass (matches text_extractor.Signal shape) ───────────────────


@dataclass
class Signal:
    signal_id: str
    signal_type: str
    source_model: str
    confidence: float
    raw_data: dict
    bounding_box: None = None


# ── Extractor ─────────────────────────────────────────────────────────────────


class VideoExtractor(BaseExtractor):
    """
    Video signal extractor for compliance-sensitive content.

    Extracts spoken-word (ASR) and on-screen-text (OCR) signals from video files.
    Both modalities feed into the same keyword / pattern policy rules as text assets.
    """

    extractor_id = "video_extractor"
    version = "1.0"

    # Sample this many frames per second (0.5 = 1 frame every 2 seconds)
    _FRAME_FPS: float = 0.5
    # Never process more than this many frames per video
    _MAX_FRAMES: int = 20

    def extract(self, asset: Any) -> list[Signal]:
        asset_type = (
            asset.get("type") if isinstance(asset, dict) else getattr(asset, "type", None)
        )
        if asset_type != "video":
            return []

        video_bytes = self._get_video_bytes(asset)
        if not video_bytes:
            logger.warning("VideoExtractor: no video bytes in asset")
            return []

        if not _ffmpeg_path():
            logger.warning(
                "VideoExtractor: ffmpeg not found on PATH. "
                "Install ffmpeg to enable video analysis."
            )
            return []

        signals: list[Signal] = []

        with tempfile.TemporaryDirectory(prefix="zataone_video_") as tmpdir:
            video_path = os.path.join(tmpdir, "input.mp4")
            with open(video_path, "wb") as f:
                f.write(video_bytes)

            # 1. ASR
            asr_signals = self._extract_asr(video_path, tmpdir)
            signals.extend(asr_signals)

            # 2. Frame OCR
            ocr_signals = self._extract_frame_ocr(video_path, tmpdir)
            signals.extend(ocr_signals)

        return signals

    # ── ASR ───────────────────────────────────────────────────────────────────

    def _extract_asr(self, video_path: str, tmpdir: str) -> list[Signal]:
        from zataone.extractors.modality import asr as asr_mod

        if not asr_mod.FASTER_WHISPER_AVAILABLE:
            logger.debug("VideoExtractor: faster-whisper unavailable; skipping ASR")
            return []

        audio_path = os.path.join(tmpdir, "audio.wav")
        try:
            result = subprocess.run(
                [
                    _ffmpeg_path(), "-y", "-i", video_path,
                    "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                    audio_path,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
            )
            if result.returncode != 0 or not os.path.exists(audio_path):
                logger.warning("VideoExtractor: ffmpeg audio extraction failed (rc=%s)", result.returncode)
                return []
        except Exception as exc:
            logger.warning("VideoExtractor: audio extraction error: %s", exc)
            return []

        try:
            with open(audio_path, "rb") as af:
                audio_bytes = af.read()
            text, info = asr_mod.transcribe_audio_bytes(audio_bytes, "audio.wav")
        except Exception as exc:
            logger.warning("VideoExtractor: ASR transcription error: %s", exc)
            return []

        if not text:
            return []

        conf = float(getattr(info, "language_probability", 1.0) or 1.0)
        conf = min(1.0, max(0.0, conf))
        return [
            Signal(
                signal_id=str(uuid.uuid4()),
                signal_type="asr_text",
                source_model=self.extractor_id,
                confidence=conf,
                raw_data={
                    "type": "asr_text",
                    "text": text,
                    "source": "video_audio",
                    "language": getattr(info, "language", None),
                },
            )
        ]

    # ── Frame OCR ─────────────────────────────────────────────────────────────

    def _extract_frame_ocr(self, video_path: str, tmpdir: str) -> list[Signal]:
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            logger.debug("VideoExtractor: pytesseract/Pillow unavailable; skipping frame OCR")
            return []

        frames_dir = os.path.join(tmpdir, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        frame_pattern = os.path.join(frames_dir, "frame_%04d.jpg")

        try:
            result = subprocess.run(
                [
                    _ffmpeg_path(), "-y", "-i", video_path,
                    "-vf", f"fps={self._FRAME_FPS}",
                    "-frames:v", str(self._MAX_FRAMES),
                    "-q:v", "3",
                    frame_pattern,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
            )
            if result.returncode != 0:
                logger.warning("VideoExtractor: frame extraction failed (rc=%s)", result.returncode)
                return []
        except Exception as exc:
            logger.warning("VideoExtractor: frame extraction error: %s", exc)
            return []

        signals: list[Signal] = []
        frame_files = sorted(
            f for f in os.listdir(frames_dir) if f.endswith(".jpg")
        )[: self._MAX_FRAMES]

        for fname in frame_files:
            frame_path = os.path.join(frames_dir, fname)
            try:
                img = Image.open(frame_path)
                ocr_result = pytesseract.image_to_data(
                    img, output_type=pytesseract.Output.DICT
                )
                words = [
                    w for w, c in zip(ocr_result["text"], ocr_result["conf"])
                    if w.strip() and int(c) >= 40
                ]
                if not words:
                    continue
                text = " ".join(words)
                avg_conf = sum(
                    int(c) for w, c in zip(ocr_result["text"], ocr_result["conf"])
                    if w.strip() and int(c) >= 40
                ) / (len(words) * 100)  # normalise to 0-1
                signals.append(
                    Signal(
                        signal_id=str(uuid.uuid4()),
                        signal_type="ocr_frame_text",
                        source_model=self.extractor_id,
                        confidence=min(1.0, avg_conf),
                        raw_data={
                            "type": "ocr_frame_text",
                            "text": text,
                            "frame": fname,
                            "source": "video_frame",
                        },
                    )
                )
            except Exception as exc:
                logger.debug("VideoExtractor: OCR failed for frame %s: %s", fname, exc)

        return signals

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _get_video_bytes(asset: Any) -> bytes | None:
        video_data = (
            asset.get("video_data") if isinstance(asset, dict)
            else getattr(asset, "video_data", None)
        )
        if isinstance(video_data, (bytes, bytearray)):
            return bytes(video_data)

        content = (
            asset.get("content") if isinstance(asset, dict)
            else getattr(asset, "content", None)
        )
        if isinstance(content, bytes):
            return content
        if isinstance(content, str) and content:
            try:
                return base64.b64decode(content)
            except Exception:
                return None
        return None
