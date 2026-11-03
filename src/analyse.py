"""Step 5 – run the SQL in ``queries/`` and export small JSON files for the dashboard.

Every query runs twice, for all postings and for IT roles only, and is written
to ``docs/data/<query>.json`` as ``{"all": [...], "it": [...]}``. Before writing,
the export is checked for anything that looks like contact data; if something
is found, the export fails instead of publishing it.
"""

from __future__ import annotations

import csv
import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.clean import DICT_DIR, EMAIL_RE, PHONE_RE
from src.config import PROJECT_ROOT, load_config
from src.db import connect

log = logging.getLogger(__name__)

QUERY_DIR = PROJECT_ROOT / "queries"
SCOPES = {"all": 0, "it": 1}
# Queries exported for both scopes. role_distribution only makes sense unfiltered.
SCOPED_QUERIES = [
    "kpis", "top_skills", "skills_by_role", "top_companies", "weekly_postings",
    "hours_distribution", "language_levels",
]
CO_OCCURRENCE = "skill_cooccurrence"
TABLE_QUERY = "current_postings_table"


class PrivacyError(RuntimeError):
    """Raised when exported data looks like it contains contact details."""


def run_query(conn: sqlite3.Connection, name: str, it_only: int = 0) -> list[dict[str, Any]]:
    """Execute ``queries/<name>.sql`` and return rows as dictionaries."""
    sql = (QUERY_DIR / f"{name}.sql").read_text(encoding="utf-8")
    return [dict(row) for row in conn.execute(sql, {"it_only": it_only}).fetchall()]


def cooccurrence_matrix(rows: list[dict[str, Any]], labels: dict[str, str]) -> dict[str, Any]:
    """Pivot long (skill_a, skill_b, postings) rows into a square matrix."""
    ids = sorted({r["skill_a"] for r in rows}, key=lambda s: -next(
        r["postings"] for r in rows if r["skill_a"] == s and r["skill_b"] == s))
    lookup = {(r["skill_a"], r["skill_b"]): r["postings"] for r in rows}
    return {
        "ids": ids,
        "labels": [labels.get(i, i) for i in ids],
        "matrix": [[lookup.get((a, b), 0) for b in ids] for a in ids],
    }


def build_meta(conn: sqlite3.Connection) -> dict[str, Any]:
    """Dataset metadata: update time, number of runs, labels for roles and skills."""
    runs = conn.execute("SELECT MIN(started_at) AS first, MAX(started_at) AS last, "
                        "COUNT(*) AS n FROM runs").fetchone()
    roles = yaml.safe_load((DICT_DIR / "roles.yaml").read_text(encoding="utf-8"))
    role_labels = {c["id"]: {"de": c["label_de"], "en": c["label_en"]} for c in roles["categories"]}
    role_labels[roles["other"]["id"]] = {"de": roles["other"]["label_de"], "en": roles["other"]["label_en"]}
    return {
        "last_run": runs["last"],
        "first_run": runs["first"],
        "runs": runs["n"],
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_postings_in_db": conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0],
        "roles": role_labels,
        "skills": {r["skill_id"]: {"label": r["label"], "category": r["category"]}
                   for r in conn.execute("SELECT * FROM skills ORDER BY skill_id")},
    }


def assert_no_contact_data(payload: Any, name: str) -> None:
    """Fail loudly if any exported string contains an email or phone number."""
    text = json.dumps(payload, ensure_ascii=False)
    # URLs legitimately contain long digit runs (reference numbers); ignore them.
    text = re.sub(r"https?://[^\"\s]+", "", text)
    for pattern in (EMAIL_RE, PHONE_RE):
        if match := pattern.search(text):
            raise PrivacyError(f"{name}: export looks like it contains contact data ({match.group()[:4]}…)")


def write_json(path: Path, payload: Any) -> None:
    """Write compact JSON (small files load faster on GitHub Pages)."""
    assert_no_contact_data(payload, path.name)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write the postings table as CSV so visitors can download the data."""
    assert_no_contact_data(rows, path.name)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)


def export(db_path: Path, out_dir: Path) -> list[Path]:
    """Export all dashboard data files and return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with connect(db_path) as conn:
        meta = build_meta(conn)
        skill_labels = {k: v["label"] for k, v in meta["skills"].items()}

        for name in SCOPED_QUERIES:
            payload = {scope: run_query(conn, name, flag) for scope, flag in SCOPES.items()}
            if name == "kpis":
                payload = {scope: rows[0] for scope, rows in payload.items()}
            written.append(out_dir / f"{name}.json")
            write_json(written[-1], payload)

        co = {scope: cooccurrence_matrix(run_query(conn, CO_OCCURRENCE, flag), skill_labels)
              for scope, flag in SCOPES.items()}
        written.append(out_dir / f"{CO_OCCURRENCE}.json")
        write_json(written[-1], co)

        written.append(out_dir / "role_distribution.json")
        write_json(written[-1], run_query(conn, "role_distribution"))

        table = run_query(conn, TABLE_QUERY)
        written.append(out_dir / "postings.json")
        write_json(written[-1], table)
        written.append(out_dir / "postings.csv")
        write_csv(written[-1], table)

        written.append(out_dir / "meta.json")
        write_json(written[-1], meta)

    log.info("Exported %d files to %s", len(written), out_dir)
    return written


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    export(cfg["paths"]["database"], cfg["paths"]["export_dir"])
