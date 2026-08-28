"""
Reads signal_log.db and produces a clean, client-facing summary:
overall accuracy, pattern-wise breakdown, confidence-level breakdown.

Run: python demo_trading_logger/accuracy_report.py
"""
import sqlite3
import os
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), "signal_log.db")


def generate_report():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM signals", conn)
    conn.close()

    if df.empty:
        print("No signals logged yet — run historical_simulator.py first.")
        return

    print("=" * 50)
    print(f"TOTAL SIGNALS TESTED: {len(df)}")
    overall_acc = round(df["correct"].mean() * 100, 2)
    print(f"OVERALL ACCURACY: {overall_acc}%")
    print("=" * 50)

    print("\n--- Accuracy by Pattern ---")
    pattern_stats = df.groupby("pattern").agg(
        count=("correct", "size"), accuracy=("correct", "mean")
    ).sort_values("count", ascending=False)
    pattern_stats["accuracy"] = (pattern_stats["accuracy"] * 100).round(2)
    print(pattern_stats)

    df["ml_confidence"] = pd.to_numeric(df["ml_confidence"], errors="coerce")

    print("\n--- Accuracy by ML Confidence Band ---")
    print(f"(confidence range in data: {df['ml_confidence'].min()} to {df['ml_confidence'].max()})")
    df["confidence_band"] = pd.cut(
        df["ml_confidence"], bins=[0, 55, 60, 65, 70, 100],
        labels=["50-55%", "55-60%", "60-65%", "65-70%", "70%+"]
    )
    conf_stats = df.groupby("confidence_band", observed=True).agg(
        count=("correct", "size"), accuracy=("correct", "mean")
    )
    conf_stats["accuracy"] = (conf_stats["accuracy"] * 100).round(2)
    print(conf_stats)

    return {
        "total_signals": len(df),
        "overall_accuracy": overall_acc,
        "pattern_breakdown": pattern_stats.to_dict(),
        "confidence_breakdown": conf_stats.to_dict(),
    }


if __name__ == "__main__":
    generate_report()