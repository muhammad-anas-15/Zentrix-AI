"""Local PostgreSQL 16 without Docker (bundled by the `pgserver` dev dependency). For development/tests only.

Run (from backend/):
    python -m scripts.dev_db            # start (data in backend/.pgdata), print DATABASE_URL
    python -m scripts.dev_db --stop
Then: set DATABASE_URL to the printed value and run `alembic upgrade head`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pgserver

PGDATA = Path(__file__).resolve().parents[1] / ".pgdata"
DB_NAME = "zentrix"


def asyncpg_url(uri: str, db: str = DB_NAME) -> str:
    base, _, _ = uri.rpartition("/")
    return base.replace("postgresql://", "postgresql+asyncpg://", 1) + f"/{db}"


def start() -> str:
    srv = pgserver.get_server(PGDATA, cleanup_mode=None)  # keep running after this process exits
    exists = srv.psql(f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}';")
    if "1 row" not in exists:
        srv.psql(f"CREATE DATABASE {DB_NAME};")
    return asyncpg_url(srv.get_uri())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    if args.stop:
        pgserver.get_server(PGDATA, cleanup_mode="stop").cleanup()
        print("stopped")
        return
    print(f"DATABASE_URL={start()}")


if __name__ == "__main__":
    main()
