"""add segment_type to records

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('records', sa.Column('segment_type', sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column('records', 'segment_type')
