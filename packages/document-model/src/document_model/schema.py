from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ReviewStatus = Literal["pending", "approved", "rejected", "needs_review"]
DocumentStatus = Literal["draft", "processing", "rendered", "review_required", "approved", "error"]
BlockType = Literal["text", "image", "table", "title", "header", "footer", "list", "caption"]
TargetType = Literal["external", "internal", "email", "toc"]


class ReconstructionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Box(ReconstructionModel):
    x: float
    y: float
    w: float
    h: float


class Word(Box):
    id: str
    line_id: str
    text: str
    confidence: float | None = None


class TextLine(Box):
    id: str
    block_id: str
    page_id: str
    text: str
    baseline_y: float | None = None
    font_family: str | None = None
    font_size: float | None = None
    font_weight: str | None = None
    font_style: str | None = None
    color: str = "#000000"
    ocr_confidence: float | None = None
    font_confidence: float | None = None
    review_status: ReviewStatus = "pending"


class LayoutBlock(Box):
    id: str
    page_id: str
    block_type: BlockType
    reading_order: int | None = None
    confidence: float | None = None
    review_status: ReviewStatus = "pending"


class ImageAsset(Box):
    id: str
    page_id: str
    source_block_id: str | None = None
    asset_path: str
    asset_type: str | None = None
    confidence: float | None = None
    review_status: ReviewStatus = "pending"


class Link(Box):
    id: str
    page_id: str
    source_type: str
    source_text: str
    target_type: TargetType
    target_uri: str | None = None
    target_page_number: int | None = None
    target_x: float | None = None
    target_y: float | None = None
    confidence: float | None = None
    review_status: ReviewStatus = "pending"


class PageQA(ReconstructionModel):
    pixel_diff: float | None = None
    structural_similarity: float | None = None
    text_coverage: float | None = None
    link_coverage: float | None = None
    unresolved_items: int | None = None
    ocr_text_found: bool | None = None
    review_status: ReviewStatus = "pending"
    notes: dict[str, Any] = Field(default_factory=dict)


class PageModel(ReconstructionModel):
    id: str
    page_number: int
    width_px: int
    height_px: int
    width_pt: float
    height_pt: float
    dpi: int
    rotation: float = 0
    original_image_path: str
    normalized_image_path: str
    blocks: list[LayoutBlock] = Field(default_factory=list)
    text_lines: list[TextLine] = Field(default_factory=list)
    words: list[Word] = Field(default_factory=list)
    assets: list[ImageAsset] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    qa: PageQA = Field(default_factory=PageQA)


class DocumentQA(ReconstructionModel):
    overall_score: float | None = None
    pixel_diff: float | None = None
    structural_similarity: float | None = None
    text_coverage: float | None = None
    link_coverage: float | None = None
    unresolved_items: int | None = None
    review_status: ReviewStatus = "pending"
    notes: dict[str, Any] = Field(default_factory=dict)


class DocumentModel(ReconstructionModel):
    id: str
    source_file: str
    output_pdf_path: str | None = None
    status: DocumentStatus = "draft"
    pages: list[PageModel] = Field(default_factory=list)
    qa: DocumentQA = Field(default_factory=DocumentQA)


DocumentReconstructionModel = DocumentModel
PageReconstructionModel = PageModel
