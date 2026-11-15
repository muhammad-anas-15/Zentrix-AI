"""WebSocket ``/v1/stream``: live public market events (closed candles, new signals).

Protocol (JSON text frames):
  client -> {"action": "subscribe", "symbols": ["EUR/USD"], "timeframes": ["15m"], "types": ["candle", "signal"]}
  client -> {"action": "auth", "access_token": "..."}   (optional)
  client -> {"action": "ping"}
  server -> {"type": "hello"} | {"type": "subscribed", ...} | {"type": "authenticated", ...} | {"type": "candle", ...}
            | {"type": "signal", ...} | {"type": "pong"} | {"type": "error", "message": ...}
A new subscribe message replaces the previous subscription. Rate limited per IP at connect.

Premium (``all_markets``, only while PREMIUM_ENFORCED=true): signal events outside the free markets are sent only
to a connection authenticated as a user with that feature, until the access token expires (send a fresh token
with another ``auth`` to continue). Candle events are public.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.errors import AppError
from app.core.logging import get_logger
from app.core.ratelimit import client_ip, enforce
from app.core.security import decode_access_token
from app.models.user import User
from app.services.entitlements import is_free_market, resolve_access
from app.services.realtime import CHANNEL, matches

router = APIRouter(tags=["signals"])
log = get_logger(__name__)
MAX_SYMBOLS = 50
MAX_AUTH = 10  # auth messages per connection
TYPES = {"candle", "signal"}
PREMIUM_LABEL = {"feature": "all_markets", "label": "Premium"}


class Viewer:
    """Who is on this connection, for the all_markets filter."""

    def __init__(self, enforced: bool) -> None:
        self.enforced = enforced
        self.all_markets_until: float | None = None  # epoch seconds; None = no premium-market signals
        self.auth_attempts = 0


async def _authenticate(ws: WebSocket, viewer: Viewer, token: object) -> dict[str, Any]:
    settings = ws.app.state.settings
    viewer.auth_attempts += 1
    if viewer.auth_attempts > MAX_AUTH:
        return {"type": "error", "code": "too_many_auth", "message": f"at most {MAX_AUTH} auth messages"}
    if not isinstance(token, str) or not token:
        return {"type": "error", "code": "invalid_token", "message": "send access_token"}
    try:
        claims = decode_access_token(settings, token)
    except AppError as exc:
        return {"type": "error", "code": exc.code, "message": exc.message}
    now = datetime.fromtimestamp(ws.app.state.clock(), tz=UTC)
    async with ws.app.state.sessionmaker() as db:
        user = await db.get(User, claims.user_id)
        if user is None or user.token_version != claims.version:
            return {"type": "error", "code": "token_revoked", "message": "sign in again"}
        access = await resolve_access(db, user, now)
    allowed = access.has("all_markets") or not settings.premium_enforced
    viewer.all_markets_until = float(claims.expires_at) if allowed else None
    return {"type": "authenticated", "plan": access.plan, "all_markets": allowed,
            "expires_at": datetime.fromtimestamp(claims.expires_at, tz=UTC).isoformat()}


def _visible(ws: WebSocket, viewer: Viewer, event: dict[str, Any]) -> dict[str, Any] | None:
    """The event to send (with its Premium label), or None when the viewer may not see it."""
    if event.get("type") != "signal":
        return event
    settings = ws.app.state.settings
    if is_free_market(settings, str(event.get("symbol")), str(event.get("timeframe"))):
        return event
    if viewer.enforced and (viewer.all_markets_until is None or ws.app.state.clock() >= viewer.all_markets_until):
        return None
    return {**event, "premium": PREMIUM_LABEL}


@router.websocket("/stream")
async def stream(ws: WebSocket) -> None:
    settings = ws.app.state.settings
    try:
        await enforce(ws, "public", client_ip(ws, settings), settings.rate_limit_public)
    except AppError:
        await ws.close(code=1013, reason="rate limited")
        return
    await ws.accept()
    sub: dict[str, set[str]] = {"symbols": set(), "timeframes": set(), "types": set(TYPES)}
    viewer = Viewer(settings.premium_enforced)
    pubsub = ws.app.state.redis.pubsub()
    try:
        await pubsub.subscribe(CHANNEL)
    except Exception:
        await ws.send_json({"type": "error", "message": "live stream unavailable; poll the REST endpoints"})
        await ws.close(code=1011)
        return
    await ws.send_json({"type": "hello", "channel": "public", "max_symbols": MAX_SYMBOLS,
                        "premium_enforced": settings.premium_enforced,
                        "free_markets": {"symbols": list(settings.free_signal_symbols),
                                         "timeframes": list(settings.free_signal_timeframes)}})

    async def pump() -> None:
        while True:
            try:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            except Exception:  # Redis connection lost: tell the client to fall back to polling
                log.warning("stream_feed_lost")
                with contextlib.suppress(Exception):
                    await ws.send_json({"type": "error", "message": "live stream interrupted; reconnect or poll"})
                    await ws.close(code=1011)
                return
            if msg is None:
                continue
            try:
                event: dict[str, Any] = json.loads(msg["data"])
            except (TypeError, ValueError):
                continue
            if matches(event, sub["symbols"], sub["timeframes"], sub["types"]):
                out = _visible(ws, viewer, event)
                if out is not None:
                    await ws.send_json(out)

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                data = json.loads(await ws.receive_text())
            except ValueError:
                await ws.send_json({"type": "error", "message": "send JSON"})
                continue
            action = data.get("action") if isinstance(data, dict) else None
            if action == "ping":
                await ws.send_json({"type": "pong"})
            elif action == "auth":
                await ws.send_json(await _authenticate(ws, viewer, data.get("access_token")))
            elif action == "subscribe":
                symbols = {str(s) for s in data.get("symbols") or []}
                if len(symbols) > MAX_SYMBOLS:
                    await ws.send_json({"type": "error", "message": f"at most {MAX_SYMBOLS} symbols"})
                    continue
                types = {str(t) for t in data.get("types") or TYPES} & TYPES
                sub.update(symbols=symbols, timeframes={str(t) for t in data.get("timeframes") or []}, types=types)
                await ws.send_json({"type": "subscribed", "symbols": sorted(symbols),
                                    "timeframes": sorted(sub["timeframes"]), "types": sorted(types)})
            else:
                await ws.send_json({"type": "error", "message": "unknown action (use subscribe, auth or ping)"})
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()
