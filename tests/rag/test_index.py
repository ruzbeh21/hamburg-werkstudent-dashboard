"""Tests for the sqlite-vec index and incremental updates (offline hash embedder)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("sqlite_vec")

from rag import store  # noqa: E402
from rag.embeddings import HashingEmbedder  # noqa: E402
from rag.index import main, update_index  # noqa: E402
from scripts.check_privacy import scan_database  # noqa: E402


@pytest.fixture
def index(tmp_path: Path) -> sqlite3.Connection:
    conn = store.connect(tmp_path / "rag_index.db")
    yield conn
    conn.close()


def test_first_build_embeds_every_posting(source, index) -> None:
    stats = update_index(source, index, HashingEmbedder())
    assert (stats.embedded, stats.postings, stats.current, stats.chunks) == (3, 3, 2, 3)
    assert stats.full_rebuild is True
    assert index.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0] == 3


def test_second_run_without_changes_embeds_nothing(source, index) -> None:
    update_index(source, index, HashingEmbedder())
    stats = update_index(source, index, HashingEmbedder())
    assert (stats.embedded, stats.metadata_only, stats.deleted) == (0, 3, 0)


def test_daily_date_change_refreshes_metadata_without_reembedding(source, index) -> None:
    update_index(source, index, HashingEmbedder())
    source.execute("INSERT INTO runs (run_id, started_at) VALUES ('r2', '2026-11-04T06:00:00+00:00')")
    source.execute("UPDATE postings SET last_seen_date = '2026-11-04' WHERE title LIKE '%Data%'")
    stats = update_index(source, index, HashingEmbedder())
    assert stats.embedded == 0 and stats.current == 1          # only the data posting is still online


def test_changed_text_reembeds_only_that_posting(source, index) -> None:
    update_index(source, index, HashingEmbedder())
    source.execute("UPDATE postings SET title = 'Werkstudent Data Engineering (m/w/d)' "
                   "WHERE title LIKE '%Analytics%'")
    stats = update_index(source, index, HashingEmbedder())
    assert stats.embedded == 1 and stats.chunks == 3            # old chunk replaced, not duplicated


def test_postings_removed_from_source_are_deleted(source, index) -> None:
    update_index(source, index, HashingEmbedder())
    source.execute("DELETE FROM postings WHERE title LIKE '%Steuer%'")
    stats = update_index(source, index, HashingEmbedder())
    assert (stats.deleted, stats.postings, stats.chunks) == (1, 2, 2)
    assert index.execute("SELECT COUNT(*) FROM fts_chunks").fetchone()[0] == 2


def test_switching_embedding_model_forces_full_rebuild(source, index) -> None:
    update_index(source, index, HashingEmbedder(dim=64))
    stats = update_index(source, index, HashingEmbedder(dim=32))
    assert stats.full_rebuild is True and stats.embedded == 3
    assert store.get_meta(index, "dim") == "32"


def test_vector_and_fulltext_tables_find_the_right_posting(source, index) -> None:
    embedder = HashingEmbedder()
    update_index(source, index, embedder)
    query = embedder.embed_query("Werkstudent Softwareentwicklung Java Elbe Software").astype(np.float32)
    top = index.execute("""SELECT p.title FROM vec_chunks AS v JOIN chunks AS c USING (chunk_id)
                           JOIN postings AS p USING (posting_id)
                           WHERE v.embedding MATCH ? AND k = 1""", (query.tobytes(),)).fetchone()
    assert "Java" in top["title"]
    hit = index.execute("""SELECT p.company FROM fts_chunks
                           JOIN chunks AS c ON c.chunk_id = fts_chunks.rowid
                           JOIN postings AS p USING (posting_id)
                           WHERE fts_chunks MATCH 'steuerberatung'""").fetchone()
    assert hit["company"] == "Alster Tax"


def test_skill_metadata_supports_sql_filters(source, index) -> None:
    update_index(source, index, HashingEmbedder())
    titles = [r[0] for r in index.execute("""SELECT title FROM postings WHERE posting_id IN
               (SELECT posting_id FROM posting_skills WHERE skill_id = 'power_bi')""")]
    assert titles == ["Werkstudent Data Analytics (m/w/d)"]


def test_published_index_passes_privacy_check_and_local_index_fails(source, tmp_path) -> None:
    public = store.connect(tmp_path / "public.db")
    update_index(source, public, HashingEmbedder())
    public.close()
    assert scan_database(tmp_path / "public.db") == []

    local = store.connect(tmp_path / "local.db")
    update_index(source, local, HashingEmbedder(), with_descriptions=True)
    local.close()
    findings = scan_database(tmp_path / "local.db")
    assert any("description chunk" in f for f in findings)
    assert any("--with-descriptions" in f for f in findings)


def test_cli_routes_description_mode_to_local_files(source, tmp_path, monkeypatch) -> None:
    source_file = Path(source.execute("PRAGMA database_list").fetchone()["file"])
    monkeypatch.setenv("RAG_SOURCE_DB", str(tmp_path / "unused-history.db"))
    monkeypatch.setenv("RAG_INDEX_DB", str(tmp_path / "rag_index.db"))
    monkeypatch.setenv("RAG_LOCAL_SOURCE_DB", str(source_file))
    monkeypatch.setenv("RAG_LOCAL_INDEX_DB", str(tmp_path / "rag_index_local.db"))
    stats = main(["--embedder", "hash", "--with-descriptions"])
    assert stats.chunks > 3
    assert (tmp_path / "rag_index_local.db").exists() and not (tmp_path / "rag_index.db").exists()


def test_index_with_old_schema_version_is_rebuilt(source, index) -> None:
    update_index(source, index, HashingEmbedder())
    store.set_meta(index, schema_version="0")
    stats = update_index(source, index, HashingEmbedder())
    assert stats.full_rebuild is True and stats.embedded == 3
    assert store.get_meta(index, "schema_version") == store.SCHEMA_VERSION
