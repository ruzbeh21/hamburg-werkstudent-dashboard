"""Retrieval evaluation: ``python -m rag.eval.run_eval`` → ``rag/eval/results.md``.

Steps:
1. ``--label`` derives the expected postings of every question from its objective
   criterion on the frozen snapshot and writes ``labels.json`` (reviewable titles).
2. A normal run builds a fresh index from the snapshot and scores four variants:
   vector only, BM25 only, hybrid (RRF), and hybrid without the question filters.

Metrics, for questions that have an answer:
* hit rate@k – share of questions with at least one expected posting in the top k
* MRR@10 – mean of 1 / rank of the first expected posting (0 if not in the top 10)
* recall@10 – share of all expected postings found in the top 10 (many questions have several)
For the questions without an answer: how often the result was correctly flagged as not confident.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

from rag import store
from rag.config import get_settings
from rag.embeddings import Embedder, get_embedder
from rag.index import update_index
from rag.query_parser import ParsedQuery, parse_question
from rag.retrieve import retrieve

EVAL_DIR = Path(__file__).resolve().parent
QUESTIONS = EVAL_DIR / "questions.yaml"
LABELS = EVAL_DIR / "labels.json"
SNAPSHOT = EVAL_DIR / "snapshot.db"
RESULTS = EVAL_DIR / "results.md"
KS = (1, 3, 5, 10)
MODES = ("vector", "bm25", "hybrid", "hybrid_no_filters")


# --------------------------------------------------------------------------- labels

def matches(row: sqlite3.Row, skills: set[str], criterion: dict, reference: date, first_run: str) -> bool:
    """Does one posting satisfy a question's criterion?"""
    if criterion.get("none"):
        return False
    if "skills_all" in criterion and not set(criterion["skills_all"]) <= skills:
        return False
    if "skills_any" in criterion and not set(criterion["skills_any"]) & skills:
        return False
    if "role" in criterion and row["role_category"] not in criterion["role"]:
        return False
    if "work_mode" in criterion and row["work_mode"] not in criterion["work_mode"]:
        return False
    for key, column in (("title_regex", "title"), ("company_regex", "company")):
        if key in criterion and not re.search(criterion[key], row[column], re.IGNORECASE):
            return False
    if "appeared_within_days" in criterion:
        start = (reference - timedelta(days=criterion["appeared_within_days"] - 1)).isoformat()
        appeared = [row["posted_date"]] if row["posted_date"] else []
        if row["first_seen_date"] > first_run:          # the first run's date is the backlog, not "new"
            appeared.append(row["first_seen_date"])
        if not any(start <= d <= reference.isoformat() for d in appeared):
            return False
    return True


def derive_labels(snapshot: Path, questions: list[dict], reference: date) -> dict[str, list[dict]]:
    """Expected postings per question, from the criteria only (current postings)."""
    conn = sqlite3.connect(f"file:{snapshot}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    skills: dict[int, set[str]] = {}
    for pid, sid in conn.execute("SELECT posting_id, skill_id FROM posting_skills"):
        skills.setdefault(pid, set()).add(sid)
    rows = conn.execute("SELECT * FROM current_postings ORDER BY posting_id").fetchall()
    first_run = conn.execute("SELECT MIN(date(started_at)) FROM runs").fetchone()[0]
    conn.close()
    return {q["id"]: [{"posting_id": r["posting_id"], "title": r["title"], "company": r["company"]}
                      for r in rows
                      if matches(r, skills.get(r["posting_id"], set()), q["criterion"], reference, first_run)]
            for q in questions}


# --------------------------------------------------------------------------- scoring

@dataclass
class QuestionResult:
    """Outcome of one question in one variant."""

    qid: str
    expected: int
    first_rank: int | None
    found_in_top10: int
    confident: bool
    top_titles: list[str] = field(default_factory=list)


def run_question(index: sqlite3.Connection, embedder: Embedder, question: dict, expected: set[int],
                 mode: str, reference: date) -> QuestionResult:
    """Retrieve the top 10 for a question and locate the expected postings."""
    if mode == "hybrid_no_filters":
        parsed, search_mode = ParsedQuery(text=question["question"]), "hybrid"
    else:
        parsed, search_mode = parse_question(question["question"], reference), mode
    result = retrieve(index, embedder, parsed, k=10, mode=search_mode)
    ids = [h.posting_id for h in result.hits]
    ranks = [i for i, pid in enumerate(ids, start=1) if pid in expected]
    return QuestionResult(qid=question["id"], expected=len(expected), first_rank=ranks[0] if ranks else None,
                          found_in_top10=len(ranks), confident=result.confident,
                          top_titles=[h.title for h in result.hits[:3]])


def summarise(results: list[QuestionResult]) -> dict[str, float]:
    """Aggregate metrics: answerable questions and no-answer questions separately."""
    answerable = [r for r in results if r.expected]
    unanswerable = [r for r in results if not r.expected]
    metrics: dict[str, float] = {}
    n = len(answerable)
    for k in KS:
        metrics[f"hit@{k}"] = sum(1 for r in answerable if r.first_rank and r.first_rank <= k) / n
    metrics["mrr@10"] = sum(1 / r.first_rank for r in answerable if r.first_rank) / len(answerable)
    metrics["recall@10"] = sum(r.found_in_top10 / min(r.expected, 10) for r in answerable) / len(answerable)
    metrics["answerable_flagged_confident"] = sum(r.confident for r in answerable) / len(answerable)
    if unanswerable:
        metrics["no_answer_rejected"] = sum(not r.confident for r in unanswerable) / len(unanswerable)
    return metrics


# --------------------------------------------------------------------------- report

def write_report(path: Path, config: dict, labels: dict, per_mode: dict[str, list[QuestionResult]],
                 questions: list[dict]) -> None:
    """Write the markdown report with the summary table and per-question details."""
    summaries = {mode: summarise(res) for mode, res in per_mode.items()}
    n_answerable = sum(1 for q in questions if labels[q["id"]])
    lines = [
        "# Retrieval evaluation", "",
        f"Generated by `python -m rag.eval.run_eval` · snapshot {config['reference_date']} "
        f"({config['postings']} postings, {config['current']} current) · embedder `{config['embedder']}` · "
        f"{len(questions)} questions ({n_answerable} answerable, "
        f"{len(questions) - n_answerable} without answer).",
        "", "Questions and labelling rules: [questions.yaml](questions.yaml) · expected postings: "
        "[labels.json](labels.json) · method: [README.md](README.md).", "",
        "| Variant | hit@1 | hit@3 | hit@5 | hit@10 | MRR@10 | recall@10 | answerable flagged confident "
        "| no-answer rejected |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for mode, m in summaries.items():
        lines.append(f"| {mode} | " + " | ".join(f"{m[f'hit@{k}']:.2f}" for k in KS)
                     + f" | {m['mrr@10']:.3f} | {m['recall@10']:.2f} "
                     f"| {m['answerable_flagged_confident']:.2f} "
                     f"| {m.get('no_answer_rejected', float('nan')):.2f} |")
    lines += ["", "## Per question (hybrid)", "",
              "| id | type | question | expected | first relevant rank | found in top 10 | confident |",
              "|---|---|---|---|---|---|---|"]
    by_id = {r.qid: r for r in per_mode["hybrid"]}
    for q in questions:
        r = by_id[q["id"]]
        rank = "–" if r.first_rank is None else str(r.first_rank)
        lines.append(f"| {q['id']} | {q['type']} | {q['question']} | {r.expected} | {rank} | "
                     f"{r.found_in_top10} | {'yes' if r.confident else 'no'} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> dict[str, dict[str, float]]:
    """Command-line entry point. Returns the summary per variant (used by tests)."""
    parser = argparse.ArgumentParser(description="Evaluate retrieval on the frozen snapshot.")
    parser.add_argument("--label", action="store_true", help="derive labels.json from the criteria and stop")
    parser.add_argument("--embedder", choices=["e5", "hash"], default="e5")
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--output", type=Path, default=RESULTS)
    args = parser.parse_args(argv)

    spec = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))
    questions, reference = spec["questions"], date.fromisoformat(spec["reference_date"])
    if args.label:
        LABELS.write_text(json.dumps(derive_labels(args.snapshot, questions, reference), ensure_ascii=False,
                                     indent=1) + "\n", encoding="utf-8")
        return {}

    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    embedder = get_embedder(args.embedder, get_settings().embed_model)
    with tempfile.TemporaryDirectory() as tmp:
        source = sqlite3.connect(f"file:{args.snapshot}?mode=ro", uri=True)
        index = store.connect(Path(tmp) / "eval_index.db")
        update_index(source, index, embedder)
        counts = store.counts(index)
        per_mode = {mode: [run_question(index, embedder, q, {e["posting_id"] for e in labels[q["id"]]},
                                        mode, reference) for q in questions] for mode in MODES}
        index.close()
        source.close()

    config = {"reference_date": spec["reference_date"], "postings": counts["postings"],
              "current": counts["current"], "embedder": embedder.name}
    write_report(args.output, config, labels, per_mode, questions)
    summaries = {mode: summarise(res) for mode, res in per_mode.items()}
    for mode, m in summaries.items():
        print(f"{mode:18} " + "  ".join(f"{k}={v:.2f}" for k, v in m.items()))
    return summaries


if __name__ == "__main__":
    main()
