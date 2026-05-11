from __future__ import annotations

from pathlib import Path

import fitz
from document_model.schema import DocumentModel, Link, PageModel


def _resolve_fontname(font_family: str | None, font_weight: str | None, font_style: str | None) -> str:
    family = (font_family or "sans-serif").lower()
    weight = (font_weight or "regular").lower()
    style = (font_style or "roman").lower()
    if "mono" in family:
        return "cour"
    if "serif" in family:
        return "tiro"
    if weight == "bold" and style == "italic":
        return "helv"
    return "helv"


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    cleaned = value.lstrip("#")
    if len(cleaned) != 6:
        return (0, 0, 0)
    return tuple(int(cleaned[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _render_page_assets(page: fitz.Page, page_model: PageModel) -> None:
    for asset in page_model.assets:
        asset_path = Path(asset.asset_path)
        if not asset_path.exists():
            continue
        rect = fitz.Rect(asset.x, asset.y, asset.x + asset.w, asset.y + asset.h)
        page.insert_image(rect, filename=str(asset_path), overlay=True)


def _render_page_text(page: fitz.Page, page_model: PageModel) -> None:
    for line in page_model.text_lines:
        fontname = _resolve_fontname(line.font_family, line.font_weight, line.font_style)
        fontsize = line.font_size or 12
        baseline_y = line.baseline_y if line.baseline_y is not None else line.y + fontsize
        page.insert_text(
            fitz.Point(line.x, baseline_y),
            line.text,
            fontname=fontname,
            fontsize=fontsize,
            color=_hex_to_rgb(line.color),
            overlay=True,
        )


def _render_page_links(page: fitz.Page, page_model: PageModel) -> None:
    for link in page_model.links:
        if not isinstance(link, Link):
            continue
        rect = fitz.Rect(link.x, link.y, link.x + link.w, link.y + link.h)
        if link.target_type == "external" and link.target_uri:
            page.insert_link({"kind": fitz.LINK_URI, "from": rect, "uri": link.target_uri})
        elif link.target_type == "internal" and link.target_page_number is not None:
            page.insert_link(
                {
                    "kind": fitz.LINK_GOTO,
                    "from": rect,
                    "page": max(link.target_page_number - 1, 0),
                    "to": fitz.Point(link.target_x or 0, link.target_y or 0),
                }
            )


def render_document(document: DocumentModel, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = fitz.open()
    for page_model in document.pages:
        page = pdf.new_page(width=page_model.width_pt, height=page_model.height_pt)
        _render_page_assets(page, page_model)
        _render_page_text(page, page_model)
        _render_page_links(page, page_model)
    pdf.save(output_path)
    pdf.close()
    document.output_pdf_path = str(output_path)
    document.status = "rendered"
    return output_path
