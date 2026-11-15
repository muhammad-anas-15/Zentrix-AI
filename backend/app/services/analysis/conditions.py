"""Market-condition light: a rule-based checklist of current conditions (it does not predict direction).

Inputs, each reported with its value and why it mattered:
- market open (session calendar) and data freshness;
- trend vs range: ADX(14) >= 25 trending, <= 20 ranging, direction from +DI/-DI;
- volatility regime: percentile of ATR(14)/price over the last 500 closed candles
  (< 20 low, > 80 high, > 95 extreme);
- trading session and liquidity (FX centres in local time, with daylight saving);
- the news guard.
Red: market closed, stale data, news blackout or extreme volatility. Amber: high volatility, news caution or
unknown, low-liquidity hours. Green otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.services.news.guard import GuardResult
from ml.data.candles import interval_seconds
from ml.data.sessions import ALWAYS_OPEN, is_market_open
from ml.features.indicators import adx, atr

FX_CENTRES = (  # (name, timezone, local open, local close)
    ("Sydney", "Australia/Sydney", time(7), time(16)),
    ("Tokyo", "Asia/Tokyo", time(9), time(18)),
    ("London", "Europe/London", time(8), time(17)),
    ("New York", "America/New_York", time(8), time(17)),
)
NY = ZoneInfo("America/New_York")
VOL_WINDOW = 500
METHOD = ("Rule-based checklist: market hours, data freshness, ADX(14) trend/range, ATR(14)/price percentile "
          "over the last 500 candles, trading session liquidity and the news guard. It describes conditions; it "
          "does not predict direction.")


@dataclass
class Factor:
    name: str
    status: str  # ok | info | caution | danger | unknown
    value: Any
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "value": self.value, "detail": self.detail}


@dataclass
class Conditions:
    light: str  # green | amber | red | unknown
    factors: list[Factor] = field(default_factory=list)
    trend: dict[str, Any] = field(default_factory=dict)
    volatility: dict[str, Any] = field(default_factory=dict)
    sessions: list[str] = field(default_factory=list)
    last_candle_close: datetime | None = None


def active_centres(now: datetime) -> list[str]:
    out = []
    for name, tz, start, end in FX_CENTRES:
        local = now.astimezone(ZoneInfo(tz))
        if local.weekday() < 5 and start <= local.time() < end:
            out.append(name)
    return out


def liquidity_note(now: datetime, session: str) -> tuple[str, str]:
    """(status, detail) for trading-session liquidity."""
    if session in ALWAYS_OPEN:
        if now.weekday() >= 5:
            return "info", "weekend: crypto trades, but volume is usually lower"
        return "ok", "24/7 market"
    ny = now.astimezone(NY)
    centres = active_centres(now)
    if time(16, 30) <= ny.time() < time(17, 30):
        return "caution", "daily rollover (around 17:00 New York): spreads usually widen"
    if ny.weekday() == 4 and ny.time() >= time(15):
        return "caution", "last hours before the weekend close: thin liquidity, weekend gap risk"
    if "London" in centres and "New York" in centres:
        return "ok", "London / New York overlap: usually the most liquid hours"
    if centres in (["Sydney"], []):
        return "caution", "only Sydney (or no major centre) open: thin liquidity"
    return "ok", f"{' / '.join(centres)} session"


def trend_state(candles: pd.DataFrame) -> dict[str, Any]:
    a, plus, minus = adx(candles["high"], candles["low"], candles["close"])
    value = float(a.iloc[-1]) if np.isfinite(a.iloc[-1]) else None
    if value is None:
        return {"regime": "unknown", "adx": None, "direction": None}
    direction = "up" if plus.iloc[-1] >= minus.iloc[-1] else "down"
    regime = "trending" if value >= 25 else "ranging" if value <= 20 else "weak trend"
    return {"regime": regime, "adx": round(value, 1), "direction": direction if regime != "ranging" else None}


def volatility_state(candles: pd.DataFrame) -> dict[str, Any]:
    atr_pct = (atr(candles["high"], candles["low"], candles["close"]) / candles["close"] * 100).dropna()
    if len(atr_pct) < 50:
        return {"regime": "unknown", "atr_pct": None, "percentile": None, "window": len(atr_pct)}
    window = atr_pct.iloc[-VOL_WINDOW:]
    current = float(window.iloc[-1])
    pct = float((window < current).mean() * 100)
    regime = "extreme" if pct > 95 else "high" if pct > 80 else "low" if pct < 20 else "normal"
    return {"regime": regime, "atr_pct": round(current, 4), "percentile": round(pct, 1), "window": len(window)}


def assess(candles: pd.DataFrame, timeframe: str, session: str, now: datetime, guard: GuardResult) -> Conditions:
    tf_s = interval_seconds(timeframe)
    last_open = int(candles["time"].iloc[-1])
    last_close = datetime.fromtimestamp(last_open + tf_s, tz=UTC)
    c = Conditions("green", last_candle_close=last_close, sessions=active_centres(now))
    now_ts = now.timestamp()

    open_now = is_market_open(int(now_ts), session)
    c.factors.append(Factor("market", "ok" if open_now else "danger", "open" if open_now else "closed",
                            "market open" if open_now else "market closed: no tradeable prices"))
    age = now_ts - last_close.timestamp()
    # a candle is expected within one timeframe (+5 min for slow feeds) of the previous close while open
    stale = open_now and age > tf_s + 300
    c.factors.append(Factor("data", "danger" if stale else "ok", {"age_s": int(age)},
                            f"latest closed {timeframe} candle is {int(age // 60)} min old"
                            + (": data feed delayed, conditions unknown" if stale else "")))

    c.trend = trend_state(candles)
    t = c.trend
    detail = {"trending": f"trending {t['direction']} (ADX {t['adx']})", "ranging": f"ranging (ADX {t['adx']})",
              "weak trend": f"weak trend {t['direction']} (ADX {t['adx']})"}.get(t["regime"], "not enough data")
    c.factors.append(Factor("trend", "info", t["regime"], detail))

    c.volatility = volatility_state(candles)
    v = c.volatility
    vol_status = {"extreme": "danger", "high": "caution", "unknown": "unknown"}.get(v["regime"], "ok")
    c.factors.append(Factor("volatility", vol_status, v["regime"],
                            f"ATR is {v['atr_pct']}% of price, higher than {v['percentile']}% of the last "
                            f"{v['window']} candles" if v["percentile"] is not None else "not enough data"))

    liq_status, liq_detail = liquidity_note(now, session)
    c.factors.append(Factor("session", liq_status, c.sessions, liq_detail))

    news_status = {"blackout": "danger", "caution": "caution", "unknown": "caution"}.get(guard.state, "ok")
    c.factors.append(Factor("news", news_status, guard.state, "; ".join(guard.reasons)))

    statuses = {f.status for f in c.factors}
    c.light = "red" if "danger" in statuses else "amber" if statuses & {"caution", "unknown"} else "green"
    return c
