"""Every chart timeframe: crypto 5m and 1d from Binance; FX/gold 4h built from 1h, 1d from Twelve Data.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-16 12:00:00.000000

Twelve Data budget (free plan, 800 calls/day): 1d for the 20 active FX/gold listings adds ~20 calls/day; those
targets get priority 900 so the worker fetches them after the signal series of a tick. 5m FX/gold is not added:
~1,700 calls/day does not fit the free plan.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FETCHED = [  # (venue, timeframe, priority, backfill)
    ("binance_spot", "5m", 60, 1000), ("binance_spot", "1d", 70, 1000),
    ("binance_usdm", "5m", 60, 1000), ("binance_usdm", "1d", 70, 1000),
    ("twelvedata", "1d", 900, 700),
]


def upgrade() -> None:
    op.add_column('ingestion_targets', sa.Column('derive_from', sa.String(length=8), nullable=True))
    op.create_foreign_key(op.f('fk_ingestion_targets_derive_from_timeframes'), 'ingestion_targets', 'timeframes',
                          ['derive_from'], ['code'])
    bind = op.get_bind()
    bind.execute(
        sa.text("""INSERT INTO ingestion_targets (listing_id, timeframe, reason, priority, backfill_candles)
                   SELECT l.id, :tf, 'chart', :priority, :backfill FROM instrument_listings l
                   JOIN venues v ON v.id = l.venue_id
                   WHERE v.code = :venue AND l.status = 'active' AND l.is_primary
                   ON CONFLICT DO NOTHING"""),
        [{"venue": v, "tf": tf, "priority": p, "backfill": b} for v, tf, p, b in FETCHED])
    # FX/gold 4h from the 1h series that is already ingested (no API calls)
    bind.execute(sa.text("""
        INSERT INTO ingestion_targets (listing_id, timeframe, reason, priority, derive_from)
        SELECT t.listing_id, '4h', 'chart', 55, '1h' FROM ingestion_targets t
        JOIN instrument_listings l ON l.id = t.listing_id JOIN venues v ON v.id = l.venue_id
        WHERE v.code = 'twelvedata' AND t.timeframe = '1h'
        ON CONFLICT DO NOTHING"""))


def downgrade() -> None:
    op.execute("DELETE FROM ingestion_targets WHERE derive_from IS NOT NULL")
    op.execute("""DELETE FROM ingestion_targets t USING instrument_listings l, venues v
                  WHERE l.id = t.listing_id AND v.id = l.venue_id AND t.reason = 'chart'
                  AND ((v.code IN ('binance_spot', 'binance_usdm') AND t.timeframe IN ('5m', '1d'))
                       OR (v.code = 'twelvedata' AND t.timeframe = '1d'))""")
    op.drop_constraint(op.f('fk_ingestion_targets_derive_from_timeframes'), 'ingestion_targets', type_='foreignkey')
    op.drop_column('ingestion_targets', 'derive_from')
