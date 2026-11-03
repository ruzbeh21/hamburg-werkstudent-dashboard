"""Tests for the SQLite layer: upserts across runs and the SQL queries."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.clean import load_role_rules
from src.db import drop_descriptions, refresh_derived, upsert_postings
from src.skills import load_skills
from tests.test_clean import make_posting

QUERIES = Path(__file__).resolve().parent.parent / "queries"


def refresh(conn: sqlite3.Connection) -> None:
    refresh_derived(conn, load_skills(), load_role_rules())


def test_repost_with_new_refnr_updates_same_row(conn: sqlite3.Connection) -> None:
    first = make_posting(id="OLD-1", posted_date="2026-08-05", first_seen_date="2026-08-05",
                         last_seen_date="2026-08-30", hours_min=16, hours_max=20)
    upsert_postings(conn, [first])
    repost = make_posting(id="NEW-2", title="Werkstudentin IT (w/m/d)", posted_date="2026-11-01",
                          first_seen_date="2026-11-03", last_seen_date="2026-11-03")
    upsert_postings(conn, [repost])

    rows = conn.execute("SELECT * FROM postings").fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["refnr"] == "NEW-2"
    assert row["posted_date"] == "2026-08-05"         # earliest kept
    assert row["first_seen_date"] == "2026-08-05"
    assert row["last_seen_date"] == "2026-11-03"
    assert row["hours_max"] == 20                     # not overwritten by NULL
    assert row["n_versions"] == 2


def test_rerunning_same_data_is_idempotent(conn: sqlite3.Connection) -> None:
    p = make_posting(id="A", n_versions=2)
    upsert_postings(conn, [p])
    upsert_postings(conn, [p])
    row = conn.execute("SELECT COUNT(*) AS n, MAX(n_versions) AS v FROM postings").fetchone()
    assert (row["n"], row["v"]) == (1, 2)


def test_refresh_derived_fills_skills_and_levels(conn: sqlite3.Connection) -> None:
    upsert_postings(conn, [make_posting(
        id="A", title="Werkstudent Data Analytics (m/w/d)", last_seen_date="2026-11-03",
        description="Du arbeitest mit Python und SQL.\nSehr gute Deutschkenntnisse.")])
    refresh(conn)
    row = conn.execute("SELECT role_category, german_level FROM postings").fetchone()
    assert (row["role_category"], row["german_level"]) == ("data", "C1")
    skills = {r[0] for r in conn.execute("SELECT skill_id FROM posting_skills")}
    assert {"python", "sql", "german"} <= skills


def test_queries_run_and_filter_it_only(conn: sqlite3.Connection) -> None:
    upsert_postings(conn, [
        make_posting(id="A", title="Werkstudent Data Analytics", company="X",
                     last_seen_date="2026-11-03", description="Python, SQL"),
        make_posting(id="B", title="Werkstudent Marketing", company="Y",
                     last_seen_date="2026-11-03", description="Excel"),
        make_posting(id="C", title="Werkstudent Softwareentwicklung", company="Z",
                     last_seen_date="2026-10-01", description="Java"),   # no longer online
    ])
    refresh(conn)
    for sql_file in QUERIES.glob("*.sql"):
        if sql_file.name != "schema.sql":
            conn.execute(sql_file.read_text(), {"it_only": 0}).fetchall()

    kpis = conn.execute((QUERIES / "kpis.sql").read_text(), {"it_only": 0}).fetchone()
    assert kpis["current_postings"] == 2 and kpis["python_pct"] == 50.0
    kpis_it = conn.execute((QUERIES / "kpis.sql").read_text(), {"it_only": 1}).fetchone()
    assert kpis_it["current_postings"] == 1 and kpis_it["python_pct"] == 100.0


def test_postings_without_text_keep_their_skills(conn: sqlite3.Connection) -> None:
    """CI mode: an old posting whose text was dropped keeps its extracted skills."""
    upsert_postings(conn, [make_posting(id="A", title="Werkstudent Data Analytics",
                                        description="Python und SQL")])
    refresh(conn)
    drop_descriptions(conn)
    refresh(conn)                                   # next run: no text available any more
    skills = {r[0] for r in conn.execute("SELECT skill_id FROM posting_skills")}
    assert {"python", "sql"} <= skills
    assert conn.execute("SELECT description FROM postings").fetchone()[0] is None


def test_drop_descriptions_leaves_no_text_in_file(tmp_path) -> None:
    from src.db import connect, init_schema
    path = tmp_path / "history.db"
    db = connect(path)
    init_schema(db)
    upsert_postings(db, [make_posting(id="A", description="GEHEIMER-TEXT " * 200)])
    db.commit()
    drop_descriptions(db)
    db.close()
    assert b"GEHEIMER-TEXT" not in path.read_bytes()


def test_missing_text_does_not_erase_earlier_findings(conn: sqlite3.Connection) -> None:
    """A run without the detail text must not downgrade work mode, hours or has_details."""
    upsert_postings(conn, [make_posting(id="A", work_mode="hybrid", hours_min=16, hours_max=20,
                                        description="Hybrides Arbeiten, 16-20 Std./Woche")])
    upsert_postings(conn, [make_posting(id="A", work_mode="not_stated", last_seen_date="2026-11-04",
                                        description="")])
    row = conn.execute("SELECT work_mode, hours_max, has_details, description, last_seen_date "
                       "FROM postings").fetchone()
    assert (row["work_mode"], row["hours_max"], row["has_details"]) == ("hybrid", 20, 1)
    assert row["description"].startswith("Hybrides")       # kept, not blanked
    assert row["last_seen_date"] == "2026-11-04"


def test_migration_adds_has_details_to_old_database(tmp_path) -> None:
    from src.db import SCHEMA_FILE, connect, init_schema
    db = connect(tmp_path / "old.db")
    # The schema as it was before has_details existed.
    old_schema = "\n".join(line for line in SCHEMA_FILE.read_text().splitlines()
                           if "has_details" not in line and "CHECK (has_details" not in line)
    db.executescript(old_schema)
    upsert_row = {"dedup_key": "x", "refnr": "A", "title": "t", "company": "c",
                  "first_seen_date": "2026-11-01", "last_seen_date": "2026-11-01",
                  "work_mode": "hybrid", "role_category": "other", "source_url": "u"}
    db.execute(f"INSERT INTO postings ({', '.join(upsert_row)}) VALUES "
               f"({', '.join('?' * len(upsert_row))})", list(upsert_row.values()))
    assert "has_details" not in {r[1] for r in db.execute("PRAGMA table_info(postings)")}
    init_schema(db)
    columns = {r[1] for r in db.execute("PRAGMA table_info(postings)")}
    assert "has_details" in columns
    assert db.execute("SELECT has_details FROM postings").fetchone()[0] == 0
