"""
Trains an XGBoost classifier on the dataset from dataset_builder.py.
Uses CHRONOLOGICAL split (never random shuffle) to avoid lookahead bias.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import pickle
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

from ml_model.dataset_builder import build_dataset

MODEL_DIR = os.path.join(os.path.dirname(__file__), "model_registry")
os.makedirs(MODEL_DIR, exist_ok=True)


def train_model(symbol: str = "BTCUSDT", interval: str = "15m", months: int = None, horizon: int = 1):
    from ml_model.dataset_builder import HISTORY_MONTHS
    months = months or HISTORY_MONTHS
    df = build_dataset(symbol, interval, months=months, horizon=horizon)
    df = df.sort_values("time").reset_index(drop=True)

    EXCLUDE = ("label", "time", "current_price", "resistance", "support")
    feature_cols = [c for c in df.columns if c not in EXCLUDE]
    X = df[feature_cols]
    y = df["label"]

    # Chronological split: 70% train, 15% val, 15% test
    n = len(df)
    train_end = int(n * 0.7)
    val_end = int(n * 0.85)

    X_train, y_train = X.iloc[:train_end], y.iloc[:train_end]
    X_val, y_val = X.iloc[train_end:val_end], y.iloc[train_end:val_end]
    X_test, y_test = X.iloc[val_end:], y.iloc[val_end:]

    model = XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
    )
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    preds = model.predict(X_test)
    metrics = {
        "accuracy": round(accuracy_score(y_test, preds), 4),
        "precision": round(precision_score(y_test, preds, zero_division=0), 4),
        "recall": round(recall_score(y_test, preds, zero_division=0), 4),
        "f1": round(f1_score(y_test, preds, zero_division=0), 4),
    }
    print("Test metrics:", metrics)

    suffix = f"_h{horizon}" if horizon > 1 else ""
    model_path = os.path.join(MODEL_DIR, f"{symbol.replace('/', '_')}_{interval}{suffix}_xgb.pkl")
    with open(model_path, "wb") as f:
        pickle.dump({"model": model, "feature_cols": feature_cols}, f)
    print("Saved model to:", model_path)

    return model, metrics, feature_cols


if __name__ == "__main__":
    train_model("BTCUSDT", "15m")