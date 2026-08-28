"""
Quick-run helper: prints assistant output in clean, readable format
for any symbol/interval, instead of a raw dict.

Usage: python check_signal.py XAU/USD 15m
"""
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from orchestrator.agent import run_assistant

if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    interval = sys.argv[2] if len(sys.argv) > 2 else "15m"

    result = run_assistant(symbol, interval, use_llm=False)
    for k, v in result.items():
        print(f"{k}: {v}")