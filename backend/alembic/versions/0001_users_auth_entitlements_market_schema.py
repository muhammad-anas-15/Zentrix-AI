"""Users, auth, entitlements, audit log; market reference tables and partitioned candles.

Revision ID: 0001
Revises: (none)
Create Date: 2026-11-12 19:39:35.519903
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('instruments',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('symbol', sa.String(length=40), nullable=False),
    sa.Column('display_name', sa.String(length=80), nullable=False),
    sa.Column('asset_class', sa.String(length=16), nullable=False),
    sa.Column('instrument_type', sa.String(length=16), nullable=False),
    sa.Column('base', sa.String(length=16), nullable=False),
    sa.Column('quote', sa.String(length=16), nullable=False),
    sa.Column('settle', sa.String(length=16), nullable=True),
    sa.Column('expiry', sa.Date(), nullable=True),
    sa.Column('contract_size', sa.Double(), nullable=True),
    sa.Column('price_decimals', sa.SmallInteger(), nullable=False),
    sa.Column('session', sa.String(length=32), nullable=False),
    sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.CheckConstraint("asset_class IN ('fx', 'metal', 'commodity', 'crypto', 'index', 'equity')", name=op.f('ck_instruments_asset_class')),
    sa.CheckConstraint("instrument_type IN ('spot', 'perpetual', 'future', 'cfd')", name=op.f('ck_instruments_instrument_type')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_instruments')),
    sa.UniqueConstraint('symbol', name=op.f('uq_instruments_symbol'))
    )
    op.create_index('ix_instruments_asset_class_active', 'instruments', ['asset_class', 'active'], unique=False)
    op.create_table('timeframes',
    sa.Column('code', sa.String(length=8), nullable=False),
    sa.Column('seconds', sa.Integer(), nullable=False),
    sa.Column('sort_order', sa.SmallInteger(), nullable=False),
    sa.PrimaryKeyConstraint('code', name=op.f('pk_timeframes'))
    )
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('display_name', sa.String(length=120), nullable=True),
    sa.Column('avatar_url', sa.Text(), nullable=True),
    sa.Column('plan', sa.String(length=16), server_default='free', nullable=False),
    sa.Column('locale', sa.String(length=8), server_default='en', nullable=False),
    sa.Column('timezone', sa.String(length=64), server_default='UTC', nullable=False),
    sa.Column('tokens_valid_after', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("locale IN ('en', 'ur')", name=op.f('ck_users_locale')),
    sa.CheckConstraint("plan IN ('free', 'premium')", name=op.f('ck_users_plan')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index('ix_users_email_lower', 'users', [sa.literal_column('lower(email)')], unique=False)
    op.create_table('venues',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.CheckConstraint("kind IN ('exchange', 'data_vendor', 'broker')", name=op.f('ck_venues_kind')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_venues')),
    sa.UniqueConstraint('code', name=op.f('uq_venues_code'))
    )
    op.create_table('audit_log',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('event', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('subject_hash', sa.String(length=64), nullable=True),
    sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_audit_log_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_log'))
    )
    op.create_index(op.f('ix_audit_log_at'), 'audit_log', ['at'], unique=False)
    op.create_index(op.f('ix_audit_log_event'), 'audit_log', ['event'], unique=False)
    op.create_index(op.f('ix_audit_log_user_id'), 'audit_log', ['user_id'], unique=False)
    op.create_table('auth_identities',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('subject', sa.String(length=255), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_auth_identities_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_auth_identities')),
    sa.UniqueConstraint('provider', 'subject', name='uq_auth_identities_provider_subject')
    )
    op.create_index(op.f('ix_auth_identities_user_id'), 'auth_identities', ['user_id'], unique=False)
    op.create_table('devices',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('fcm_token', sa.Text(), nullable=False),
    sa.Column('platform', sa.String(length=16), nullable=False),
    sa.Column('app_version', sa.String(length=32), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("platform IN ('android', 'ios', 'web')", name=op.f('ck_devices_platform')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_devices_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_devices')),
    sa.UniqueConstraint('fcm_token', name=op.f('uq_devices_fcm_token'))
    )
    op.create_index(op.f('ix_devices_user_id'), 'devices', ['user_id'], unique=False)
    op.create_table('entitlements',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("source IN ('plan', 'subscription', 'admin', 'promo')", name=op.f('ck_entitlements_source')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_entitlements_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_entitlements'))
    )
    op.create_index(op.f('ix_entitlements_user_id'), 'entitlements', ['user_id'], unique=False)
    op.create_table('instrument_listings',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('instrument_id', sa.Integer(), nullable=False),
    sa.Column('venue_id', sa.Integer(), nullable=False),
    sa.Column('venue_symbol', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('is_primary', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.CheckConstraint("status IN ('active', 'planned', 'restricted', 'disabled')", name=op.f('ck_instrument_listings_status')),
    sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], name=op.f('fk_instrument_listings_instrument_id_instruments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['venue_id'], ['venues.id'], name=op.f('fk_instrument_listings_venue_id_venues'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_instrument_listings')),
    sa.UniqueConstraint('venue_id', 'venue_symbol', name='uq_instrument_listings_venue_symbol')
    )
    op.create_index(op.f('ix_instrument_listings_instrument_id'), 'instrument_listings', ['instrument_id'], unique=False)
    op.create_index(op.f('ix_instrument_listings_venue_id'), 'instrument_listings', ['venue_id'], unique=False)
    op.create_index('uq_instrument_listings_primary', 'instrument_listings', ['instrument_id'], unique=True, postgresql_where=sa.text('is_primary'))
    op.create_table('refresh_tokens',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('family_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('device_name', sa.String(length=120), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('replaced_by', sa.Uuid(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_refresh_tokens_token_hash'))
    )
    op.create_index('ix_refresh_tokens_family_id', 'refresh_tokens', ['family_id'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
    op.create_table('subscriptions',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('product_id', sa.String(length=120), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('external_ref', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("provider IN ('google_play', 'manual')", name=op.f('ck_subscriptions_provider')),
    sa.CheckConstraint("status IN ('active', 'grace', 'cancelled', 'expired')", name=op.f('ck_subscriptions_status')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_subscriptions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_subscriptions'))
    )
    op.create_index(op.f('ix_subscriptions_user_id'), 'subscriptions', ['user_id'], unique=False)
    op.create_table('candles',
    sa.Column('listing_id', sa.Integer(), nullable=False),
    sa.Column('timeframe', sa.String(length=8), nullable=False),
    sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
    sa.Column('open', sa.Double(), nullable=False),
    sa.Column('high', sa.Double(), nullable=False),
    sa.Column('low', sa.Double(), nullable=False),
    sa.Column('close', sa.Double(), nullable=False),
    sa.Column('volume', sa.Double(), nullable=True),
    sa.Column('quote_volume', sa.Double(), nullable=True),
    sa.Column('trades', sa.BigInteger(), nullable=True),
    sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['listing_id'], ['instrument_listings.id'], name=op.f('fk_candles_listing_id_instrument_listings'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['timeframe'], ['timeframes.code'], name=op.f('fk_candles_timeframe_timeframes')),
    sa.PrimaryKeyConstraint('listing_id', 'timeframe', 'ts', name=op.f('pk_candles')),
    postgresql_partition_by='RANGE (ts)'
    )


def downgrade() -> None:
    op.drop_table('candles')
    op.drop_index(op.f('ix_subscriptions_user_id'), table_name='subscriptions')
    op.drop_table('subscriptions')
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_family_id', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index('uq_instrument_listings_primary', table_name='instrument_listings', postgresql_where=sa.text('is_primary'))
    op.drop_index(op.f('ix_instrument_listings_venue_id'), table_name='instrument_listings')
    op.drop_index(op.f('ix_instrument_listings_instrument_id'), table_name='instrument_listings')
    op.drop_table('instrument_listings')
    op.drop_index(op.f('ix_entitlements_user_id'), table_name='entitlements')
    op.drop_table('entitlements')
    op.drop_index(op.f('ix_devices_user_id'), table_name='devices')
    op.drop_table('devices')
    op.drop_index(op.f('ix_auth_identities_user_id'), table_name='auth_identities')
    op.drop_table('auth_identities')
    op.drop_index(op.f('ix_audit_log_user_id'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_event'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_at'), table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_table('venues')
    op.drop_index('ix_users_email_lower', table_name='users')
    op.drop_table('users')
    op.drop_table('timeframes')
    op.drop_index('ix_instruments_asset_class_active', table_name='instruments')
    op.drop_table('instruments')
