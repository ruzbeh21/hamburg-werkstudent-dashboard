"""Tests for the dashboard export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.analyse import PrivacyError, assert_no_contact_data, cooccurrence_matrix, export
from src.db import upsert_postings
from tests.test_clean import make_posting
from tests.test_db import refresh


def test_cooccurrence_matrix_is_square_and_sorted_by_frequency() -> None:
    rows = [
        {"skill_a": "python", "skill_b": "python", "postings": 3},
        {"skill_a": "python", "skill_b": "sql", "postings": 2},
        {"skill_a": "sql", "skill_b": "python", "postings": 2},
        {"skill_a": "sql", "skill_b": "sql", "postings": 5},
    ]
    result = cooccurrence_matrix(rows, {"python": "Python", "sql": "SQL"})
    assert result["ids"] == ["sql", "python"]
    assert result["labels"] == ["SQL", "Python"]
    assert result["matrix"] == [[5, 2], [2, 3]]


@pytest.mark.parametrize("payload", [
    {"title": "Kontakt: jobs@realfirma.de"},
    [{"note": "Ruf an: +49 40 1234567"}],
])
def test_privacy_guard_blocks_contact_data(payload: object) -> None:
    with pytest.raises(PrivacyError):
        assert_no_contact_data(payload, "test.json")


def test_privacy_guard_allows_dates_and_reference_urls() -> None:
    assert_no_contact_data({"posted_date": "2026-11-03", "hours": 20,
                            "source_url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-1000976534-S",
                            "matrix": [[0, 0, 3]]}, "ok.json")


def test_export_writes_files_without_descriptions(conn, tmp_path: Path) -> None:
    upsert_postings(conn, [make_posting(
        id="A", title="Werkstudent Data Analytics", last_seen_date="2026-11-03",
        description="Python und SQL. Geheimer Beschreibungstext.")])
    refresh(conn)
    conn.commit()
    db_file = Path(conn.execute("PRAGMA database_list").fetchone()["file"])

    out = tmp_path / "out"
    files = export(db_file, out)
    names = {f.name for f in files}
    assert {"kpis.json", "top_skills.json", "postings.json", "postings.csv", "meta.json"} <= names
    kpis = json.loads((out / "kpis.json").read_text())
    assert set(kpis) == {"all", "it"} and kpis["all"]["current_postings"] == 1
    for f in files:
        assert "Geheimer Beschreibungstext" not in f.read_text(encoding="utf-8")
