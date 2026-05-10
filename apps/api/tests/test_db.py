from __future__ import annotations

import pytest
from app import db as api_db
from app.models import Base
from document_model.schema import DocumentModel, ImageAsset, LayoutBlock, PageModel, TextLine, Word
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


@pytest.fixture(autouse=True)
def setup_in_memory_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_fk(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Session = sessionmaker(engine)
    monkeypatch.setattr(api_db, "_ENGINE", engine)
    monkeypatch.setattr(api_db, "_SESSION_FACTORY", Session)
    Base.metadata.create_all(engine)
    yield
    monkeypatch.setattr(api_db, "_ENGINE", None)
    monkeypatch.setattr(api_db, "_SESSION_FACTORY", None)


def test_get_engine_uninitialized(monkeypatch):
    monkeypatch.setattr(api_db, "_ENGINE", None)
    with pytest.raises(RuntimeError):
        api_db.get_engine()

def test_session_scope_uninitialized(monkeypatch):
    monkeypatch.setattr(api_db, "_SESSION_FACTORY", None)
    with pytest.raises(RuntimeError):
        with api_db.session_scope():
            pass


def test_persist_document_model_orders_parent_rows_before_children(tmp_path):
    document = DocumentModel(
        id="doc-1",
        source_file="book/sample.png",
        output_pdf_path=str(tmp_path / "out.pdf"),
        status="rendered",
        pages=[
            PageModel(
                id="page-1",
                page_number=1,
                width_px=100,
                height_px=200,
                width_pt=72.0,
                height_pt=144.0,
                dpi=300,
                original_image_path="output/artifacts/pages/0001.original.png",
                normalized_image_path="output/artifacts/pages/0001.normalized.png",
                blocks=[
                    LayoutBlock(
                        id="block-1",
                        page_id="page-1",
                        block_type="image",
                        x=0,
                        y=0,
                        w=72.0,
                        h=144.0,
                        reading_order=0,
                        confidence=1.0,
                        review_status="approved",
                    ),
                ],
                text_lines=[
                    TextLine(
                        id="line-1",
                        block_id="block-1",
                        page_id="page-1",
                        text="hello",
                        x=10.0,
                        y=10.0,
                        w=50.0,
                        h=12.0,
                        baseline_y=20.0,
                        font_family="sans-serif",
                        font_size=12.0,
                        font_weight="regular",
                        font_style="roman",
                        ocr_confidence=1.0,
                        font_confidence=0.5,
                        review_status="approved",
                    ),
                ],
                words=[
                    Word(
                        id="word-1",
                        line_id="line-1",
                        text="hello",
                        x=10.0,
                        y=10.0,
                        w=50.0,
                        h=12.0,
                        confidence=1.0,
                    ),
                ],
                assets=[
                    ImageAsset(
                        id="asset-1",
                        page_id="page-1",
                        source_block_id="block-1",
                        asset_path="output/artifacts/pages/0001.normalized.png",
                        x=0.0,
                        y=0.0,
                        w=72.0,
                        h=144.0,
                        asset_type="page-image",
                        confidence=1.0,
                        review_status="approved",
                    ),
                ],
            )
        ],
    )

    api_db.persist_document_model(document, str(tmp_path / "model.json"))
