from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any

from document_model.schema import DocumentModel
from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    DocumentRow,
    ImageAssetRow,
    JobRow,
    LayoutBlockRow,
    LinkRow,
    PageRow,
    TextLineRow,
    WordRow,
)

_ENGINE: Engine | None = None
_SESSION_FACTORY: sessionmaker[Session] | None = None


def init_database(database_url: str) -> None:
    global _ENGINE, _SESSION_FACTORY
    _ENGINE = create_engine(database_url, future=True, pool_pre_ping=True)
    _SESSION_FACTORY = sessionmaker(_ENGINE, expire_on_commit=False, class_=Session)


def get_engine() -> Engine:
    if _ENGINE is None:
        raise RuntimeError("Database is not initialized")
    return _ENGINE


@contextmanager
def session_scope():
    if _SESSION_FACTORY is None:
        raise RuntimeError("Database is not initialized")
    session = _SESSION_FACTORY()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_document_row(document_id: str, source_path: str, status: str = "uploaded") -> None:
    with session_scope() as session:
        session.add(
            DocumentRow(
                id=document_id,
                source_path=source_path,
                output_pdf_path=None,
                model_path=None,
                status=status,
            )
        )


def create_job_row(job_id: str, document_id: str, job_type: str, status: str = "queued", queue_name: str = "default") -> None:
    with session_scope() as session:
        session.add(
            JobRow(
                id=job_id,
                document_id=document_id,
                job_type=job_type,
                status=status,
                queue_name=queue_name,
            )
        )


def update_job_status(job_id: str, status: str, error_message: str | None = None) -> None:
    with session_scope() as session:
        job = session.get(JobRow, job_id)
        if job is None:
            return
        job.status = status
        job.error_message = error_message


def update_document_status(document_id: str, status: str, output_pdf_path: str | None = None, model_path: str | None = None) -> None:
    with session_scope() as session:
        document = session.get(DocumentRow, document_id)
        if document is None:
            return
        document.status = status
        if output_pdf_path is not None:
            document.output_pdf_path = output_pdf_path
        if model_path is not None:
            document.model_path = model_path


def persist_document_model(document: DocumentModel, model_path: str) -> None:
    with session_scope() as session:
        document_row = session.get(DocumentRow, document.id)
        if document_row is None:
            document_row = DocumentRow(
                id=document.id,
                source_path=document.source_file,
                output_pdf_path=document.output_pdf_path,
                model_path=model_path,
                status=document.status,
            )
            session.add(document_row)
        else:
            document_row.source_path = document.source_file
            document_row.output_pdf_path = document.output_pdf_path
            document_row.model_path = model_path
            document_row.status = document.status

        existing_pages = session.scalars(select(PageRow.id).where(PageRow.document_id == document.id)).all()
        if existing_pages:
            existing_line_ids = session.scalars(select(TextLineRow.id).where(TextLineRow.page_id.in_(existing_pages))).all()
            if existing_line_ids:
                session.execute(delete(WordRow).where(WordRow.line_id.in_(existing_line_ids)))
            session.execute(delete(TextLineRow).where(TextLineRow.page_id.in_(existing_pages)))
            session.execute(delete(LayoutBlockRow).where(LayoutBlockRow.page_id.in_(existing_pages)))
            session.execute(delete(ImageAssetRow).where(ImageAssetRow.page_id.in_(existing_pages)))
            session.execute(delete(LinkRow).where(LinkRow.page_id.in_(existing_pages)))
            session.execute(delete(PageRow).where(PageRow.id.in_(existing_pages)))

        for page in document.pages:
            session.add(
                PageRow(
                    id=page.id,
                    document_id=document.id,
                    page_number=page.page_number,
                    width_px=page.width_px,
                    height_px=page.height_px,
                    width_pt=page.width_pt,
                    height_pt=page.height_pt,
                    dpi=page.dpi,
                    original_image_path=page.original_image_path,
                    normalized_image_path=page.normalized_image_path,
                    rotation=page.rotation,
                )
            )
            for block in page.blocks:
                session.add(
                    LayoutBlockRow(
                        id=block.id,
                        page_id=block.page_id,
                        block_type=block.block_type,
                        x=block.x,
                        y=block.y,
                        w=block.w,
                        h=block.h,
                        reading_order=block.reading_order,
                        confidence=block.confidence,
                        review_status=block.review_status,
                    )
                )
            for line in page.text_lines:
                session.add(
                    TextLineRow(
                        id=line.id,
                        block_id=line.block_id,
                        page_id=line.page_id,
                        text=line.text,
                        x=line.x,
                        y=line.y,
                        w=line.w,
                        h=line.h,
                        baseline_y=line.baseline_y,
                        font_family=line.font_family,
                        font_size=line.font_size,
                        font_weight=line.font_weight,
                        font_style=line.font_style,
                        color=line.color,
                        ocr_confidence=line.ocr_confidence,
                        font_confidence=line.font_confidence,
                        review_status=line.review_status,
                    )
                )
            for word in page.words:
                session.add(
                    WordRow(
                        id=word.id,
                        line_id=word.line_id,
                        text=word.text,
                        x=word.x,
                        y=word.y,
                        w=word.w,
                        h=word.h,
                        confidence=word.confidence,
                    )
                )
            for asset in page.assets:
                session.add(
                    ImageAssetRow(
                        id=asset.id,
                        page_id=asset.page_id,
                        source_block_id=asset.source_block_id,
                        asset_path=asset.asset_path,
                        x=asset.x,
                        y=asset.y,
                        w=asset.w,
                        h=asset.h,
                        asset_type=asset.asset_type,
                        confidence=asset.confidence,
                        review_status=asset.review_status,
                    )
                )
            for link in page.links:
                session.add(
                    LinkRow(
                        id=link.id,
                        page_id=link.page_id,
                        source_type=link.source_type,
                        source_text=link.source_text,
                        x=link.x,
                        y=link.y,
                        w=link.w,
                        h=link.h,
                        target_type=link.target_type,
                        target_uri=link.target_uri,
                        target_page_number=link.target_page_number,
                        target_x=link.target_x,
                        target_y=link.target_y,
                        confidence=link.confidence,
                        review_status=link.review_status,
                    )
                )


def fetch_job(job_id: str) -> dict[str, Any] | None:
    with session_scope() as session:
        job = session.get(JobRow, job_id)
        if job is None:
            return None
        return {
            "id": job.id,
            "document_id": job.document_id,
            "job_type": job.job_type,
            "status": job.status,
            "queue_name": job.queue_name,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        }


def fetch_document_source_path(document_id: str) -> str | None:
    with session_scope() as session:
        doc = session.get(DocumentRow, document_id)
        if doc is None:
            return None
        return doc.source_path


def fetch_document(document_id: str) -> dict[str, Any] | None:
    with session_scope() as session:
        doc = session.get(DocumentRow, document_id)
        if doc is None:
            return None
        pages = session.scalars(select(PageRow).where(PageRow.document_id == document_id).order_by(PageRow.page_number)).all()
        page_ids = [p.id for p in pages]
        blocks = session.scalars(select(LayoutBlockRow).where(LayoutBlockRow.page_id.in_(page_ids))).all() if page_ids else []
        lines = session.scalars(select(TextLineRow).where(TextLineRow.page_id.in_(page_ids))).all() if page_ids else []
        line_ids = [l.id for l in lines]
        words = session.scalars(select(WordRow).where(WordRow.line_id.in_(line_ids))).all() if line_ids else []
        assets = session.scalars(select(ImageAssetRow).where(ImageAssetRow.page_id.in_(page_ids))).all() if page_ids else []
        links = session.scalars(select(LinkRow).where(LinkRow.page_id.in_(page_ids))).all() if page_ids else []

        words_by_line: dict[str, list[dict[str, Any]]] = {}
        for word in words:
            words_by_line.setdefault(word.line_id, []).append(
                {
                    "id": word.id,
                    "line_id": word.line_id,
                    "text": word.text,
                    "x": word.x,
                    "y": word.y,
                    "w": word.w,
                    "h": word.h,
                    "confidence": word.confidence,
                }
            )

        blocks_by_page: dict[str, list[dict[str, Any]]] = {}
        for block in blocks:
            blocks_by_page.setdefault(block.page_id, []).append(
                {
                    "id": block.id,
                    "page_id": block.page_id,
                    "block_type": block.block_type,
                    "x": block.x,
                    "y": block.y,
                    "w": block.w,
                    "h": block.h,
                    "reading_order": block.reading_order,
                    "confidence": block.confidence,
                    "review_status": block.review_status,
                }
            )

        lines_by_page: dict[str, list[dict[str, Any]]] = {}
        for line in lines:
            lines_by_page.setdefault(line.page_id, []).append(
                {
                    "id": line.id,
                    "block_id": line.block_id,
                    "page_id": line.page_id,
                    "text": line.text,
                    "x": line.x,
                    "y": line.y,
                    "w": line.w,
                    "h": line.h,
                    "baseline_y": line.baseline_y,
                    "font_family": line.font_family,
                    "font_size": line.font_size,
                    "font_weight": line.font_weight,
                    "font_style": line.font_style,
                    "color": line.color,
                    "ocr_confidence": line.ocr_confidence,
                    "font_confidence": line.font_confidence,
                    "review_status": line.review_status,
                    "words": words_by_line.get(line.id, []),
                }
            )

        assets_by_page: dict[str, list[dict[str, Any]]] = {}
        for asset in assets:
            assets_by_page.setdefault(asset.page_id, []).append(
                {
                    "id": asset.id,
                    "page_id": asset.page_id,
                    "source_block_id": asset.source_block_id,
                    "asset_path": asset.asset_path,
                    "x": asset.x,
                    "y": asset.y,
                    "w": asset.w,
                    "h": asset.h,
                    "asset_type": asset.asset_type,
                    "confidence": asset.confidence,
                    "review_status": asset.review_status,
                }
            )

        links_by_page: dict[str, list[dict[str, Any]]] = {}
        for link in links:
            links_by_page.setdefault(link.page_id, []).append(
                {
                    "id": link.id,
                    "page_id": link.page_id,
                    "source_type": link.source_type,
                    "source_text": link.source_text,
                    "x": link.x,
                    "y": link.y,
                    "w": link.w,
                    "h": link.h,
                    "target_type": link.target_type,
                    "target_uri": link.target_uri,
                    "target_page_number": link.target_page_number,
                    "target_x": link.target_x,
                    "target_y": link.target_y,
                    "confidence": link.confidence,
                    "review_status": link.review_status,
                }
            )

        page_payload = []
        for page in pages:
            page_payload.append(
                {
                    "id": page.id,
                    "document_id": page.document_id,
                    "page_number": page.page_number,
                    "width_px": page.width_px,
                    "height_px": page.height_px,
                    "width_pt": page.width_pt,
                    "height_pt": page.height_pt,
                    "dpi": page.dpi,
                    "original_image_path": page.original_image_path,
                    "normalized_image_path": page.normalized_image_path,
                    "rotation": page.rotation,
                    "layout_blocks": blocks_by_page.get(page.id, []),
                    "text_lines": lines_by_page.get(page.id, []),
                    "image_assets": assets_by_page.get(page.id, []),
                    "links": links_by_page.get(page.id, []),
                }
            )
        return {
            "document": {
                "id": doc.id,
                "source_path": doc.source_path,
                "output_pdf_path": doc.output_pdf_path,
                "model_path": doc.model_path,
                "status": doc.status,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            },
            "pages": page_payload,
        }


def fetch_documents_summary() -> list[dict[str, Any]]:
    with session_scope() as session:
        documents = session.scalars(select(DocumentRow).order_by(DocumentRow.created_at.desc())).all()
        if not documents:
            return []
        doc_ids = [doc.id for doc in documents]
        jobs = session.scalars(
            select(JobRow).where(JobRow.document_id.in_(doc_ids)).order_by(JobRow.document_id, JobRow.created_at.desc())
        ).all()
        latest_by_doc: dict[str, JobRow] = {}
        for job in jobs:
            if job.document_id not in latest_by_doc:
                latest_by_doc[job.document_id] = job

        result: list[dict[str, Any]] = []
        for doc in documents:
            latest_job = latest_by_doc.get(doc.id)
            result.append(
                {
                    "document_id": doc.id,
                    "source_filename": Path(doc.source_path).name,
                    "status": doc.status,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                    "latest_job_id": latest_job.id if latest_job else None,
                    "latest_job_status": latest_job.status if latest_job else None,
                    "has_model": bool(doc.model_path),
                    "has_pdf": bool(doc.output_pdf_path),
                }
            )
        return result
