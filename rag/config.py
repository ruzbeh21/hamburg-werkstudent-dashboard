"""Settings for the RAG assistant, read from environment variables with safe defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _path(name: str, default: str) -> Path:
    """Resolve a path setting relative to the project root."""
    value = Path(os.environ.get(name) or default)
    return value if value.is_absolute() else PROJECT_ROOT / value


@dataclass(frozen=True)
class Settings:
    """All tunable values in one place.

    * ``source_db`` – the pipeline's SQLite database. The committed ``data/history.db``
      has no description texts, so the default index is built from structured fields.
    * ``index_db`` – the vector + full-text index written by ``python -m rag.index``.
    """

    source_db: Path = field(default_factory=lambda: _path("RAG_SOURCE_DB", "data/history.db"))
    index_db: Path = field(default_factory=lambda: _path("RAG_INDEX_DB", "data/rag_index.db"))
    # Local "rich" mode with description texts: never committed (see .gitignore).
    local_source_db: Path = field(default_factory=lambda: _path("RAG_LOCAL_SOURCE_DB", "data/jobs.db"))
    local_index_db: Path = field(
        default_factory=lambda: _path("RAG_LOCAL_INDEX_DB", "data/rag_index_local.db"))
    embed_model: str = field(
        default_factory=lambda: os.environ.get("RAG_EMBED_MODEL") or "intfloat/multilingual-e5-small")
    # Description chunks: E5 reads at most 512 tokens; ~350 words keeps German text below that.
    chunk_words: int = 350
    chunk_overlap: int = 50


def get_settings() -> Settings:
    """Return settings for the current environment (re-read on every call, handy in tests)."""
    return Settings()
