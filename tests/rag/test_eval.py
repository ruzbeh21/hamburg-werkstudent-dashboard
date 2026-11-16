"""Tests for the evaluation script: label rules, metrics and an offline end-to-end run."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("sqlite_vec")

from rag.eval.run_eval import QuestionResult, main, matches, summarise  # noqa: E402

REF = date(2026, 11, 16)
ROW = {"role_category": "data", "work_mode": "hybrid", "title": "Werkstudent Data Analytics",
       "company": "Airbus Operations GmbH", "posted_date": "2026-10-01", "first_seen_date": "2026-11-12"}


@pytest.mark.parametrize("criterion, expected", [
    ({"skills_all": ["python", "sql"]}, True),
    ({"skills_all": ["python", "java"]}, False),
    ({"skills_any": ["java", "sql"]}, True),
    ({"role": ["software"]}, False),
    ({"title_regex": "data"}, True),
    ({"company_regex": "lufthansa"}, False),
    ({"work_mode": ["remote"]}, False),
    ({"appeared_within_days": 7}, True),              # first seen 11-12, after the first run
    ({"none": True}, False),
])
def test_label_criteria(criterion: dict, expected: bool) -> None:
    assert matches(ROW, {"python", "sql"}, criterion, REF, first_run="2026-11-03") is expected


def test_first_run_date_does_not_count_as_new() -> None:
    backlog = {**ROW, "first_seen_date": "2026-11-03"}
    assert matches(backlog, set(), {"appeared_within_days": 14}, REF, first_run="2026-11-03") is False


def test_metrics_for_answerable_and_unanswerable_questions() -> None:
    results = [
        QuestionResult("a", expected=2, first_rank=1, found_in_top10=2, confident=True),
        QuestionResult("b", expected=4, first_rank=3, found_in_top10=1, confident=True),
        QuestionResult("c", expected=1, first_rank=None, found_in_top10=0, confident=False),
        QuestionResult("d", expected=0, first_rank=None, found_in_top10=0, confident=False),
    ]
    m = summarise(results)
    assert m["hit@1"] == pytest.approx(1 / 3) and m["hit@3"] == pytest.approx(2 / 3)
    assert m["mrr@10"] == pytest.approx((1 + 1 / 3) / 3)
    assert m["recall@10"] == pytest.approx((1 + 0.25 + 0) / 3)
    assert m["no_answer_rejected"] == 1.0


def test_offline_run_writes_a_report(tmp_path: Path) -> None:
    out = tmp_path / "results.md"
    summaries = main(["--embedder", "hash", "--output", str(out)])
    assert set(summaries) == {"vector", "bm25", "hybrid", "hybrid_no_filters"}
    report = out.read_text()
    assert "| hybrid |" in report and "## By question group" in report and "q20" in report
