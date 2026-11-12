"""Migrations: models and migrations agree, round-trip works, candle partitions behave."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pgserver
import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401
from app.db.base import Base
from tests.api.conftest import alembic, make_database

pytestmark = pytest.mark.db
PARTITION = re.compile(r"^candles_\d{4}_\d{2}$")
MARCH_31 = datetime(2026, 3, 31, 23, 45, tzinfo=UTC)
JAN_2031 = datetime(2031, 1, 5, tzinfo=UTC)


def _include(obj: object, name: str | None, type_: str, reflected: bool, compare_to: object) -> bool:
    return not (type_ == "table" and name is not None and PARTITION.match(name))


async def test_migrations_match_models_and_round_trip(pg: pgserver.PostgresServer) -> None:
    url = make_database(pg, "zentrix_migrations")
    await alembic(url, "upgrade", "head")
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            diff = await conn.run_sync(lambda c: compare_metadata(
                MigrationContext.configure(c, opts={"include_object": _include, "compare_type": True}),
                Base.metadata))
            assert diff == [], diff
        await alembic(url, "downgrade", "base")
        async with engine.connect() as conn:
            sql = "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            tables = (await conn.execute(text(sql))).scalar()
            assert tables == 0
        await alembic(url, "upgrade", "head")
    finally:
        await engine.dispose()


async def test_candle_partitions(db_url: str) -> None:
    engine = create_async_engine(db_url)
    insert = text("""INSERT INTO candles (listing_id, timeframe, ts, open, high, low, close)
                     SELECT l.id, :tf, :ts, 1.1, 1.2, 1.0, 1.15
                     FROM instrument_listings l JOIN instruments i ON i.id = l.instrument_id
                     WHERE i.symbol = 'EUR/USD'""")
    try:
        async with engine.begin() as conn:
            await conn.execute(insert, {"tf": "15m", "ts": MARCH_31})
            part = (await conn.execute(text("SELECT tableoid::regclass::text FROM candles"))).scalar()
            assert part == "candles_2026_03"  # UTC month boundary, not local time
        with pytest.raises(DBAPIError, match="no partition"):
            async with engine.begin() as conn:
                await conn.execute(insert, {"tf": "15m", "ts": JAN_2031})
        async with engine.begin() as conn:
            sql = "SELECT zx_ensure_candle_partitions('2031-01-01', '2031-02-01')"
            created = (await conn.execute(text(sql))).scalar()
            assert created == 2
            await conn.execute(insert, {"tf": "15m", "ts": JAN_2031})
        with pytest.raises(IntegrityError):  # unknown timeframe
            async with engine.begin() as conn:
                await conn.execute(insert, {"tf": "7m", "ts": MARCH_31})
        with pytest.raises(IntegrityError):  # duplicate candle
            async with engine.begin() as conn:
                await conn.execute(insert, {"tf": "15m", "ts": MARCH_31})
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM candles"))
        await engine.dispose()
