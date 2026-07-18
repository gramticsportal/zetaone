# zataone object storage

"""
Content-addressable object storage for original asset media.

Objects are keyed by sha256 content hash (the same hash stored on Asset.content_hash),
so identical uploads share one stored object. A small JSON sidecar records the
content type for serving.

Backends:
  local (default) — files under ZATAONE_OBJECT_STORE_DIR (default: ./data/objects)
  gcs             — set ZATAONE_OBJECT_STORE_BUCKET; requires google-cloud-storage

URIs: file:///abs/path/ab/cd/<hash>  or  gs://bucket/objects/ab/cd/<hash>
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_CONTENT_TYPE = "application/octet-stream"


def _shard(content_hash: str) -> str:
    """ab/cd/<hash> layout to keep directories small."""
    return f"{content_hash[:2]}/{content_hash[2:4]}/{content_hash}"


class ObjectStore:
    """Content-addressable object storage (local disk or GCS)."""

    def __init__(self) -> None:
        self._bucket_name = (os.environ.get("ZATAONE_OBJECT_STORE_BUCKET") or "").strip()
        base = (os.environ.get("ZATAONE_OBJECT_STORE_DIR") or "").strip()
        self._base_dir = Path(base) if base else Path("data") / "objects"
        self._gcs_bucket = None

    # ── Public API ────────────────────────────────────────────────────────

    def put(self, data: bytes, content_type: str | None = None) -> str:
        """
        Store bytes; return storage URI. Idempotent — re-putting identical
        content returns the same URI without rewriting.
        """
        content_hash = hashlib.sha256(data or b"").hexdigest()
        ct = content_type or _DEFAULT_CONTENT_TYPE
        if self._bucket_name:
            return self._put_gcs(content_hash, data, ct)
        return self._put_local(content_hash, data, ct)

    def get(self, uri: str) -> tuple[bytes, str]:
        """Fetch (bytes, content_type) for a storage URI. Raises FileNotFoundError."""
        if uri.startswith("gs://"):
            return self._get_gcs(uri)
        if uri.startswith("file://"):
            return self._get_local(Path(uri[len("file://"):]))
        return self._get_local(Path(uri))

    def exists(self, uri: str) -> bool:
        try:
            self.get(uri)
            return True
        except (FileNotFoundError, OSError):
            return False

    # ── Local backend ─────────────────────────────────────────────────────

    def _local_path(self, content_hash: str) -> Path:
        return self._base_dir / _shard(content_hash)

    def _put_local(self, content_hash: str, data: bytes, content_type: str) -> str:
        path = self._local_path(content_hash)
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
            path.with_suffix(".meta").write_text(
                json.dumps({"content_type": content_type}), encoding="utf-8"
            )
        return f"file://{path.resolve().as_posix()}"

    def _get_local(self, path: Path) -> tuple[bytes, str]:
        if not path.is_file():
            raise FileNotFoundError(str(path))
        content_type = _DEFAULT_CONTENT_TYPE
        meta_path = path.with_suffix(".meta")
        if meta_path.is_file():
            try:
                content_type = json.loads(meta_path.read_text(encoding="utf-8")).get(
                    "content_type", _DEFAULT_CONTENT_TYPE
                )
            except (json.JSONDecodeError, OSError):
                pass
        return path.read_bytes(), content_type

    # ── GCS backend ───────────────────────────────────────────────────────

    def _bucket(self):
        if self._gcs_bucket is None:
            from google.cloud import storage as gcs

            self._gcs_bucket = gcs.Client().bucket(self._bucket_name)
        return self._gcs_bucket

    def _put_gcs(self, content_hash: str, data: bytes, content_type: str) -> str:
        key = f"objects/{_shard(content_hash)}"
        blob = self._bucket().blob(key)
        if not blob.exists():
            blob.upload_from_string(data, content_type=content_type)
        return f"gs://{self._bucket_name}/{key}"

    def _get_gcs(self, uri: str) -> tuple[bytes, str]:
        rest = uri[len("gs://"):]
        bucket_name, _, key = rest.partition("/")
        from google.cloud import storage as gcs

        blob = gcs.Client().bucket(bucket_name).get_blob(key)
        if blob is None:
            raise FileNotFoundError(uri)
        return blob.download_as_bytes(), blob.content_type or _DEFAULT_CONTENT_TYPE
