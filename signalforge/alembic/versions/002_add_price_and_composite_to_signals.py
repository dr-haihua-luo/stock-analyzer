"""add price and composite_score to signals

Revision ID: 002
Revises: 001
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'signals',
        sa.Column('price_at_signal', sa.Float(), nullable=True)
    )
    op.add_column(
        'signals',
        sa.Column('composite_score', sa.Float(), nullable=True)
    )


def downgrade():
    op.drop_column('signals', 'composite_score')
    op.drop_column('signals', 'price_at_signal')