import sys, os

from app.services.assistant.agent import run_assistant

def get_trading_signal(symbol: str, timeframe: str) -> dict:
    result = run_assistant(symbol, timeframe)
    return result

# CLI se run karne ke liye purana behavior bhi rakh lo:
if __name__ == "__main__":
    result = get_trading_signal(sys.argv[1], sys.argv[2])
    for k, v in result.items():
        print(f"{k}: {v}")