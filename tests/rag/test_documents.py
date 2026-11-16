"""Tests for turning postings into index documents (chunking, text, hashing)."""

from __future__ import annotations

import sqlite3

import pytest

from rag.documents import build_documents, chunk_words, load_hamburg_districts, location_text


def by_title(docs, word):
    return next(d for d in docs if word in d.title)


def test_one_structured_document_per_posting(source: sqlite3.Connection) -> None:
    docs = build_documents(source)
    assert len(docs) == 3 and all(len(d.chunks) == 1 for d in docs)
    text = by_title(docs, "Data Analytics").chunks[0]
    for expected in ("Werkstudent Data Analytics", "Unternehmen: Hafen Daten GmbH", "Python", "SQL",
                     "Power BI", "Rolle: Data / BI / KI (Data / BI / AI)", "hybrid", "bis 20",
                     "Deutsch C1", "Veröffentlicht: 2026-11-10"):
        assert expected in text


def test_default_documents_contain_no_description_text(source: sqlite3.Connection) -> None:
    docs = build_documents(source)
    assert all("Mandantenbetreuung" not in c and "Du arbeitest" not in c for d in docs for c in d.chunks)


def test_current_flag_follows_latest_run(source: sqlite3.Connection) -> None:
    docs = build_documents(source)
    assert by_title(docs, "Data Analytics").is_current is True
    assert by_title(docs, "Steuerberatung").is_current is False


def test_local_mode_splits_long_descriptions_into_chunks(source: sqlite3.Connection) -> None:
    docs = build_documents(source, with_descriptions=True, chunk_size=100, chunk_overlap=20)
    tax = by_title(docs, "Steuerberatung")
    assert len(tax.chunks) > 3                                   # summary + several description parts
    assert all(c.startswith("Werkstudent Steuerberatung (m/w/d) – Alster Tax\n") for c in tax.chunks[1:])
    assert len(by_title(docs, "Data Analytics").chunks) == 2     # short text: one description chunk


def test_chunk_words_covers_every_word_with_overlap() -> None:
    words = [f"w{i}" for i in range(23)]
    chunks = chunk_words(" ".join(words), size=10, overlap=3)
    assert [c.split()[0] for c in chunks] == ["w0", "w7", "w14"]
    assert chunks[-1].split()[-1] == "w22"
    assert chunks[0].split()[-3:] == chunks[1].split()[:3]       # overlap kept


@pytest.mark.parametrize("text, expected", [("", []), ("eins zwei", ["eins zwei"])])
def test_chunk_words_short_inputs(text: str, expected: list[str]) -> None:
    assert chunk_words(text, size=10, overlap=3) == expected


def test_chunk_words_rejects_overlap_not_smaller_than_size() -> None:
    with pytest.raises(ValueError):
        chunk_words("a b c", size=3, overlap=3)


def test_content_hash_ignores_daily_dates_but_tracks_text_and_model(source: sqlite3.Connection) -> None:
    doc = build_documents(source)[0]
    original = doc.content_hash("model-a")
    doc.last_seen_date, doc.is_current = "2026-12-01", False
    assert doc.content_hash("model-a") == original
    assert doc.content_hash("model-b") != original
    doc.chunks[0] += "\nSkills: Rust"
    assert doc.content_hash("model-a") != original


@pytest.mark.parametrize("district, expected", [
    ("Hamburg-Nord", "Hamburg-Nord, Hamburg"),
    ("Hamburg", "Hamburg"),
    ("Quickborn", "Quickborn (Umgebung Hamburg)"),
    ("", "Hamburg"),
])
def test_location_text_distinguishes_districts_from_nearby_towns(district: str, expected: str) -> None:
    assert location_text(district, load_hamburg_districts()) == expected
