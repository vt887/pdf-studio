from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db as api_db

@pytest.fixture(autouse=True)
def setup_in_memory_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(engine)
    monkeypatch.setattr(api_db, "_ENGINE", engine)
    monkeypatch.setattr(api_db, "_SESSION_FACTORY", Session)
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

