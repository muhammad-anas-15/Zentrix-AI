"""Ingestion targets, model versions, signals and outcomes (live track record); default targets.

Default targets respect the Twelve Data free plan (8 req/min, 800/day): 6 instruments x (15m, 1h) is about
720 calls per weekday. Binance public data has no such budget: 20 listings x (15m, 1h, 4h).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-12 20:10:24.611909
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TWELVE_DATA_LIVE = "EUR/USD,GBP/USD,USD/JPY,XAU/USD,AUD/USD,USD/CAD"
DEFAULT_TARGETS = [  # (venue, timeframe, priority, comma-separated symbols or '' for all active listings)
    ("twelvedata", "15m", 10, TWELVE_DATA_LIVE),
    ("twelvedata", "1h", 20, TWELVE_DATA_LIVE),
    ("binance_usdm", "15m", 30, ""), ("binance_usdm", "1h", 40, ""), ("binance_usdm", "4h", 50, ""),
    ("binance_spot", "15m", 30, ""), ("binance_spot", "1h", 40, ""), ("binance_spot", "4h", 50, ""),
]


def upgrade() -> None:
    op.create_table('ingestion_targets',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('listing_id', sa.Integer(), nullable=False),
    sa.Column('timeframe', sa.String(length=8), nullable=False),
    sa.Column('enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('priority', sa.SmallInteger(), server_default='100', nullable=False),
    sa.Column('reason', sa.String(length=16), nullable=False),
    sa.Column('backfill_candles', sa.Integer(), server_default='700', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("reason IN ('model', 'htf', 'chart', 'manual')", name=op.f('ck_ingestion_targets_reason')),
    sa.ForeignKeyConstraint(['listing_id'], ['instrument_listings.id'], name=op.f('fk_ingestion_targets_listing_id_instrument_listings'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['timeframe'], ['timeframes.code'], name=op.f('fk_ingestion_targets_timeframe_timeframes')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ingestion_targets')),
    sa.UniqueConstraint('listing_id', 'timeframe', name='uq_ingestion_targets_listing_timeframe')
    )
    op.create_index(op.f('ix_ingestion_targets_listing_id'), 'ingestion_targets', ['listing_id'], unique=False)
    op.create_table('model_versions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('listing_id', sa.Integer(), nullable=False),
    sa.Column('timeframe', sa.String(length=8), nullable=False),
    sa.Column('horizon', sa.SmallInteger(), nullable=False),
    sa.Column('htf_timeframe', sa.String(length=8), nullable=True),
    sa.Column('label_mode', sa.String(length=16), nullable=False),
    sa.Column('trained_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('git_commit', sa.String(length=40), nullable=True),
    sa.Column('walk_forward_run_id', sa.String(length=64), nullable=True),
    sa.Column('usable', sa.Boolean(), nullable=False),
    sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('calibration', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('strength', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('usability', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('registered_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("label_mode IN ('open_to_open', 'close_to_close')", name=op.f('ck_model_versions_label_mode')),
    sa.ForeignKeyConstraint(['htf_timeframe'], ['timeframes.code'], name=op.f('fk_model_versions_htf_timeframe_timeframes')),
    sa.ForeignKeyConstraint(['listing_id'], ['instrument_listings.id'], name=op.f('fk_model_versions_listing_id_instrument_listings'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['timeframe'], ['timeframes.code'], name=op.f('fk_model_versions_timeframe_timeframes')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_model_versions')),
    sa.UniqueConstraint('key', 'trained_at', name='uq_model_versions_key_trained_at')
    )
    op.create_index(op.f('ix_model_versions_listing_id'), 'model_versions', ['listing_id'], unique=False)
    op.create_index('uq_model_versions_active_series', 'model_versions', ['listing_id', 'timeframe', 'horizon'], unique=True, postgresql_where=sa.text('active'))
    op.create_table('signals',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('model_version_id', sa.Integer(), nullable=False),
    sa.Column('listing_id', sa.Integer(), nullable=False),
    sa.Column('instrument_id', sa.Integer(), nullable=False),
    sa.Column('timeframe', sa.String(length=8), nullable=False),
    sa.Column('horizon', sa.SmallInteger(), nullable=False),
    sa.Column('candle_ts', sa.DateTime(timezone=True), nullable=False),
    sa.Column('decision_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('direction', sa.String(length=4), nullable=False),
    sa.Column('p_up_raw', sa.Double(), nullable=False),
    sa.Column('p_up', sa.Double(), nullable=False),
    sa.Column('confidence', sa.Double(), nullable=False),
    sa.Column('strength', sa.String(length=24), nullable=False),
    sa.Column('model_usable', sa.Boolean(), nullable=False),
    sa.Column('features', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.CheckConstraint("direction IN ('up', 'down')", name=op.f('ck_signals_direction')),
    sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], name=op.f('fk_signals_instrument_id_instruments'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['listing_id'], ['instrument_listings.id'], name=op.f('fk_signals_listing_id_instrument_listings'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['model_version_id'], ['model_versions.id'], name=op.f('fk_signals_model_version_id_model_versions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['timeframe'], ['timeframes.code'], name=op.f('fk_signals_timeframe_timeframes')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_signals')),
    sa.UniqueConstraint('model_version_id', 'candle_ts', name='uq_signals_model_version_candle')
    )
    op.create_index('ix_signals_created_at', 'signals', ['created_at'], unique=False)
    op.create_index('ix_signals_instrument_candle_ts', 'signals', ['instrument_id', 'candle_ts'], unique=False)
    op.create_index('ix_signals_series_candle_ts', 'signals', ['listing_id', 'timeframe', 'horizon', 'candle_ts'], unique=False)
    op.create_table('signal_outcomes',
    sa.Column('signal_id', sa.BigInteger(), nullable=False),
    sa.Column('outcome', sa.String(length=8), nullable=False),
    sa.Column('entry_ts', sa.DateTime(timezone=True), nullable=True),
    sa.Column('entry_price', sa.Double(), nullable=True),
    sa.Column('exit_ts', sa.DateTime(timezone=True), nullable=True),
    sa.Column('exit_price', sa.Double(), nullable=True),
    sa.Column('move', sa.Double(), nullable=True),
    sa.Column('move_pct', sa.Double(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.CheckConstraint("outcome IN ('win', 'loss', 'flat', 'void')", name=op.f('ck_signal_outcomes_outcome')),
    sa.ForeignKeyConstraint(['signal_id'], ['signals.id'], name=op.f('fk_signal_outcomes_signal_id_signals'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('signal_id', name=op.f('pk_signal_outcomes'))
    )
    op.create_index(op.f('ix_signal_outcomes_resolved_at'), 'signal_outcomes', ['resolved_at'], unique=False)

    op.get_bind().execute(
        sa.text("""INSERT INTO ingestion_targets (listing_id, timeframe, reason, priority)
                   SELECT l.id, :tf, 'chart', :priority FROM instrument_listings l JOIN venues v ON v.id = l.venue_id
                   JOIN instruments i ON i.id = l.instrument_id
                   WHERE v.code = :venue AND l.status = 'active' AND (:symbols = '' OR i.symbol = ANY(string_to_array(:symbols, ',')))
                   ON CONFLICT DO NOTHING"""),
        [{"venue": venue, "tf": tf, "priority": prio, "symbols": symbols} for venue, tf, prio, symbols in DEFAULT_TARGETS])


def downgrade() -> None:
    op.drop_index(op.f('ix_signal_outcomes_resolved_at'), table_name='signal_outcomes')
    op.drop_table('signal_outcomes')
    op.drop_index('ix_signals_series_candle_ts', table_name='signals')
    op.drop_index('ix_signals_instrument_candle_ts', table_name='signals')
    op.drop_index('ix_signals_created_at', table_name='signals')
    op.drop_table('signals')
    op.drop_index('uq_model_versions_active_series', table_name='model_versions', postgresql_where=sa.text('active'))
    op.drop_index(op.f('ix_model_versions_listing_id'), table_name='model_versions')
    op.drop_table('model_versions')
    op.drop_index(op.f('ix_ingestion_targets_listing_id'), table_name='ingestion_targets')
    op.drop_table('ingestion_targets')
