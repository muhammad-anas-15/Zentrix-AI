"""Post-deploy smoke test: is a deployed API healthy, safe and serving data?

    python -m scripts.smoke https://api-staging.example.com
    python -m scripts.smoke http://127.0.0.1:8000 --dev        # local: docs may be on

Checks readiness (database + Redis), market data endpoints, security headers, that API docs, developer sign-in and
metrics are not public, and the response time of each call. Exits 1 if any check fails.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx


@dataclass
class Check:
    name: str
    method: str
    path: str
    expect: Callable[[httpx.Response], str | None]  # None = pass, else the failure reason


def status(code: int) -> Callable[[httpx.Response], str | None]:
    return lambda r: None if r.status_code == code else f"HTTP {r.status_code}, expected {code}"


def ok_json(key: str) -> Callable[[httpx.Response], str | None]:
    def check(r: httpx.Response) -> str | None:
        if r.status_code != 200:
            return f"HTTP {r.status_code}: {r.text[:120]}"
        return None if key in r.json() else f"missing '{key}'"
    return check


def headers_ok(r: httpx.Response) -> str | None:
    missing = [h for h in ("x-content-type-options", "x-frame-options", "x-request-id") if h not in r.headers]
    return f"missing headers {missing}" if missing else None


def checks(dev: bool) -> list[Check]:
    out = [
        Check("liveness", "GET", "/health", ok_json("status")),
        Check("readiness (db + redis)", "GET", "/ready", status(200)),
        Check("security headers", "GET", "/health", headers_ok),
        Check("instruments", "GET", "/v1/instruments?limit=5", ok_json("items")),
        Check("candles EUR/USD 15m", "GET", "/v1/candles?symbol=EUR/USD&timeframe=15m&limit=50", ok_json("candles")),
        Check("live candle BTC/USDT", "GET", "/v1/candles/live?symbol=BTC/USDT&timeframe=15m", ok_json("candle")),
        Check("market radar", "GET", "/v1/radar", ok_json("items")),
        Check("track record", "GET", "/v1/track-record", ok_json("overall")),
        Check("news feed", "GET", "/v1/news/feed?limit=5", ok_json("items")),
        Check("unknown route is JSON 404", "GET", "/v1/nope", status(404)),
        Check("auth required", "GET", "/v1/me", status(401)),
    ]
    if not dev:
        out += [
            Check("docs not public", "GET", "/docs", status(404)),
            Check("openapi not public", "GET", "/openapi.json", status(404)),
            Check("dev sign-in absent", "POST", "/v1/auth/dev", status(404)),
            Check("metrics not public", "GET", "/metrics", lambda r: None if r.status_code in (401, 404)
                  else f"HTTP {r.status_code}"),
        ]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_url")
    ap.add_argument("--dev", action="store_true", help="local dev API: skip the 'not public' checks")
    ap.add_argument("--timeout", type=float, default=30)
    a = ap.parse_args(argv)
    failed = 0
    headers = {"User-Agent": "zentrix-smoke/1.0"}
    with httpx.Client(base_url=a.base_url.rstrip("/"), timeout=a.timeout, headers=headers) as c:
        for ch in checks(a.dev):
            start = time.perf_counter()
            try:
                r = c.request(ch.method, ch.path, json={} if ch.method == "POST" else None)
                reason = ch.expect(r)
            except httpx.HTTPError as exc:
                reason = f"{type(exc).__name__}: {exc}"
            ms = (time.perf_counter() - start) * 1000
            failed += reason is not None
            print(f"{'FAIL' if reason else 'ok  '}  {ms:7.0f} ms  {ch.name}{'  -> ' + reason if reason else ''}")
    print(f"\n{'FAILED' if failed else 'PASSED'}: {failed} of {len(checks(a.dev))} checks failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
