"""Market Pulse: headline items and feed health.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-15 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('news_items',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('external_id', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('url', sa.String(length=1000), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('impact', sa.String(length=8), nullable=False),
    sa.Column('impact_reason', sa.String(length=80), nullable=False),
    sa.Column('assets', postgresql.ARRAY(sa.String(length=12)), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("impact IN ('high', 'medium', 'low')", name=op.f('ck_news_items_impact')),
    sa.CheckConstraint("kind IN ('central_bank', 'regulator', 'headline')", name=op.f('ck_news_items_kind')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_news_items')),
    sa.UniqueConstraint('source', 'external_id', name='uq_news_items_source_external_id')
    )
    op.create_index('ix_news_items_assets', 'news_items', ['assets'], unique=False, postgresql_using='gin')
    op.create_index(op.f('ix_news_items_published_at'), 'news_items', ['published_at'], unique=False)
    op.create_table('news_feed_status',
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_ok_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.String(length=80), nullable=True),
    sa.Column('items', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('code', name=op.f('pk_news_feed_status'))
    )


def downgrade() -> None:
    op.drop_table('news_feed_status')
    op.drop_index(op.f('ix_news_items_published_at'), table_name='news_items')
    op.drop_index('ix_news_items_assets', table_name='news_items', postgresql_using='gin')
    op.drop_table('news_items')
