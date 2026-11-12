from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
import pytest

from ml.data import history
from ml.data.sources import binance, twelvedata
from ml.settings import get_settings
from tests.conftest import T0, make_candles

M15 = 900


class FakeResponse:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> Any:
        return self.payload


class FakeSession:
    def __init__(self, payloads: list[Any]) -> None:
        self.payloads = payloads
        self.calls: list[dict] = []
        self.urls: list[str] = []

    def get(self, url: str, params: dict, timeout: int) -> FakeResponse:
        self.calls.append(params)
        self.urls.append(url)
        return FakeResponse(self.payloads.pop(0))


@pytest.fixture
def td_key(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-secret-key")
    monkeypatch.setenv("TWELVE_DATA_MIN_INTERVAL_S", "0")
    get_settings.cache_clear()
    yield "test-secret-key"
    get_settings.cache_clear()


def test_twelvedata_parses_utc_and_requests_utc(td_key: str) -> None:
    session = FakeSession([{"values": [  # newest first, as the API returns
        {"datetime": "2026-11-12 12:30:00", "open": "1.1", "high": "1.2", "low": "1.0", "close": "1.15"},
        {"datetime": "2026-11-12 12:15:00", "open": "1.0", "high": "1.1", "low": "0.9", "close": "1.05"},
    ]}])
    rows = twelvedata.fetch_time_series("EUR/USD", "15m", outputsize=2, session=session)  # type: ignore[arg-type]
    assert session.calls[0]["timezone"] == "UTC"
    assert [r["time"] for r in rows] == [
        int(datetime(2026, 11, 12, 12, 15, tzinfo=UTC).timestamp()),
        int(datetime(2026, 11, 12, 12, 30, tzinfo=UTC).timestamp()),
    ]
    assert rows[0]["volume"] == 0.0


def test_twelvedata_errors_never_leak_the_key(td_key: str) -> None:
    session = FakeSession([{"code": 401, "message": "Invalid API key", "status": "error"}])
    with pytest.raises(twelvedata.TwelveDataError) as exc:
        twelvedata.fetch_time_series("EUR/USD", "15m", session=session)  # type: ignore[arg-type]
    assert td_key not in str(exc.value)


def test_twelvedata_no_data_returns_empty(td_key: str) -> None:
    session = FakeSession([{"code": 400, "message": "No data is available on the specified dates."}])
    assert twelvedata.fetch_time_series("EUR/USD", "15m", session=session) == []  # type: ignore[arg-type]


def test_twelvedata_fetch_range_pages_backwards(monkeypatch: pytest.MonkeyPatch) -> None:
    all_rows = make_candles(12_000, "15m").to_dict("records")
    seen_end: list[int | None] = []

    def fake(symbol: str, interval: str, outputsize: int, end_ts: int | None = None, session: Any = None):
        seen_end.append(end_ts)
        upto = [r for r in all_rows if end_ts is None or r["time"] <= end_ts]
        return upto[-outputsize:]

    monkeypatch.setattr(twelvedata, "fetch_time_series", fake)
    start = int(all_rows[1_000]["time"])
    df = twelvedata.fetch_range("EUR/USD", "15m", start_ts=start)
    assert len(df) == 11_000 and df["time"].is_unique and df["time"].iloc[0] == start
    assert seen_end[0] is None and len(seen_end) == 3


def test_binance_fetch_range_pages_forwards(monkeypatch: pytest.MonkeyPatch) -> None:
    all_rows = make_candles(2_500, "15m").to_dict("records")

    def fake(symbol: str, interval: str, limit: int, start_ms: int | None = None, end_ms: int | None = None,
             session: Any = None, market: str = "usdm"):
        sel = [r for r in all_rows if r["time"] * 1000 >= (start_ms or 0) and r["time"] * 1000 <= (end_ms or 1e20)]
        return sel[:limit]

    monkeypatch.setattr(binance, "fetch_klines", fake)
    monkeypatch.setattr(binance.time, "sleep", lambda s: None)
    df = binance.fetch_range("BTCUSDT", "15m", start_ts=T0, end_ts=int(all_rows[-1]["time"]))
    assert len(df) == 2_500 and df["time"].is_unique


def test_load_history_caches_closed_candles_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    candles = make_candles(300, "15m")
    last_open = int(candles["time"].iloc[-1])
    now = last_open + 120  # last candle is still forming
    monkeypatch.setattr(history, "fetch_range", lambda s, i, start, end=None: candles)
    df = history.load_history("BTCUSDT", "15m", months=1, now=now, cache_dir=tmp_path)
    assert df["time"].iloc[-1] == last_open - M15
    cached = history.read_cache("BTCUSDT", "15m", cache_dir=tmp_path)
    assert cached["time"].iloc[-1] == last_open - M15  # the forming candle was never cached

    # Offline mode uses only the cache.
    monkeypatch.setattr(history, "fetch_range", lambda *a, **k: pytest.fail("network used offline"))
    off = history.load_history("BTCUSDT", "15m", months=1, now=now, offline=True, cache_dir=tmp_path)
    pd.testing.assert_frame_equal(df, off)


def test_import_csv_round_trip(tmp_path: Any) -> None:
    candles = make_candles(50, "1h")
    csv = tmp_path / "export.csv"
    candles.assign(time=pd.to_datetime(candles["time"], unit="s", utc=True).astype(str)).to_csv(csv, index=False)
    history.import_csv(csv, "EUR/USD", "1h", cache_dir=tmp_path)
    pd.testing.assert_frame_equal(history.read_cache("EUR/USD", "1h", cache_dir=tmp_path), candles)


def test_binance_spot_and_futures_use_their_own_endpoints() -> None:
    kline = [[1_700_000_000_000, "1", "2", "0.5", "1.5", "10"]]
    for market, host in (("spot", "api.binance.com/api/v3"), ("usdm", "fapi.binance.com/fapi/v1")):
        session = FakeSession([kline])
        rows = binance.fetch_klines("BTCUSDT", "15m", limit=5000, session=session, market=market)  # type: ignore[arg-type]
        assert host in session.urls[0] and rows[0]["close"] == 1.5
        assert session.calls[0]["limit"] == binance.MAX_LIMIT[market]  # capped per market
