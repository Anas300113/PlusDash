"""Shared pytest fixtures: in-memory SQLite DB."""
from __future__ import annotations

import os

import pytest

# All backend tests use isolated SQLite fixtures, never the shared managed DB.
os.environ.setdefault("PLUS_REAL_STUDENT_DATA", "0")

from src.core.database import Base, get_engine


@pytest.fixture()
def engine():
    eng = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture()
def session(engine):
    from sqlalchemy.orm import sessionmaker
    S = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = S()
    yield s
    s.close()
