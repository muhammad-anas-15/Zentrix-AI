"""Trader tools: economic calendar, risk profiles, journal, watchlists, alerts and alert events (inbox/outbox).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-13 00:57:27.176321
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('news_events',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('external_id', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('currency', sa.String(length=8), nullable=False),
    sa.Column('impact', sa.String(length=8), nullable=False),
    sa.Column('event_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('forecast', sa.String(length=32), nullable=True),
    sa.Column('previous', sa.String(length=32), nullable=True),
    sa.Column('actual', sa.String(length=32), nullable=True),
    sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("impact IN ('high', 'medium', 'low', 'holiday', 'none')", name=op.f('ck_news_events_impact')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_news_events')),
    sa.UniqueConstraint('source', 'external_id', name='uq_news_events_source_external_id')
    )
    op.create_index('ix_news_events_currency_event_at', 'news_events', ['currency', 'event_at'], unique=False)
    op.create_index(op.f('ix_news_events_event_at'), 'news_events', ['event_at'], unique=False)
    op.create_table('risk_profiles',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('account_currency', sa.String(length=8), server_default='USD', nullable=False),
    sa.Column('balance', sa.Double(), nullable=True),
    sa.Column('risk_per_trade_pct', sa.Double(), server_default='1', nullable=False),
    sa.Column('max_daily_loss_pct', sa.Double(), server_default='3', nullable=False),
    sa.Column('max_trades_per_day', sa.SmallInteger(), server_default='6', nullable=False),
    sa.Column('max_consecutive_losses', sa.SmallInteger(), server_default='3', nullable=False),
    sa.Column('leverage', sa.Double(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('max_daily_loss_pct > 0 AND max_daily_loss_pct <= 100', name=op.f('ck_risk_profiles_max_daily_loss_pct')),
    sa.CheckConstraint('risk_per_trade_pct > 0 AND risk_per_trade_pct <= 100', name=op.f('ck_risk_profiles_risk_per_trade_pct')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_risk_profiles_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', name=op.f('pk_risk_profiles'))
    )
    op.create_table('watchlists',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_watchlists_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_watchlists')),
    sa.UniqueConstraint('user_id', 'name', name='uq_watchlists_user_name')
    )
    op.create_index(op.f('ix_watchlists_user_id'), 'watchlists', ['user_id'], unique=False)
    op.create_table('alerts',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('instrument_id', sa.Integer(), nullable=True),
    sa.Column('watchlist_id', sa.BigInteger(), nullable=True),
    sa.Column('timeframe', sa.String(length=8), nullable=True),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('recurring', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('cooldown_s', sa.Integer(), server_default='0', nullable=False),
    sa.Column('note', sa.String(length=120), nullable=True),
    sa.Column('last_triggered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('trigger_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('price_cross', 'pct_move', 'signal', 'news')", name=op.f('ck_alerts_kind')),
    sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], name=op.f('fk_alerts_instrument_id_instruments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['timeframe'], ['timeframes.code'], name=op.f('fk_alerts_timeframe_timeframes')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_alerts_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['watchlist_id'], ['watchlists.id'], name=op.f('fk_alerts_watchlist_id_watchlists'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_alerts'))
    )
    op.create_index('ix_alerts_active_kind', 'alerts', ['kind'], unique=False, postgresql_where=sa.text('active'))
    op.create_index('ix_alerts_instrument_id', 'alerts', ['instrument_id'], unique=False, postgresql_where=sa.text('active'))
    op.create_index(op.f('ix_alerts_user_id'), 'alerts', ['user_id'], unique=False)
    op.create_table('watchlist_items',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('watchlist_id', sa.BigInteger(), nullable=False),
    sa.Column('instrument_id', sa.Integer(), nullable=False),
    sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], name=op.f('fk_watchlist_items_instrument_id_instruments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['watchlist_id'], ['watchlists.id'], name=op.f('fk_watchlist_items_watchlist_id_watchlists'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_watchlist_items')),
    sa.UniqueConstraint('watchlist_id', 'instrument_id', name='uq_watchlist_items_list_instrument')
    )
    op.create_index(op.f('ix_watchlist_items_instrument_id'), 'watchlist_items', ['instrument_id'], unique=False)
    op.create_index(op.f('ix_watchlist_items_watchlist_id'), 'watchlist_items', ['watchlist_id'], unique=False)
    op.create_table('alert_events',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('alert_id', sa.BigInteger(), nullable=True),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('dedupe_key', sa.String(length=120), nullable=False),
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('triggered_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('delivery', sa.String(length=16), server_default='pending', nullable=False),
    sa.Column('attempts', sa.SmallInteger(), server_default='0', nullable=False),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("delivery IN ('pending', 'sent', 'partial', 'failed', 'no_devices', 'disabled')", name=op.f('ck_alert_events_delivery')),
    sa.ForeignKeyConstraint(['alert_id'], ['alerts.id'], name=op.f('fk_alert_events_alert_id_alerts'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_alert_events_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_alert_events')),
    sa.UniqueConstraint('alert_id', 'dedupe_key', name='uq_alert_events_alert_dedupe')
    )
    op.create_index('ix_alert_events_undelivered', 'alert_events', ['id'], unique=False, postgresql_where=sa.text("delivery IN ('pending', 'failed')"))
    op.create_index('ix_alert_events_user_id_id', 'alert_events', ['user_id', 'id'], unique=False)
    op.create_table('journal_entries',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('instrument_id', sa.Integer(), nullable=False),
    sa.Column('timeframe', sa.String(length=8), nullable=True),
    sa.Column('side', sa.String(length=8), nullable=False),
    sa.Column('quantity', sa.Double(), nullable=False),
    sa.Column('entry_price', sa.Double(), nullable=False),
    sa.Column('entry_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('exit_price', sa.Double(), nullable=True),
    sa.Column('exit_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('stop_loss', sa.Double(), nullable=True),
    sa.Column('take_profit', sa.Double(), nullable=True),
    sa.Column('fees', sa.Double(), server_default='0', nullable=False),
    sa.Column('account_currency', sa.String(length=8), nullable=False),
    sa.Column('fx_rate', sa.Double(), nullable=True),
    sa.Column('risk_account', sa.Double(), nullable=True),
    sa.Column('pnl_quote', sa.Double(), nullable=True),
    sa.Column('pnl_account', sa.Double(), nullable=True),
    sa.Column('r_multiple', sa.Double(), nullable=True),
    sa.Column('signal_id', sa.BigInteger(), nullable=True),
    sa.Column('setup', sa.String(length=64), nullable=True),
    sa.Column('tags', postgresql.ARRAY(sa.String(length=32)), server_default='{}', nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("side IN ('long', 'short')", name=op.f('ck_journal_entries_side')),
    sa.CheckConstraint('(exit_price IS NULL) = (exit_at IS NULL)', name=op.f('ck_journal_entries_exit_complete')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_journal_entries_quantity')),
    sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], name=op.f('fk_journal_entries_instrument_id_instruments'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['signal_id'], ['signals.id'], name=op.f('fk_journal_entries_signal_id_signals'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['timeframe'], ['timeframes.code'], name=op.f('fk_journal_entries_timeframe_timeframes')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_journal_entries_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_journal_entries'))
    )
    op.create_index('ix_journal_entries_user_entry_at', 'journal_entries', ['user_id', 'entry_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_journal_entries_user_entry_at', table_name='journal_entries')
    op.drop_table('journal_entries')
    op.drop_index('ix_alert_events_user_id_id', table_name='alert_events')
    op.drop_index('ix_alert_events_undelivered', table_name='alert_events', postgresql_where=sa.text("delivery IN ('pending', 'failed')"))
    op.drop_table('alert_events')
    op.drop_index(op.f('ix_watchlist_items_watchlist_id'), table_name='watchlist_items')
    op.drop_index(op.f('ix_watchlist_items_instrument_id'), table_name='watchlist_items')
    op.drop_table('watchlist_items')
    op.drop_index(op.f('ix_alerts_user_id'), table_name='alerts')
    op.drop_index('ix_alerts_instrument_id', table_name='alerts', postgresql_where=sa.text('active'))
    op.drop_index('ix_alerts_active_kind', table_name='alerts', postgresql_where=sa.text('active'))
    op.drop_table('alerts')
    op.drop_index(op.f('ix_watchlists_user_id'), table_name='watchlists')
    op.drop_table('watchlists')
    op.drop_table('risk_profiles')
    op.drop_index(op.f('ix_news_events_event_at'), table_name='news_events')
    op.drop_index('ix_news_events_currency_event_at', table_name='news_events')
    op.drop_table('news_events')
