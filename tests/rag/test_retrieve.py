"""Tests for hybrid retrieval, filters, fusion and the confidence gate (offline embedder)."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("sqlite_vec")

from rag import store  # noqa: E402
from rag.embeddings import HashingEmbedder  # noqa: E402
from rag.index import update_index  # noqa: E402
from rag.query_parser import ParsedQuery, parse_question  # noqa: E402
from rag.retrieve import fts_query, retrieve, rrf, today_from_index  # noqa: E402

TODAY = date(2026, 11, 3)


@pytest.fixture
def index(source, tmp_path: Path) -> sqlite3.Connection:
    conn = store.connect(tmp_path / "rag_index.db")
    update_index(source, conn, HashingEmbedder())
    yield conn
    conn.close()


def ask(index, text, **kwargs):
    return retrieve(index, HashingEmbedder(), parse_question(text, TODAY), **kwargs)


def test_rrf_rewards_postings_ranked_high_in_both_lists() -> None:
    scores = rrf([[1, 2, 3], [2, 1, 4]])
    assert scores[1] == scores[2] > scores[3] > 0 and scores[4] > 0
    assert rrf([[7]])[7] == pytest.approx(1 / 61)


@pytest.mark.parametrize("text, expected", [
    ("Werkstudent Softwareentwickler", '"softwareentwickl"*'),
    ('SQL "OR" NEAR(', '"sql" OR "near"'),             # FTS5 syntax in user input is neutralised
    ("Werkstudent in Hamburg", None),                  # stopwords only
])
def test_fts_query_is_safe_and_uses_prefixes(text: str, expected: str | None) -> None:
    assert fts_query(text) == expected


def test_skill_filter_returns_only_matching_postings(index) -> None:
    result = ask(index, "Werkstudent mit Python und Power BI")
    assert [h.company for h in result.hits] == ["Hafen Daten GmbH"]
    assert result.confident and "skills (all of): python, power_bi" in result.applied_filters


def test_skill_filter_relaxes_to_any_then_says_so(index) -> None:
    result = ask(index, "Java oder Power BI")           # no posting has both
    assert {h.company for h in result.hits} == {"Hafen Daten GmbH", "Elbe Software AG"}
    assert any(f.startswith("skills (any of") for f in result.applied_filters)


def test_skill_nobody_has_is_dropped_and_reported(index) -> None:
    result = ask(index, "Werkstudent mit Tableau")       # a known skill, but no test posting has it
    assert result.hits                                   # still ranked by search
    assert any(f.startswith("skill filter dropped") for f in result.applied_filters)


def test_strict_skills_return_nothing_instead_of_relaxing(index) -> None:
    query = parse_question("Java und Power BI", TODAY)
    result = retrieve(index, HashingEmbedder(), query, strict_skills=True)
    assert result.hits == [] and result.confident is False


def test_expired_postings_are_excluded_by_default(index) -> None:
    assert all(h.is_current for h in ask(index, "Steuerberatung").hits)
    expired = ask(index, "Steuerberatung", include_expired=True)
    assert expired.hits[0].company == "Alster Tax"


def test_time_filter_ignores_first_seen_dates_from_the_first_run(index) -> None:
    # Fixture: one run on 2026-11-03; first seen 2026-11-01, published 2026-11-10 / 2026-10-01.
    # "Last 7 days" before 11-03 contains a first-seen date, but not one *after* the first run.
    assert ask(index, "Neue Stellen in den letzten 7 Tagen").hits == []
    later = retrieve(index, HashingEmbedder(), parse_question("in den letzten 30 Tagen", date(2026, 11, 20)))
    assert [h.posted_date for h in later.hits] == ["2026-11-10"]      # matched by publication date


@pytest.mark.parametrize("mode", ["vector", "bm25", "hybrid"])
def test_all_modes_rank_the_obvious_match_first(index, mode: str) -> None:
    result = retrieve(index, HashingEmbedder(), ParsedQuery(text="Softwareentwicklung Java Elbe"), mode=mode)
    assert result.hits[0].company == "Elbe Software AG"
    assert result.hits[0].score > 0


def test_hits_explain_their_rank(index) -> None:
    hit = ask(index, "Softwareentwicklung Java").hits[0]
    assert hit.bm25_rank == 1 and hit.vector_rank is not None and hit.vector_similarity is not None


def test_unrelated_question_is_not_confident(index) -> None:
    result = retrieve(index, HashingEmbedder(), ParsedQuery(text="Bäckerei Brötchen backen"))
    assert result.confident is False


def test_today_comes_from_the_latest_run(index) -> None:
    assert today_from_index(index) == TODAY
