from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DocumentRow(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    output_pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class JobRow(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    queue_name: Mapped[str] = mapped_column(Text, nullable=False, default="default")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PageRow(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    height_px: Mapped[int] = mapped_column(Integer, nullable=False)
    width_pt: Mapped[float] = mapped_column(Float, nullable=False)
    height_pt: Mapped[float] = mapped_column(Float, nullable=False)
    dpi: Mapped[int] = mapped_column(Integer, nullable=False)
    original_image_path: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_image_path: Mapped[str] = mapped_column(Text, nullable=False)
    rotation: Mapped[float] = mapped_column(Float, nullable=False, default=0)


class LayoutBlockRow(Base):
    __tablename__ = "layout_blocks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id"), nullable=False, index=True)
    block_type: Mapped[str] = mapped_column(Text, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    w: Mapped[float] = mapped_column(Float, nullable=False)
    h: Mapped[float] = mapped_column(Float, nullable=False)
    reading_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")


class TextLineRow(Base):
    __tablename__ = "text_lines"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    block_id: Mapped[str] = mapped_column(ForeignKey("layout_blocks.id"), nullable=False)
    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id"), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    w: Mapped[float] = mapped_column(Float, nullable=False)
    h: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    font_family: Mapped[str | None] = mapped_column(Text, nullable=True)
    font_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    font_weight: Mapped[str | None] = mapped_column(Text, nullable=True)
    font_style: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(Text, nullable=False, default="#000000")
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    font_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")


class WordRow(Base):
    __tablename__ = "words"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    line_id: Mapped[str] = mapped_column(ForeignKey("text_lines.id"), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    w: Mapped[float] = mapped_column(Float, nullable=False)
    h: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class ImageAssetRow(Base):
    __tablename__ = "image_assets"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id"), nullable=False, index=True)
    source_block_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_path: Mapped[str] = mapped_column(Text, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    w: Mapped[float] = mapped_column(Float, nullable=False)
    h: Mapped[float] = mapped_column(Float, nullable=False)
    asset_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")


class LinkRow(Base):
    __tablename__ = "links"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    w: Mapped[float] = mapped_column(Float, nullable=False)
    h: Mapped[float] = mapped_column(Float, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
