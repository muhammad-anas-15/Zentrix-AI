"""CLI: print the assistant's signal for the last closed candle.

Run (from backend/):  python -m scripts.check_signal EUR/USD 15m [--llm] [--no-news] [--no-knowledge]
Needs a trained artifact (python -m ml.training.pipeline). Not financial advice.
"""

from __future__ import annotations

import argparse
import json

from app.services.assistant.agent import run_assistant


def main() -> None:
    parser = argparse.ArgumentParser(description="Zentrix signal for the last closed candle")
    parser.add_argument("symbol", help="e.g. EUR/USD, XAU/USD, BTCUSDT")
    parser.add_argument("interval", help="1m, 5m, 15m or 1h")
    parser.add_argument("--llm", action="store_true", help="add a Gemini explanation (needs GEMINI_API_KEY)")
    parser.add_argument("--no-news", action="store_true")
    parser.add_argument("--no-knowledge", action="store_true")
    args = parser.parse_args()
    result = run_assistant(args.symbol, args.interval, use_llm=args.llm, use_news=not args.no_news,
                           use_knowledge=not args.no_knowledge)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
