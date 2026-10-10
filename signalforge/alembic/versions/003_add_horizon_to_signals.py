"""add horizon column to signals

Revision ID: 003
Revises: 002
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'signals',
        sa.Column('horizon', sa.String(20), nullable=False,
                   server_default='swing')
    )
    op.create_index(
        'ix_signal_records_ticker_horizon_created',
        'signals', ['ticker', 'horizon', 'timestamp']
    )


def downgrade():
    op.drop_index('ix_signal_records_ticker_horizon_created')
    op.drop_column('signals', 'horizon')
