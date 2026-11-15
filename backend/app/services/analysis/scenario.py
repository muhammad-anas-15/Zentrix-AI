"""Scenario path: where price may be 1-5 candles ahead, with the band's measured reliability.

Band = 10th / 50th / 90th percentile of past k-candle close-to-close log moves (last ``window`` candles),
applied to the latest close. Coverage is measured out of sample: for each of the most recent ``test`` cases,
the band is rebuilt from moves known before that case and checked against what happened. A nominal 80% band
that covered, say, 74% is reported as 74%. Direction probabilities come only from registered models, each shown
with its live track record and whether it has a demonstrated edge.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ml.calibration.strength import wilson_interval

QUANTILES = (0.1, 0.5, 0.9)
METHOD = ("Price band: 10th-90th percentile of past k-candle moves from the stored history, applied to the "
          "latest close. 'coverage' = how often such a band (built only from earlier data) contained the actual "
          "price over the most recent test cases. Direction: only from registered models, with their live track "
          "record; models without a demonstrated edge are marked unreliable (treat as 50/50).")


def bands(candles: pd.DataFrame, steps: int = 5, window: int = 1000, test: int = 250) -> list[dict[str, Any]]:
    close = candles["close"].to_numpy(float)
    logp = np.log(close)
    n = len(close)
    out = []
    for k in range(1, steps + 1):
        moves = logp[k:] - logp[:-k]  # moves[i] = log(close[i+k] / close[i])
        recent = moves[-window:]
        q = np.quantile(recent, QUANTILES) if len(recent) >= 50 else None
        hits = tested = 0
        # case j: start at close[j] (j + k < n); band from moves whose end index i + k <= j
        for j in range(max(0, n - k - test), n - k):
            known = moves[max(0, j - k - window + 1): j - k + 1]
            if len(known) < 200:
                continue
            lo, hi = np.quantile(known, (QUANTILES[0], QUANTILES[-1]))
            hits += int(lo <= moves[j] <= hi)
            tested += 1
        cov = hits / tested if tested else None
        ci = wilson_interval(hits, tested) if tested else None
        out.append({
            "k": k,
            "low": float(close[-1] * np.exp(q[0])) if q is not None else None,
            "median": float(close[-1] * np.exp(q[1])) if q is not None else None,
            "high": float(close[-1] * np.exp(q[2])) if q is not None else None,
            "nominal_coverage": QUANTILES[-1] - QUANTILES[0],
            "coverage": cov, "coverage_ci95": list(ci) if ci else None, "coverage_tested": tested,
            "history": int(len(recent)),
        })
    return out
