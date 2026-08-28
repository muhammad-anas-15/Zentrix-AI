"""
Historical Simulation: replays the assistant's full logic (ML + pattern)
against past candles, comparing each signal to what ACTUALLY happened
next. Gives a large-sample accuracy result in minutes instead of
waiting weeks for live signals.

Run: python demo_trading_logger/historical_simulator.py
"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pickle
import pandas as pd

from ml_model.dataset_builder import build_dataset

DB_PATH = os.path.join(os.path.dirname(__file__), "signal_log.db")
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "ml_model", "model_registry")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, interval TEXT, time INTEGER,
            pattern TEXT, rsi REAL, ml_signal TEXT, ml_confidence REAL,
            actual_outcome TEXT, correct INTEGER
        )
    """)
    conn.commit()
    return conn


def load_model(symbol: str, interval: str):
    safe_symbol = symbol.replace("/", "_")
    path = os.path.join(MODEL_DIR, f"{safe_symbol}_{interval}_xgb.pkl")
    with open(path, "rb") as f:
        payload = pickle.load(f)
    return payload["model"], payload["feature_cols"]


def simulate(symbol: str = "BTCUSDT", interval: str = "15m", months: int = 12):
    print(f"Building historical dataset for {symbol} {interval} ({months} months)...")
    df = build_dataset(symbol, interval, months=months).sort_values("time").reset_index(drop=True)

    model, feature_cols = load_model(symbol, interval)
    pattern_cols = [c for c in df.columns if c.startswith("pattern_")]

    conn = init_db()
    correct_count = 0
    total = 0

    for i in range(len(df) - 1):  # -1 so "actual next outcome" always exists
        row = df.iloc[i]
        X = pd.DataFrame([row[feature_cols]])
        pred = model.predict(X)[0]
        proba = model.predict_proba(X)[0]
        ml_signal = "Up" if pred == 1 else "Down"
        ml_confidence = round(max(proba) * 100, 1)

        # recover pattern name from one-hot columns
        pattern = next((c.replace("pattern_", "") for c in pattern_cols if row.get(c) == 1), "Unknown")

        actual_label = df.iloc[i]["label"]  # 1 = next candle up, 0 = down
        actual_outcome = "Up" if actual_label == 1 else "Down"
        correct = 1 if ml_signal == actual_outcome else 0

        conn.execute(
            "INSERT INTO signals (symbol, interval, time, pattern, rsi, ml_signal, "
            "ml_confidence, actual_outcome, correct) VALUES (?,?,?,?,?,?,?,?,?)",
            (symbol, interval, int(row["time"]), pattern, float(row["rsi"]),
             ml_signal, float(ml_confidence), actual_outcome, int(correct))
        )
        correct_count += correct
        total += 1

    conn.commit()
    conn.close()

    accuracy = round(correct_count / total * 100, 2) if total else 0
    print(f"\nSimulation complete: {total} signals tested")
    print(f"Correct: {correct_count} | Accuracy: {accuracy}%")
    print(f"Logged to: {DB_PATH}")
    return {"total": total, "correct": correct_count, "accuracy": accuracy}


if __name__ == "__main__":
    simulate("BTCUSDT", "15m", months=12)