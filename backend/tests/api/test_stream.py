"""WebSocket /v1/stream driven over raw ASGI (same event loop as the app and fakeredis)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import fakeredis
from fastapi import FastAPI

from app.services.realtime import CHANNEL


class WS:
    def __init__(self, app: FastAPI) -> None:
        self.app = app
        self.inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.outbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.task: asyncio.Task[None] | None = None

    async def connect(self) -> dict[str, Any]:
        scope = {"type": "websocket", "path": "/v1/stream", "raw_path": b"/v1/stream", "query_string": b"",
                 "headers": [(b"host", b"test")], "client": ("10.0.0.9", 5000), "server": ("test", 80),
                 "scheme": "ws", "subprotocols": [], "asgi": {"version": "3.0"}, "root_path": ""}
        self.task = asyncio.create_task(self.app(scope, self.inbox.get, self.outbox.put))  # type: ignore[arg-type]
        await self.inbox.put({"type": "websocket.connect"})
        return await self.raw()

    async def raw(self) -> dict[str, Any]:
        return await asyncio.wait_for(self.outbox.get(), 5)

    async def recv(self) -> dict[str, Any]:
        msg = await self.raw()
        assert msg["type"] == "websocket.send", msg
        return json.loads(msg["text"])  # type: ignore[no-any-return]

    async def send(self, data: Any) -> None:
        text = data if isinstance(data, str) else json.dumps(data)
        await self.inbox.put({"type": "websocket.receive", "text": text})

    async def close(self) -> None:
        await self.inbox.put({"type": "websocket.disconnect", "code": 1000})
        assert self.task is not None
        await asyncio.wait_for(self.task, 5)


async def test_stream_filters_live_events(app: FastAPI, fake_redis: fakeredis.FakeAsyncRedis) -> None:
    ws = WS(app)
    assert (await ws.connect())["type"] == "websocket.accept"
    assert (await ws.recv())["type"] == "hello"
    await ws.send({"action": "subscribe", "symbols": ["EUR/USD"], "timeframes": ["15m"]})
    sub = await ws.recv()
    assert sub == {"type": "subscribed", "symbols": ["EUR/USD"], "timeframes": ["15m"], "types": ["candle", "signal"]}

    def candle(symbol: str, tf: str, c: float) -> str:
        return json.dumps({"type": "candle", "symbol": symbol, "venue": "twelvedata", "timeframe": tf,
                           "candle": {"t": "2026-11-04T14:00:00+00:00", "o": c, "h": c, "l": c, "c": c, "v": None}})

    await fake_redis.publish(CHANNEL, candle("GBP/USD", "15m", 1.3))  # not subscribed
    await fake_redis.publish(CHANNEL, candle("EUR/USD", "1h", 1.2))  # other timeframe
    await fake_redis.publish(CHANNEL, candle("EUR/USD", "15m", 1.1))
    await fake_redis.publish(CHANNEL, json.dumps({"type": "signal", "symbol": "EUR/USD", "timeframe": "15m",
                                                  "id": 7, "strength": "Very Weak - Wait"}))
    got = [await ws.recv(), await ws.recv()]
    assert [(e["type"], e.get("candle", {}).get("c")) for e in got] == [("candle", 1.1), ("signal", None)]

    await ws.send({"action": "ping"})
    assert await ws.recv() == {"type": "pong"}
    await ws.send("not json")
    assert (await ws.recv())["type"] == "error"
    await ws.send({"action": "subscribe", "symbols": [f"S{i}" for i in range(51)]})
    assert "at most 50" in (await ws.recv())["message"]
    await ws.close()
