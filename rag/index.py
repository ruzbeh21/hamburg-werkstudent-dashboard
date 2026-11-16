"""Build or update the RAG index: ``python -m rag.index``.

Incremental by design: a posting is only re-embedded when the text that gets embedded
changes (detected by a content hash). Postings that are simply still online only get
their metadata refreshed (last seen date, "current" flag), which is what changes daily.
That keeps the daily CI step to a few seconds after the model is cached.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from rag import store
from rag.config import get_settings
from rag.documents import build_documents
from rag.embeddings import Embedder, get_embedder

log = logging.getLogger(__name__)


@dataclass
class IndexStats:
    """What an indexing run did."""

    embedded: int = 0          # new or changed postings (vectors written)
    metadata_only: int = 0     # unchanged text, refreshed metadata
    deleted: int = 0
    postings: int = 0
    current: int = 0
    chunks: int = 0
    full_rebuild: bool = False
    seconds: float = 0.0


def update_index(source: sqlite3.Connection, index: sqlite3.Connection, embedder: Embedder,
                 with_descriptions: bool = False, full: bool = False,
                 chunk_size: int = 350, chunk_overlap: int = 50) -> IndexStats:
    """Bring the index in line with the source database and return what changed."""
    started = time.perf_counter()
    stats = IndexStats()
    stats.full_rebuild = store.ensure_schema(index, embedder.name, embedder.dim) or full
    docs = build_documents(source, with_descriptions, chunk_size, chunk_overlap)
    known = {} if stats.full_rebuild else store.indexed_hashes(index)

    to_embed = []
    for doc in docs:
        digest = doc.content_hash(embedder.name)
        store.upsert_metadata(index, doc, digest)
        if known.get(doc.posting_id) == digest:
            stats.metadata_only += 1
        else:
            to_embed.append(doc)

    if to_embed:
        texts = [chunk for doc in to_embed for chunk in doc.chunks]
        vectors = embedder.embed_passages(texts)
        offset = 0
        for doc in to_embed:
            store.replace_chunks(index, doc, vectors[offset:offset + len(doc.chunks)])
            offset += len(doc.chunks)
    stats.embedded = len(to_embed)

    gone = sorted(set(store.indexed_hashes(index)) - {d.posting_id for d in docs})
    store.delete_postings(index, gone)
    stats.deleted = len(gone)

    store.set_meta(index, with_descriptions=str(with_descriptions).lower(),
                   source_last_run=_last_run(source) or "")
    index.commit()
    if stats.embedded or stats.deleted:
        index.execute("VACUUM")                 # keep the committed file compact after rewrites
    stats.__dict__.update(store.counts(index))
    stats.seconds = round(time.perf_counter() - started, 2)
    return stats


def _last_run(source: sqlite3.Connection) -> str | None:
    return source.execute("SELECT MAX(started_at) FROM runs").fetchone()[0]


def main(argv: list[str] | None = None) -> IndexStats:
    """Command-line entry point."""
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Build or update the RAG index.")
    parser.add_argument("--source", type=Path, default=settings.source_db, help="pipeline database")
    parser.add_argument("--index", type=Path, default=settings.index_db, help="index file to write")
    parser.add_argument("--with-descriptions", action="store_true",
                        help="also embed scrubbed description texts (local data/jobs.db only, never commit)")
    parser.add_argument("--full", action="store_true", help="re-embed every posting")
    parser.add_argument("--embedder", choices=["e5", "hash"], default="e5",
                        help="'hash' = tiny offline embedder for tests")
    args = parser.parse_args(argv)
    if args.with_descriptions:
        # Description chunks are stored in the full-text table, so they must never land in
        # the committed index file: switch to the local database and a git-ignored target.
        if args.source == settings.source_db:
            args.source = settings.local_source_db
        if args.index == settings.index_db:
            args.index = settings.local_index_db

    source = sqlite3.connect(f"file:{args.source}?mode=ro", uri=True)
    index = store.connect(args.index)
    try:
        stats = update_index(source, index, get_embedder(args.embedder, settings.embed_model),
                             args.with_descriptions, args.full, settings.chunk_words, settings.chunk_overlap)
    finally:
        source.close()
        index.close()
    log.info("Index %s: %s", args.index.name, asdict(stats))
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
