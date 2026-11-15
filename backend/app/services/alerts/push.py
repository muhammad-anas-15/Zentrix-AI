"""Push delivery via Firebase Cloud Messaging HTTP v1, and the alert-event outbox.

``FcmSender`` signs a service-account JWT (RS256, PyJWT), exchanges it for an OAuth access token and posts one
message per device token. Tokens FCM reports as unregistered/invalid are deleted. Without credentials the
``DisabledSender`` is used: events stay in the in-app inbox with delivery ``disabled``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
import jwt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.tools import AlertEvent
from app.models.user import Device

log = get_logger(__name__)
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


@dataclass(frozen=True)
class SendResult:
    ok: bool
    unregistered: bool = False
    error: str | None = None


class PushSender(Protocol):
    enabled: bool

    async def send(self, token: str, title: str, body: str, data: dict[str, str]) -> SendResult: ...


class DisabledSender:
    enabled = False

    async def send(self, token: str, title: str, body: str, data: dict[str, str]) -> SendResult:
        return SendResult(False, error="push not configured")


class FcmSender:
    enabled = True

    def __init__(self, credentials: dict[str, Any], transport: httpx.AsyncBaseTransport | None = None,
                 clock: Any = time.time) -> None:
        self.project = credentials["project_id"]
        self.email = credentials["client_email"]
        self.key = credentials["private_key"]
        self.token_uri = credentials.get("token_uri", "https://oauth2.googleapis.com/token")
        self.transport = transport
        self.clock = clock
        self._token: str | None = None
        self._expires = 0.0

    @classmethod
    def from_file(cls, path: Path) -> FcmSender:
        return cls(json.loads(path.read_text(encoding="utf-8")))

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        now = self.clock()
        if self._token and now < self._expires - 60:
            return self._token
        assertion = jwt.encode({"iss": self.email, "scope": FCM_SCOPE, "aud": self.token_uri, "iat": int(now),
                                "exp": int(now) + 3600}, self.key, algorithm="RS256")
        r = await client.post(self.token_uri, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                                    "assertion": assertion})
        r.raise_for_status()
        body = r.json()
        self._token, self._expires = body["access_token"], now + float(body.get("expires_in", 3600))
        return self._token

    async def send(self, token: str, title: str, body: str, data: dict[str, str]) -> SendResult:
        async with httpx.AsyncClient(timeout=10, transport=self.transport) as client:
            try:
                access = await self._access_token(client)
                r = await client.post(
                    f"https://fcm.googleapis.com/v1/projects/{self.project}/messages:send",
                    headers={"Authorization": f"Bearer {access}"},
                    json={"message": {"token": token, "notification": {"title": title, "body": body},
                                      "data": data, "android": {"priority": "high"}}})
            except httpx.HTTPError as exc:
                return SendResult(False, error=type(exc).__name__)
        if r.status_code == 200:
            return SendResult(True)
        status = ""
        try:
            err = r.json().get("error", {})
            status = err.get("status", "")
            codes = {d.get("errorCode") for d in err.get("details", []) if isinstance(d, dict)}
        except ValueError:
            codes = set()
        # Only UNREGISTERED means the token is dead; INVALID_ARGUMENT can also be our payload, so keep the token.
        if r.status_code == 404 or "UNREGISTERED" in codes:
            return SendResult(False, unregistered=True, error="unregistered")
        if r.status_code == 401:
            self._token = None
        return SendResult(False, error=f"http {r.status_code} {status}".strip())


def make_sender(credentials_file: Path | None) -> PushSender:
    if credentials_file is None:
        return DisabledSender()
    return FcmSender.from_file(credentials_file)


async def deliver_pending(db: AsyncSession, sender: PushSender, now: datetime, max_attempts: int = 3,
                          batch: int = 200) -> dict[str, int]:
    """Send pending (and previously failed) alert events to each of the user's devices. Caller commits."""
    events = (await db.scalars(select(AlertEvent).where(AlertEvent.delivery.in_(("pending", "failed")),
                                                        AlertEvent.attempts < max_attempts)
                               .order_by(AlertEvent.id).limit(batch))).all()
    counts = {"sent": 0, "partial": 0, "failed": 0, "no_devices": 0, "disabled": 0, "removed_tokens": 0}
    for ev in events:
        ev.attempts += 1
        if not sender.enabled:
            ev.delivery = "disabled"
            counts["disabled"] += 1
            continue
        devices = (await db.scalars(select(Device).where(Device.user_id == ev.user_id))).all()
        if not devices:
            ev.delivery = "no_devices"
            counts["no_devices"] += 1
            continue
        data = {k: str(v) for k, v in (ev.data or {}).items()} | {"event_id": str(ev.id), "kind": ev.kind}
        ok = 0
        errors: list[str] = []
        dead: list[int] = []
        for d in devices:
            res = await sender.send(d.fcm_token, ev.title, ev.body, data)
            if res.ok:
                ok += 1
            elif res.unregistered:
                dead.append(d.id)
            else:
                errors.append(res.error or "error")
        if dead:
            await db.execute(delete(Device).where(Device.id.in_(dead)))
            counts["removed_tokens"] += len(dead)
        ev.error = "; ".join(sorted(set(errors))) or None
        if ok and not errors:
            ev.delivery, ev.delivered_at = "sent", now
        elif ok:
            ev.delivery, ev.delivered_at = "partial", now
        elif errors:
            ev.delivery = "failed"
        else:
            ev.delivery = "no_devices"  # every token was dead
        counts[ev.delivery] += 1
    if events:
        log.info("push_delivery", **counts)
    return counts
