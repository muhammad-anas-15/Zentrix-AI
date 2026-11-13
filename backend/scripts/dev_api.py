"""Run the API for the app on this machine in one command: local PostgreSQL (pgserver, no Docker), migrations,
developer sign-in, and CORS for the Flutter web build.

Run (from backend/):
    python -m scripts.dev_api                  # http://127.0.0.1:8000, for `flutter run -d chrome --web-port 8090`
    python -m scripts.dev_api --worker         # also run the ingestion worker (fresh candles, signals, calendar)
    python -m scripts.dev_api --host 0.0.0.0   # reachable from a phone on the same Wi-Fi
Stop with Ctrl+C. The database keeps running; stop it with `python -m scripts.dev_db --stop`.

Developer sign-in lets anyone sign in as any email: it is only for this machine. APP_ENV is forced to dev, so the
settings refuse it anywhere else.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def dev_env(database_url: str, web_port: int, extra_origins: Sequence[str] = ()) -> dict[str, str]:
    """Environment for a local API used by the app: dev mode, developer sign-in, CORS for the web build."""
    origins = [f"http://localhost:{web_port}", f"http://127.0.0.1:{web_port}", *extra_origins]
    return {"APP_ENV": "dev", "DEV_LOGIN": "true", "DATABASE_URL": database_url, "CORS_ORIGINS": ",".join(origins)}


def migrate(database_url: str) -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--web-port", type=int, default=8090, help="port of `flutter run -d chrome --web-port`")
    parser.add_argument("--worker", action="store_true", help="also run the ingestion worker")
    args = parser.parse_args(argv)

    from scripts import dev_db

    url = dev_db.start()
    os.environ.update(dev_env(url, args.web_port))
    migrate(url)
    worker = None
    if args.worker:
        worker = subprocess.Popen([sys.executable, "-m", "app.workers.main"], cwd=BACKEND, env=dict(os.environ))

    shown = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    print(f"\nZentrix API (dev, developer sign-in ON): http://{shown}:{args.port}/docs")
    print(f"App: flutter run -d chrome --web-port {args.web_port} "
          f"--dart-define=API_BASE_URL=http://{shown}:{args.port} --dart-define=DEV_LOGIN=true")
    if args.host in ("0.0.0.0", "::"):
        print("WARNING: listening on all interfaces; developer sign-in is reachable from your network.")
    print()

    import uvicorn

    try:
        uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info")
    finally:
        if worker is not None:
            worker.terminate()


if __name__ == "__main__":
    main()
