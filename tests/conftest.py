"""Shared pytest fixtures."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.db import connect, init_schema, sync_skill_dictionary
from src.skills import load_skills


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    """Fresh database with schema, skill dictionary and one run on 2026-11-03."""
    db = connect(tmp_path / "test.db")
    init_schema(db)
    sync_skill_dictionary(db, load_skills())
    db.execute("INSERT INTO runs (run_id, started_at) VALUES ('r1', '2026-11-03T06:00:00+00:00')")
    return db
