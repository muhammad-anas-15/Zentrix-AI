"""Register trained artifacts (ml/artifacts/*/metadata.json) as model versions for live signals.

Run (from backend/):  python -m app.workers.register_models [--artifacts PATH]
Re-running is safe: already registered versions are skipped. A new training run of the same model becomes the
active version; the previous one stays in the table (its signals keep pointing at it).
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.core.config import get_settings
from app.db.session import make_engine, make_sessionmaker
from app.services.signals.registry import register_artifacts


async def _run(root: Path | None) -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        async with make_sessionmaker(engine)() as db:
            for r in await register_artifacts(db, settings, root):
                print(f"{r.status:22s} {r.key:22s} {r.detail}")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--artifacts", type=Path, default=None)
    asyncio.run(_run(parser.parse_args().artifacts))


if __name__ == "__main__":
    main()
