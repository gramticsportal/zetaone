# zataone stuck-asset reaper

"""
Marks assets stuck in status='processing' as failed so they never hang forever
(e.g. after an instance recycle killed the background pipeline thread).

Runs a sweep at startup, then periodically in a daemon thread.

Env:
  ZATAONE_STUCK_ASSET_TIMEOUT_MIN  — minutes before 'processing' counts as stuck (default 30)
  ZATAONE_REAPER_INTERVAL_S        — seconds between sweeps (default 300); 0 disables the loop
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()


def _timeout_minutes() -> int:
    v = (os.environ.get("ZATAONE_STUCK_ASSET_TIMEOUT_MIN") or "").strip()
    return int(v) if v.isdigit() and int(v) > 0 else 30


def _interval_seconds() -> int:
    v = (os.environ.get("ZATAONE_REAPER_INTERVAL_S") or "").strip()
    if v.isdigit():
        return int(v)
    return 300


def reap_stuck_assets() -> int:
    """One sweep: fail assets processing longer than the timeout. Returns count."""
    from zataone.models import Asset as AssetModel
    from zataone.storage.database import get_session_factory

    cutoff = datetime.utcnow() - timedelta(minutes=_timeout_minutes())
    session = get_session_factory()()
    try:
        stuck = (
            session.query(AssetModel)
            .filter(AssetModel.status == "processing", AssetModel.created_at < cutoff)
            .all()
        )
        for a in stuck:
            a.status = "failed"
        if stuck:
            session.commit()
            logger.warning(
                "Reaper marked %d stuck asset(s) as failed: %s",
                len(stuck),
                [str(a.id) for a in stuck[:20]],
            )
        return len(stuck)
    except Exception:
        session.rollback()
        logger.exception("Reaper sweep failed")
        return 0
    finally:
        session.close()


def start_reaper() -> None:
    """Start the periodic sweep loop once (idempotent). Safe if DB is down."""
    global _started
    with _lock:
        if _started:
            return
        _started = True

    interval = _interval_seconds()

    def _loop() -> None:
        # Initial sweep shortly after startup, then periodic.
        try:
            reap_stuck_assets()
        except Exception:
            logger.exception("Initial reaper sweep failed")
        if interval <= 0:
            return
        stop_wait = threading.Event()
        while True:
            stop_wait.wait(interval)
            try:
                reap_stuck_assets()
            except Exception:
                logger.exception("Reaper sweep failed")

    threading.Thread(target=_loop, name="zataone-reaper", daemon=True).start()
