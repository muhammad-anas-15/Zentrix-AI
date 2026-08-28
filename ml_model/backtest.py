"""
Walk-forward validation: retrains on rolling windows and tests on the
next unseen chunk each time — more realistic than a single train/test split.
Also simulates simple trading (with fees) to report Sharpe/drawdown.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score

from ml_model.dataset_builder import build_dataset

FEE_PCT = 0.0004  # 0.04% per trade (typical spot fee)


def walk_forward_backtest(symbol: str = "BTCUSDT", interval: str = "15m",
                           n_folds: int = 5, months: int = None):
    from ml_model.dataset_builder import HISTORY_MONTHS
    months = months or HISTORY_MONTHS
    df = build_dataset(symbol, interval, months=months).sort_values("time").reset_index(drop=True)
    EXCLUDE = ("label", "time", "current_price", "resistance", "support")
    feature_cols = [c for c in df.columns if c not in EXCLUDE]

    fold_size = len(df) // (n_folds + 1)
    accuracies = []
    all_returns = []

    for fold in range(n_folds):
        train_end = fold_size * (fold + 1)
        test_end = train_end + fold_size

        train = df.iloc[:train_end]
        test = df.iloc[train_end:test_end]
        if len(test) == 0:
            continue

        model = XGBClassifier(n_estimators=150, max_depth=4, learning_rate=0.05,
                               eval_metric="logloss")
        model.fit(train[feature_cols], train["label"])
        preds = model.predict(test[feature_cols])

        acc = accuracy_score(test["label"], preds)
        accuracies.append(acc)

        # simple strategy: go long if pred=1, flat if pred=0; subtract fee per trade
        price_change_pct = test["current_price"].pct_change().fillna(0).values
        strat_returns = np.where(preds == 1, price_change_pct - FEE_PCT, 0)
        all_returns.extend(strat_returns)

        print(f"Fold {fold+1}: accuracy={acc:.4f}, trades={sum(preds)}")

    returns = np.array(all_returns)
    sharpe = (returns.mean() / (returns.std() + 1e-9)) * np.sqrt(252 * 24 * 4)
    cum_returns = np.cumsum(returns)
    max_drawdown = np.min(cum_returns - np.maximum.accumulate(cum_returns))

    print("\n--- Walk-Forward Summary ---")
    print("Avg accuracy:", round(np.mean(accuracies), 4))
    print("Sharpe ratio (approx):", round(sharpe, 3))
    print("Max drawdown:", round(max_drawdown, 5))

    return {
        "avg_accuracy": round(np.mean(accuracies), 4),
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(max_drawdown, 5),
    }


if __name__ == "__main__":
    walk_forward_backtest("BTCUSDT", "15m", n_folds=5)