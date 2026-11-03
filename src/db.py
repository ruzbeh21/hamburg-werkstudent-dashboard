"""Step 4 – store cleaned postings, runs and skills in SQLite.

The database is updated incrementally (upserts), so it also works as the
long-term history when only the latest raw run is available, e.g. in CI.
Derived columns (role, skills, language levels) are recomputed for every
stored posting on each build, so dictionary edits apply retroactively.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import asdict
from pathlib import Path

from src.clean import Posting, classify_role, clean, load_role_rules, title_key
from src.config import PROJECT_ROOT, load_config
from src.skills import Skill, analyse_posting, load_skills

log = logging.getLogger(__name__)

SCHEMA_FILE = PROJECT_ROOT / "queries" / "schema.sql"

UPSERT_POSTING = """
INSERT INTO postings (
    dedup_key, refnr, title, company, city, postcode, district, posted_date,
    first_seen_date, last_seen_date, offer_type, working_time, contract,
    hours_min, hours_max, work_mode, role_category, n_versions, has_details, source_url, description
) VALUES (
    :dedup_key, :id, :title, :company, :city, :postcode, :district, :posted_date,
    :first_seen_date, :last_seen_date, :offer_type, :working_time, :contract,
    :hours_min, :hours_max, :work_mode, :role_category, :n_versions, :has_details, :source_url, :description
)
ON CONFLICT (dedup_key) DO UPDATE SET
    refnr           = excluded.refnr,
    title           = excluded.title,
    company         = excluded.company,
    city            = excluded.city,
    postcode        = excluded.postcode,
    district        = excluded.district,
    posted_date     = MIN(COALESCE(postings.posted_date, excluded.posted_date),
                          COALESCE(excluded.posted_date, postings.posted_date)),
    first_seen_date = MIN(postings.first_seen_date, excluded.first_seen_date),
    last_seen_date  = MAX(postings.last_seen_date, excluded.last_seen_date),
    offer_type      = excluded.offer_type,
    working_time    = excluded.working_time,
    contract        = excluded.contract,
    hours_min       = COALESCE(excluded.hours_min, postings.hours_min),
    hours_max       = COALESCE(excluded.hours_max, postings.hours_max),
    -- without the text this run, "not_stated" means "unknown": keep what the text said before
    work_mode       = CASE WHEN excluded.has_details = 1 OR excluded.work_mode <> 'not_stated'
                           THEN excluded.work_mode ELSE postings.work_mode END,
    n_versions      = CASE WHEN excluded.refnr = postings.refnr
                           THEN MAX(postings.n_versions, excluded.n_versions)
                           ELSE MAX(postings.n_versions + 1, excluded.n_versions) END,
    has_details     = MAX(postings.has_details, excluded.has_details),
    source_url      = excluded.source_url,
    description     = COALESCE(excluded.description, postings.description)
"""


def connect(path: Path) -> sqlite3.Connection:
    """Open the database with foreign keys enabled and dict-like rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection, schema_file: Path = SCHEMA_FILE) -> None:
    """Create tables, indices and views if they do not exist, then apply migrations."""
    conn.executescript(schema_file.read_text(encoding="utf-8"))
    migrate(conn)


def migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a database was first created.

    ``has_details`` (Nov 2026): existing rows default to 0 ("unknown"), so the
    coverage figure errs on the cautious side for older databases.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(postings)")}
    if "has_details" not in columns:
        conn.execute("ALTER TABLE postings ADD COLUMN has_details INTEGER NOT NULL DEFAULT 0 "
                     "CHECK (has_details IN (0, 1))")


def dedup_key(title: str, company: str) -> str:
    """Stable key for a logical posting across re-posts."""
    return f"{title_key(title)}|{company.lower()}"


def upsert_runs(conn: sqlite3.Connection, raw_dir: Path) -> int:
    """Insert run metadata from every manifest; returns the number of new runs."""
    before = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    for manifest in sorted((raw_dir / "search").glob("*/manifest.json")):
        m = json.loads(manifest.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT OR IGNORE INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (manifest.parent.name, m["started_at"], m.get("finished_at"), m.get("location"),
             m.get("radius_km"), m.get("unique_postings"), m.get("details_fetched"),
             json.dumps(m.get("postings_per_term", {}), ensure_ascii=False)),
        )
    return conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] - before


def upsert_postings(conn: sqlite3.Connection, postings: list[Posting]) -> None:
    """Insert new postings and update existing ones by dedup key."""
    rows = [{**asdict(p), "dedup_key": dedup_key(p.title, p.company),
             "has_details": int(bool(p.description)), "description": p.description or None}
            for p in postings]
    conn.executemany(UPSERT_POSTING, rows)


def sync_skill_dictionary(conn: sqlite3.Connection, skills: list[Skill]) -> None:
    """Make the skills table match the YAML dictionary (adds, renames, removes)."""
    conn.executemany(
        "INSERT INTO skills VALUES (?, ?, ?) "
        "ON CONFLICT (skill_id) DO UPDATE SET label = excluded.label, category = excluded.category",
        [(s.id, s.label, s.category) for s in skills],
    )
    placeholders = ",".join("?" * len(skills))
    conn.execute(f"DELETE FROM skills WHERE skill_id NOT IN ({placeholders})", [s.id for s in skills])


def refresh_derived(conn: sqlite3.Connection, skills: list[Skill],
                    role_rules: list[tuple[str, list[re.Pattern[str]]]]) -> None:
    """Recompute role for every posting, and skills/language levels where text exists.

    Postings whose description was already dropped (CI history database) keep
    the skills extracted while their text was available.
    """
    for row in conn.execute("SELECT posting_id, title, description FROM postings").fetchall():
        conn.execute("UPDATE postings SET role_category = ? WHERE posting_id = ?",
                     (classify_role(row["title"], role_rules), row["posting_id"]))
        if not row["description"]:
            continue
        result = analyse_posting(row["title"], row["description"], skills)
        conn.execute(
            "UPDATE postings SET german_level = ?, english_level = ? WHERE posting_id = ?",
            (result.german_level, result.english_level, row["posting_id"]),
        )
        conn.execute("DELETE FROM posting_skills WHERE posting_id = ?", (row["posting_id"],))
        conn.executemany(
            "INSERT INTO posting_skills VALUES (?, ?, ?)",
            [(row["posting_id"], sid, where) for sid, where in result.skills.items()],
        )


def drop_descriptions(conn: sqlite3.Connection) -> None:
    """Remove all description texts and compact the file so no text remains on disk."""
    conn.execute("UPDATE postings SET description = NULL")
    conn.commit()
    conn.execute("VACUUM")


def build(cfg: dict) -> Path:
    """Run cleaning and load everything into SQLite; returns the database path."""
    raw_dir: Path = cfg["paths"]["raw_dir"]
    db_path: Path = cfg["paths"]["database"]
    postings = clean(raw_dir)
    skills, role_rules = load_skills(), load_role_rules()

    conn = connect(db_path)
    try:
        with conn:
            init_schema(conn)
            new_runs = upsert_runs(conn, raw_dir)
            upsert_postings(conn, postings)
            sync_skill_dictionary(conn, skills)
            refresh_derived(conn, skills, role_rules)
            total = conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0]
        if not cfg["database"]["keep_descriptions"]:
            drop_descriptions(conn)
    finally:
        conn.close()
    log.info("DB %s: %d postings, %d new runs, descriptions %s", db_path.name, total, new_runs,
             "kept" if cfg["database"]["keep_descriptions"] else "dropped")
    return db_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build(load_config())
