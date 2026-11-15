"""Premium tiering: plan expiry and admin flag on users; grant metadata on entitlements.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-13 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('plan_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('entitlements', sa.Column('note', sa.String(length=300), nullable=True))
    op.add_column('entitlements', sa.Column('granted_by', sa.Uuid(), nullable=True))
    op.add_column('entitlements', sa.Column('created_at', sa.DateTime(timezone=True),
                                            server_default=sa.text('now()'), nullable=False))
    op.create_foreign_key(op.f('fk_entitlements_granted_by_users'), 'entitlements', 'users', ['granted_by'], ['id'],
                          ondelete='SET NULL')
    op.drop_index(op.f('ix_entitlements_user_id'), table_name='entitlements')
    op.create_index('ix_entitlements_user_id_key', 'entitlements', ['user_id', 'key'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_entitlements_user_id_key', table_name='entitlements')
    op.create_index(op.f('ix_entitlements_user_id'), 'entitlements', ['user_id'], unique=False)
    op.drop_constraint(op.f('fk_entitlements_granted_by_users'), 'entitlements', type_='foreignkey')
    op.drop_column('entitlements', 'created_at')
    op.drop_column('entitlements', 'granted_by')
    op.drop_column('entitlements', 'note')
    op.drop_column('users', 'is_admin')
    op.drop_column('users', 'plan_expires_at')
