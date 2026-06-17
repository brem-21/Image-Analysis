"""add s3_key to records

Revision ID: a1b2c3d4e5f6
Revises: 31ade931cfe1
Create Date: 2026-06-15

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "31ade931cfe1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("records", sa.Column("s3_key", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("records", "s3_key")
