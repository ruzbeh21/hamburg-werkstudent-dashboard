"""Fixtures for RAG tests: a small pipeline database built with the real pipeline code."""

from __future__ import annotations

import sqlite3

import pytest

from src.db import upsert_postings
from tests.test_clean import make_posting
from tests.test_db import refresh

POSTINGS = [
    dict(id="R-1", title="Werkstudent Data Analytics (m/w/d)", company="Hafen Daten GmbH",
         posted_date="2026-11-10", last_seen_date="2026-11-03", work_mode="hybrid", hours_max=20,
         description="Du arbeitest mit Python, SQL und Power BI. Sehr gute Deutschkenntnisse."),
    dict(id="R-2", title="Werkstudent Softwareentwicklung Java (m/w/d)", company="Elbe Software AG",
         posted_date="2026-10-01", last_seen_date="2026-11-03",
         description="Java, Spring und Git. Gute Englischkenntnisse."),
    dict(id="R-3", title="Werkstudent Steuerberatung (m/w/d)", company="Alster Tax",
         posted_date="2026-09-01", last_seen_date="2026-10-20",          # no longer online
         description="Excel und MS Office. " + "Mandantenbetreuung im Team. " * 200),
]


@pytest.fixture
def source(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Pipeline database (schema + one run on 2026-11-03) with three postings and skills."""
    upsert_postings(conn, [make_posting(**p) for p in POSTINGS])
    refresh(conn)
    conn.commit()
    return conn
