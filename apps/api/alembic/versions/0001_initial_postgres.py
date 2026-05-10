"""initial postgres schema

Revision ID: 0001_initial_postgres
Revises:
Create Date: 2026-05-09 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_postgres"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("output_pdf_path", sa.Text(), nullable=True),
        sa.Column("model_path", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("queue_name", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_document_id", "jobs", ["document_id"], unique=False)
    op.create_index("ix_jobs_status", "jobs", ["status"], unique=False)

    op.create_table(
        "pages",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("width_pt", sa.Float(), nullable=False),
        sa.Column("height_pt", sa.Float(), nullable=False),
        sa.Column("dpi", sa.Integer(), nullable=False),
        sa.Column("original_image_path", sa.Text(), nullable=False),
        sa.Column("normalized_image_path", sa.Text(), nullable=False),
        sa.Column("rotation", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pages_document_id", "pages", ["document_id"], unique=False)

    op.create_table(
        "layout_blocks",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("page_id", sa.Text(), nullable=False),
        sa.Column("block_type", sa.Text(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("w", sa.Float(), nullable=False),
        sa.Column("h", sa.Float(), nullable=False),
        sa.Column("reading_order", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("review_status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_layout_blocks_page_id", "layout_blocks", ["page_id"], unique=False)

    op.create_table(
        "text_lines",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("block_id", sa.Text(), nullable=False),
        sa.Column("page_id", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("w", sa.Float(), nullable=False),
        sa.Column("h", sa.Float(), nullable=False),
        sa.Column("baseline_y", sa.Float(), nullable=True),
        sa.Column("font_family", sa.Text(), nullable=True),
        sa.Column("font_size", sa.Float(), nullable=True),
        sa.Column("font_weight", sa.Text(), nullable=True),
        sa.Column("font_style", sa.Text(), nullable=True),
        sa.Column("color", sa.Text(), nullable=False, server_default=sa.text("'#000000'")),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("font_confidence", sa.Float(), nullable=True),
        sa.Column("review_status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.ForeignKeyConstraint(["block_id"], ["layout_blocks.id"]),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_text_lines_page_id", "text_lines", ["page_id"], unique=False)

    op.create_table(
        "words",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("line_id", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("w", sa.Float(), nullable=False),
        sa.Column("h", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["line_id"], ["text_lines.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_words_line_id", "words", ["line_id"], unique=False)

    op.create_table(
        "image_assets",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("page_id", sa.Text(), nullable=False),
        sa.Column("source_block_id", sa.Text(), nullable=True),
        sa.Column("asset_path", sa.Text(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("w", sa.Float(), nullable=False),
        sa.Column("h", sa.Float(), nullable=False),
        sa.Column("asset_type", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("review_status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_image_assets_page_id", "image_assets", ["page_id"], unique=False)

    op.create_table(
        "links",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("page_id", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("w", sa.Float(), nullable=False),
        sa.Column("h", sa.Float(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_uri", sa.Text(), nullable=True),
        sa.Column("target_page_number", sa.Integer(), nullable=True),
        sa.Column("target_x", sa.Float(), nullable=True),
        sa.Column("target_y", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("review_status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_links_page_id", "links", ["page_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_links_page_id", table_name="links")
    op.drop_table("links")
    op.drop_index("ix_image_assets_page_id", table_name="image_assets")
    op.drop_table("image_assets")
    op.drop_index("ix_words_line_id", table_name="words")
    op.drop_table("words")
    op.drop_index("ix_text_lines_page_id", table_name="text_lines")
    op.drop_table("text_lines")
    op.drop_index("ix_layout_blocks_page_id", table_name="layout_blocks")
    op.drop_table("layout_blocks")
    op.drop_index("ix_pages_document_id", table_name="pages")
    op.drop_table("pages")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_document_id", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("documents")
