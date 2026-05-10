"""add pixel dimensions to pages

Revision ID: 0002_pages_dimensions_px
Revises: 0001_initial_postgres
Create Date: 2026-05-09 15:45:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_pages_dimensions_px"
down_revision: Union[str, None] = "0001_initial_postgres"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pages", sa.Column("width_px", sa.Integer(), nullable=True))
    op.add_column("pages", sa.Column("height_px", sa.Integer(), nullable=True))
    op.execute("UPDATE pages SET width_px = ROUND(width_pt * dpi / 72.0), height_px = ROUND(height_pt * dpi / 72.0)")
    op.alter_column("pages", "width_px", nullable=False)
    op.alter_column("pages", "height_px", nullable=False)


def downgrade() -> None:
    op.drop_column("pages", "height_px")
    op.drop_column("pages", "width_px")
