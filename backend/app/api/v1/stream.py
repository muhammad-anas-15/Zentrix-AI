"""WebSocket ``/v1/stream``: live public market events (closed candles, new signals).

Protocol (JSON text frames):
  client -> {"action": "subscribe", "symbols": ["EUR/USD"], "timeframes": ["15m"], "types": ["candle", "signal"]}
  client -> {"action": "ping"}
  server -> {"type": "hello"} | {"type": "subscribed", ...} | {"type": "candle", ...} | {"type": "signal", ...}
            | {"type": "pong"} | {"type": "error", "message": ...}
A new subscribe message replaces the previous subscription. Rate limited per IP at connect.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.errors import AppError
from app.core.logging import get_logger
from app.core.ratelimit import client_ip, enforce
from app.services.realtime import CHANNEL, matches

router = APIRouter(tags=["signals"])
log = get_logger(__name__)
MAX_SYMBOLS = 50
TYPES = {"candle", "signal"}


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
    pubsub = ws.app.state.redis.pubsub()
    try:
        await pubsub.subscribe(CHANNEL)
    except Exception:
        await ws.send_json({"type": "error", "message": "live stream unavailable; poll the REST endpoints"})
        await ws.close(code=1011)
        return
    await ws.send_json({"type": "hello", "channel": "public", "max_symbols": MAX_SYMBOLS})

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
                await ws.send_json(event)

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
                await ws.send_json({"type": "error", "message": "unknown action (use subscribe or ping)"})
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()
