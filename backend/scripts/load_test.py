"""Load test on the signal and market endpoints (closed-loop: N virtual users, each sends its next request as soon as
the previous one returns).

    python -m scripts.load_test http://127.0.0.1:8000 --users 50 --duration 60

Run it against a server started with RATE_LIMIT_ENABLED=false (one machine sends everything from one IP), on a host
like the production one. Prints throughput, error rate and latency percentiles per endpoint; --json for a file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from collections import defaultdict

import httpx

# (weight, name, path): roughly what an app session does; signals and live charts dominate
MIX: list[tuple[int, str, str]] = [
    (25, "signals/latest", "/v1/signals/latest?symbol=EUR/USD&timeframe=15m"),
    (10, "signals (history)", "/v1/signals?limit=20"),
    (10, "track-record", "/v1/track-record"),
    (15, "candles", "/v1/candles?symbol={sym}&timeframe=15m&limit=300"),
    (20, "candles/live", "/v1/candles/live?symbol={live}&timeframe=15m"),
    (8, "radar", "/v1/radar"),
    (7, "news/feed", "/v1/news/feed?limit=20"),
    (5, "conditions", "/v1/conditions?symbol={sym}&timeframe=15m"),
]
SYMBOLS = ["EUR/USD", "GBP/USD", "XAU/USD", "USD/JPY", "BTC/USDT"]
LIVE = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "EUR/USD"]


def pick() -> tuple[str, str]:
    weights = [w for w, _, _ in MIX]
    _, name, path = random.choices(MIX, weights=weights)[0]
    return name, path.format(sym=random.choice(SYMBOLS), live=random.choice(LIVE))


def pct(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))]


async def user(client: httpx.AsyncClient, until: float, stats: dict[str, list[float]], errors: dict[str, int]) -> None:
    while time.perf_counter() < until:
        name, path = pick()
        start = time.perf_counter()
        try:
            r = await client.get(path)
            if r.status_code >= 400:
                errors[name] += 1
        except httpx.HTTPError:
            errors[name] += 1
        stats[name].append((time.perf_counter() - start) * 1000)


async def run(base: str, users: int, duration: float) -> dict[str, object]:
    stats: dict[str, list[float]] = defaultdict(list)
    errors: dict[str, int] = defaultdict(int)
    limits = httpx.Limits(max_connections=users, max_keepalive_connections=users)
    async with httpx.AsyncClient(base_url=base, timeout=30, limits=limits) as client:
        await client.get("/health")
        until = time.perf_counter() + duration
        start = time.perf_counter()
        await asyncio.gather(*(user(client, until, stats, errors) for _ in range(users)))
        elapsed = time.perf_counter() - start
    rows = {}
    for name in sorted(stats, key=lambda n: -len(stats[n])):
        v = stats[name]
        rows[name] = {"requests": len(v), "rps": round(len(v) / elapsed, 1), "errors": errors[name],
                      "p50_ms": round(statistics.median(v), 1), "p95_ms": round(pct(v, 0.95), 1),
                      "p99_ms": round(pct(v, 0.99), 1), "max_ms": round(max(v), 1)}
    total = sum(len(v) for v in stats.values())
    all_ms = [x for v in stats.values() for x in v]
    return {"users": users, "duration_s": round(elapsed, 1), "requests": total, "rps": round(total / elapsed, 1),
            "errors": sum(errors.values()), "p50_ms": round(statistics.median(all_ms), 1),
            "p95_ms": round(pct(all_ms, 0.95), 1), "p99_ms": round(pct(all_ms, 0.99), 1), "endpoints": rows}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_url")
    ap.add_argument("--users", type=int, default=50)
    ap.add_argument("--duration", type=float, default=60)
    ap.add_argument("--json", help="also write the result to this file")
    a = ap.parse_args()
    res = asyncio.run(run(a.base_url.rstrip("/"), a.users, a.duration))
    print(f"{res['users']} users, {res['duration_s']} s: {res['requests']} requests, {res['rps']} req/s, "
          f"{res['errors']} errors, p50 {res['p50_ms']} ms, p95 {res['p95_ms']} ms, p99 {res['p99_ms']} ms")
    print(f"{'endpoint':20} {'req':>6} {'req/s':>7} {'err':>5} {'p50':>8} {'p95':>8} {'p99':>8} {'max':>8}")
    for name, r in res["endpoints"].items():  # type: ignore[attr-defined]
        print(f"{name:20} {r['requests']:>6} {r['rps']:>7} {r['errors']:>5} {r['p50_ms']:>8} {r['p95_ms']:>8} "
              f"{r['p99_ms']:>8} {r['max_ms']:>8}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2)


if __name__ == "__main__":
    main()
