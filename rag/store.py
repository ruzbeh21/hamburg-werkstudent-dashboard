"""The index: one SQLite file with vectors (sqlite-vec), full text (FTS5) and metadata.

Why sqlite-vec instead of Chroma: the project already lives in SQLite, so metadata
filters (date range, skills) are plain SQL joins, BM25 comes for free from SQLite's
built-in FTS5 in the same file, and the whole index is one small file that CI can
commit and the API can open read-only. Chroma would add a heavy dependency, its own
storage format and filters without joins – it pays off at a much larger scale.
At a few hundred postings, sqlite-vec's exact (brute-force) KNN takes milliseconds.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import sqlite_vec

from rag.documents import PostingDoc

# Bump when the table layout changes: an index with another version is rebuilt.
SCHEMA_VERSION = "1"
# sqlite-vec preallocates vector storage in blocks (default 1024 vectors = 1.5 MB for
# 384 dims). 128 keeps the committed file at ~0.2 MB for a few hundred postings.
VEC_CHUNK_SIZE = 128

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS postings (
    posting_id      INTEGER PRIMARY KEY,     -- same id as in the pipeline database
    dedup_key       TEXT NOT NULL,
    content_hash    TEXT NOT NULL,           -- what was embedded; drives incremental updates
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    district        TEXT,
    posted_date     TEXT,
    first_seen_date TEXT NOT NULL,
    last_seen_date  TEXT NOT NULL,
    is_current      INTEGER NOT NULL,
    role_category   TEXT NOT NULL,
    work_mode       TEXT NOT NULL,
    hours_max       INTEGER,
    german_level    TEXT,
    english_level   TEXT,
    source_url      TEXT NOT NULL,
    skills          TEXT NOT NULL,           -- display labels, comma-separated
    summary         TEXT NOT NULL            -- structured text of chunk 0, no description
);

CREATE TABLE IF NOT EXISTS posting_skills (
    posting_id INTEGER NOT NULL REFERENCES postings (posting_id) ON DELETE CASCADE,
    skill_id   TEXT NOT NULL,
    PRIMARY KEY (posting_id, skill_id)
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id   INTEGER PRIMARY KEY,
    posting_id INTEGER NOT NULL REFERENCES postings (posting_id) ON DELETE CASCADE,
    chunk_no   INTEGER NOT NULL              -- 0 = structured summary, 1.. = description parts
);
CREATE INDEX IF NOT EXISTS idx_chunks_posting ON chunks (posting_id);
CREATE INDEX IF NOT EXISTS idx_postings_dates ON postings (posted_date, first_seen_date);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(
    text, tokenize = 'unicode61 remove_diacritics 2'
);
"""


def connect(path: Path) -> sqlite3.Connection:
    """Open (or create) an index file with the sqlite-vec extension loaded."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    """Read one value from the meta table, if the table exists."""
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    except sqlite3.OperationalError:
        return None
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, **values: str) -> None:
    """Write key/value pairs to the meta table."""
    conn.executemany("INSERT INTO meta VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                     list(values.items()))


def ensure_schema(conn: sqlite3.Connection, model_name: str, dim: int) -> bool:
    """Create the schema; drop everything first if it was built with another model.

    Vectors from different models are not comparable, so a model change forces a full
    rebuild. Returns True if the index was (re)created from scratch.
    """
    previous = get_meta(conn, "embed_model")
    rebuild = previous is not None and (previous != model_name or get_meta(conn, "dim") != str(dim)
                                        or get_meta(conn, "schema_version") != SCHEMA_VERSION)
    if rebuild:
        for table in ("vec_chunks", "fts_chunks", "chunks", "posting_skills", "postings", "meta"):
            conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.executescript(SCHEMA)
    conn.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0("
                 f"chunk_id INTEGER PRIMARY KEY, embedding float[{dim}] distance_metric=cosine, "
                 f"chunk_size={VEC_CHUNK_SIZE})")
    set_meta(conn, embed_model=model_name, dim=str(dim), schema_version=SCHEMA_VERSION)
    return rebuild or previous is None


def indexed_hashes(conn: sqlite3.Connection) -> dict[int, str]:
    """Content hash per posting currently in the index."""
    rows = conn.execute("SELECT posting_id, content_hash FROM postings")
    return {r["posting_id"]: r["content_hash"] for r in rows}


def upsert_metadata(conn: sqlite3.Connection, doc: PostingDoc, content_hash: str) -> None:
    """Insert or refresh the metadata row and skills of a posting (no vectors)."""
    conn.execute(
        """INSERT INTO postings VALUES (:posting_id, :dedup_key, :content_hash, :title, :company,
               :district, :posted_date, :first_seen_date, :last_seen_date, :is_current, :role_category,
               :work_mode, :hours_max, :german_level, :english_level, :source_url, :skills, :summary)
           ON CONFLICT (posting_id) DO UPDATE SET
               dedup_key = excluded.dedup_key, content_hash = excluded.content_hash,
               title = excluded.title, company = excluded.company, district = excluded.district,
               posted_date = excluded.posted_date, first_seen_date = excluded.first_seen_date,
               last_seen_date = excluded.last_seen_date, is_current = excluded.is_current,
               role_category = excluded.role_category, work_mode = excluded.work_mode,
               hours_max = excluded.hours_max, german_level = excluded.german_level,
               english_level = excluded.english_level, source_url = excluded.source_url,
               skills = excluded.skills, summary = excluded.summary""",
        {**{k: getattr(doc, k) for k in (
            "posting_id", "dedup_key", "title", "company", "district", "posted_date", "first_seen_date",
            "last_seen_date", "role_category", "work_mode", "hours_max", "german_level",
            "english_level", "source_url")},
         "is_current": int(doc.is_current), "content_hash": content_hash,
         "skills": ", ".join(doc.skill_labels), "summary": doc.chunks[0]},
    )
    conn.execute("DELETE FROM posting_skills WHERE posting_id = ?", (doc.posting_id,))
    conn.executemany("INSERT INTO posting_skills VALUES (?, ?)", [(doc.posting_id, s) for s in doc.skill_ids])


def _delete_chunks(conn: sqlite3.Connection, posting_ids: list[int]) -> None:
    for pid in posting_ids:
        rows = conn.execute("SELECT chunk_id FROM chunks WHERE posting_id = ?", (pid,))
        ids = [r["chunk_id"] for r in rows]
        conn.executemany("DELETE FROM vec_chunks WHERE chunk_id = ?", [(i,) for i in ids])
        conn.executemany("DELETE FROM fts_chunks WHERE rowid = ?", [(i,) for i in ids])
        conn.execute("DELETE FROM chunks WHERE posting_id = ?", (pid,))


def replace_chunks(conn: sqlite3.Connection, doc: PostingDoc, vectors: np.ndarray) -> None:
    """Swap a posting's chunks, vectors and full-text rows for new ones."""
    _delete_chunks(conn, [doc.posting_id])
    for chunk_no, (text, vector) in enumerate(zip(doc.chunks, vectors, strict=True)):
        chunk_id = conn.execute("INSERT INTO chunks (posting_id, chunk_no) VALUES (?, ?)",
                                (doc.posting_id, chunk_no)).lastrowid
        conn.execute("INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
                     (chunk_id, np.asarray(vector, dtype=np.float32).tobytes()))
        conn.execute("INSERT INTO fts_chunks (rowid, text) VALUES (?, ?)", (chunk_id, text))


def delete_postings(conn: sqlite3.Connection, posting_ids: list[int]) -> None:
    """Remove postings that no longer exist in the source database."""
    _delete_chunks(conn, posting_ids)
    conn.executemany("DELETE FROM postings WHERE posting_id = ?", [(i,) for i in posting_ids])


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Number of postings, current postings and chunks in the index."""
    row = conn.execute("""SELECT (SELECT COUNT(*) FROM postings) AS postings,
                                 (SELECT COUNT(*) FROM postings WHERE is_current = 1) AS current,
                                 (SELECT COUNT(*) FROM chunks) AS chunks""").fetchone()
    return dict(row)
