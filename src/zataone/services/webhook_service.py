# zataone webhook service

"""
WebhookService — register, manage, and fire compliance event webhooks.

Delivery uses httpx (already a project dependency), HMAC-SHA256 signed payloads,
and up to 3 retries with exponential back-off. Fire-and-forget: delivery is
dispatched in a daemon thread so it never blocks the compliance pipeline.

Event types:
  verdict.completed  — every successful compliance check
  verdict.flagged    — only when status is NON_COMPLIANT or BORDERLINE
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_VALID_EVENTS = frozenset({"verdict.completed", "verdict.flagged"})
_DELIVERY_TIMEOUT = 10        # seconds per attempt
_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 1.5           # seconds; attempt n waits base^(n-1)


class WebhookService:

    # ── Registration ──────────────────────────────────────────────────────

    def register(
        self,
        session: Any,
        url: str,
        events: list[str],
        *,
        tenant_id: uuid.UUID | str | None = None,
        secret: str | None = None,
    ) -> "Webhook":  # noqa: F821 — avoids circular at module load
        from zataone.models.webhook import Webhook

        unknown = [e for e in events if e not in _VALID_EVENTS]
        if unknown:
            raise ValueError(f"Unknown event types: {unknown}. Valid: {sorted(_VALID_EVENTS)}")
        if not url.startswith(("http://", "https://")):
            raise ValueError("Webhook URL must start with http:// or https://")

        hook = Webhook(
            tenant_id=uuid.UUID(str(tenant_id)) if tenant_id else None,
            url=url,
            secret=secret,
            events=list(events),
        )
        session.add(hook)
        return hook

    def list_hooks(
        self,
        session: Any,
        tenant_id: uuid.UUID | str | None = None,
    ) -> list[dict[str, Any]]:
        from zataone.models.webhook import Webhook

        q = session.query(Webhook).filter(Webhook.is_active == True)  # noqa: E712
        if tenant_id is not None:
            q = q.filter(Webhook.tenant_id == uuid.UUID(str(tenant_id)))
        hooks = q.order_by(Webhook.created_at.desc()).all()
        return [self._to_dict(h) for h in hooks]

    def deactivate(self, session: Any, webhook_id: uuid.UUID) -> bool:
        from zataone.models.webhook import Webhook

        hook = session.query(Webhook).filter(Webhook.id == webhook_id).first()
        if hook is None:
            return False
        hook.is_active = False
        return True

    # ── Event dispatch ────────────────────────────────────────────────────

    def fire_event_async(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        tenant_id: uuid.UUID | str | None = None,
        session_factory: Any = None,
    ) -> None:
        """
        Dispatch event to all matching webhooks in a daemon thread.

        Does not block; exceptions are logged, never raised.
        """
        t = threading.Thread(
            target=self._fire_event_sync,
            args=(event_type, payload, tenant_id, session_factory),
            daemon=True,
        )
        t.start()

    def _fire_event_sync(
        self,
        event_type: str,
        payload: dict[str, Any],
        tenant_id: Any,
        session_factory: Any,
    ) -> None:
        try:
            from zataone.models.webhook import Webhook
            from zataone.storage.database import get_session_factory

            factory = session_factory or get_session_factory()
            session = factory()
            try:
                q = session.query(Webhook).filter(Webhook.is_active == True)  # noqa: E712
                if tenant_id is not None:
                    tid = uuid.UUID(str(tenant_id))
                    q = q.filter(
                        (Webhook.tenant_id == tid) | (Webhook.tenant_id == None)  # noqa: E711
                    )
                hooks = q.all()

                matching = [h for h in hooks if event_type in (h.events or [])]
                if not matching:
                    return

                payload_str = json.dumps({
                    "event": event_type,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    **payload,
                }, default=str)

                for hook in matching:
                    status_code = self._deliver(hook, payload_str, event_type)
                    hook.last_triggered_at = datetime.utcnow()
                    hook.last_status_code = status_code

                session.commit()
            finally:
                session.close()
        except Exception:
            logger.exception("Webhook dispatch failed for event %s", event_type)

    def _deliver(self, hook: Any, payload_str: str, event_type: str) -> int:
        """POST payload to hook URL with HMAC sig. Returns final HTTP status."""
        try:
            import httpx
        except ImportError:
            logger.error("httpx not installed; cannot deliver webhook")
            return 0

        headers = {
            "Content-Type": "application/json",
            "X-ZataOne-Event": event_type,
            "User-Agent": "ZataOne-Webhook/1.0",
        }
        if hook.secret:
            sig = hmac.new(
                hook.secret.encode(), payload_str.encode(), hashlib.sha256
            ).hexdigest()
            headers["X-ZataOne-Signature"] = f"sha256={sig}"

        status_code = 0
        for attempt in range(_MAX_ATTEMPTS):
            if attempt > 0:
                time.sleep(_BACKOFF_BASE ** (attempt - 1))
            try:
                resp = httpx.post(
                    hook.url,
                    content=payload_str,
                    headers=headers,
                    timeout=_DELIVERY_TIMEOUT,
                )
                status_code = resp.status_code
                if resp.is_success:
                    logger.debug(
                        "Webhook delivered to %s (event=%s, status=%s)",
                        hook.url, event_type, status_code,
                    )
                    return status_code
                logger.warning(
                    "Webhook %s returned %s on attempt %d",
                    hook.url, status_code, attempt + 1,
                )
            except Exception as exc:
                logger.warning(
                    "Webhook %s delivery error on attempt %d: %s",
                    hook.url, attempt + 1, exc,
                )
        return status_code

    # ── Serialization ─────────────────────────────────────────────────────

    @staticmethod
    def _to_dict(hook: Any) -> dict[str, Any]:
        return {
            "webhook_id": str(hook.id),
            "tenant_id": str(hook.tenant_id) if hook.tenant_id else None,
            "url": hook.url,
            "events": hook.events or [],
            "is_active": hook.is_active,
            "created_at": hook.created_at.isoformat() if hook.created_at else None,
            "last_triggered_at": hook.last_triggered_at.isoformat() if hook.last_triggered_at else None,
            "last_status_code": hook.last_status_code,
        }
