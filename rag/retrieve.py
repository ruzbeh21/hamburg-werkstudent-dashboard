"""Hybrid retrieval: vector search + BM25, fused with Reciprocal Rank Fusion, under SQL filters.

Why hybrid: embeddings catch meaning across languages ("software developer" ↔
"Softwareentwicklung"), BM25 catches exact names and rare terms ("Airbus", "SAP")
that embeddings blur. RRF combines the two *rankings* rather than their scores, so we
never have to calibrate cosine similarities against BM25 values: each list
contributes 1 / (60 + rank), the constant 60 from the original RRF paper.

Filters are applied in SQL first (current postings, time range, work mode, skills);
search then only ranks the postings that passed. Skills found automatically in a
question are tried as AND, then OR, then dropped – and the response says which.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from rag.embeddings import Embedder
from rag.query_parser import ParsedQuery

RRF_K = 60
# A result list is "confident" if the question shares a word with a top posting (BM25 hit)
# or the best vector similarity reaches this value. Chosen on 10 development queries that
# are *not* in the evaluation set (related: 0.862–0.892, unrelated: 0.804–0.823); the
# gap-to-median rule tried first did not separate them – see rag/eval/README.md.
MIN_TOP_SIMILARITY = 0.84

STOPWORDS = set("""
a an and are as at be bei bis das dem den der des die du ein eine einem einen einer er es fuer für gibt
haben hamburg hat ich im in ist je jobs job kann mit nach oder sind sie stelle stellen suche suchen sucht
the to und von welche welcher welches werkstudent werkstudenten werkstudentin werkstudentinnen wie wo
working student students which who with what are for in of on job jobs diese dieser diesem woche week
this neue neuen new gibt es firmen unternehmen companies company position positions bereich area or
""".split())


@dataclass
class Hit:
    """One retrieved posting with the scores that explain its rank."""

    posting_id: int
    title: str
    company: str
    district: str | None
    posted_date: str | None
    first_seen_date: str
    is_current: bool
    role_category: str
    work_mode: str
    hours_max: int | None
    skills: str
    source_url: str
    summary: str
    score: float = 0.0
    vector_rank: int | None = None
    vector_similarity: float | None = None
    bm25_rank: int | None = None


@dataclass
class RetrievalResult:
    """Ranked hits plus what was filtered and whether the result looks relevant."""

    hits: list[Hit]
    applied_filters: list[str] = field(default_factory=list)
    confident: bool = False
    candidates: int = 0


def fts_query(text: str) -> str | None:
    """Build a safe FTS5 query: content words OR-ed, long words as prefixes (cheap stemming).

    Quoting every token avoids FTS5 syntax errors on user input; "Softwareentwickler"
    becomes ``"softwareentwickl"*`` so it also matches "Softwareentwicklung".
    """
    tokens = [t for t in re.findall(r"\w+", text.lower()) if len(t) > 1 and t not in STOPWORDS]
    if not tokens:
        return None
    parts = [f'"{t[:-2]}"*' if len(t) >= 7 else f'"{t}"' for t in dict.fromkeys(tokens)]
    return " OR ".join(parts)


def candidate_ids(index: sqlite3.Connection, query: ParsedQuery, include_expired: bool,
                  skills: list[str], skill_mode: str) -> list[int]:
    """Posting ids that pass the SQL filters."""
    where, params = [], []
    if not include_expired:
        where.append("p.is_current = 1")
    if query.date_from and query.date_to:
        # "Appeared" = first published in the range, or first seen in the range *after* the
        # very first collection run – that run saw the whole backlog, so its date means nothing.
        first_run = (index.execute("SELECT value FROM meta WHERE key = 'source_first_run'").fetchone()
                     or [""])[0][:10]
        where.append("(p.posted_date BETWEEN ? AND ? "
                     "OR (p.first_seen_date BETWEEN ? AND ? AND p.first_seen_date > ?))")
        params += [query.date_from.isoformat(), query.date_to.isoformat()] * 2 + [first_run]
    if query.remote_or_hybrid:
        where.append("p.work_mode IN ('remote', 'hybrid')")
    if skills:
        marks = ",".join("?" * len(skills))
        having = f"COUNT(DISTINCT skill_id) = {len(skills)}" if skill_mode == "and" else "COUNT(*) >= 1"
        where.append(f"p.posting_id IN (SELECT posting_id FROM posting_skills WHERE skill_id IN ({marks}) "
                     f"GROUP BY posting_id HAVING {having})")
        params += skills
    sql = "SELECT posting_id FROM postings AS p" + (" WHERE " + " AND ".join(where) if where else "")
    return [r[0] for r in index.execute(sql, params)]


def filter_candidates(index: sqlite3.Connection, query: ParsedQuery,
                      include_expired: bool = False,
                      strict_skills: bool = False) -> tuple[list[int], list[str], bool]:
    """Apply filters; relax automatically found skills AND → OR → none if nothing matches.

    Returns the candidate ids, human-readable filter notes, and whether the skill filter
    was actually applied (False if the question had none or it had to be dropped).
    """
    applied = ["only postings online in the latest run"] if not include_expired else []
    applied += [n for n in query.notes if not n.startswith("skills")]
    if not query.skills:
        return candidate_ids(index, query, include_expired, [], "and"), applied, False
    modes = [("and", query.skills)]
    if not strict_skills:
        modes += [("or", query.skills), ("none", [])]
    for mode, skills in modes:
        ids = candidate_ids(index, query, include_expired, skills, mode)
        if ids or strict_skills:
            break
    if mode == "and":
        applied.append("skills (all of): " + ", ".join(query.skills))
    elif mode == "or":
        applied.append("skills (any of, no posting had all): " + ", ".join(query.skills))
    else:
        applied.append("skill filter dropped – no posting mentions " + ", ".join(query.skills))
    return ids, applied, mode != "none"


def vector_ranking(index: sqlite3.Connection, embedder: Embedder, text: str,
                   allowed: set[int]) -> tuple[list[int], dict[int, float]]:
    """Rank allowed postings by best chunk similarity. Exact search over all chunks (small corpus)."""
    total = index.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    if not total:
        return [], {}
    vector = np.asarray(embedder.embed_query(text), dtype=np.float32)
    rows = index.execute("""SELECT c.posting_id, v.distance
                            FROM vec_chunks AS v JOIN chunks AS c USING (chunk_id)
                            WHERE v.embedding MATCH ? AND k = ? ORDER BY v.distance""",
                         (vector.tobytes(), total)).fetchall()
    best: dict[int, float] = {}
    for posting_id, distance in rows:
        best.setdefault(posting_id, 1.0 - distance)        # rows are sorted: first = best chunk
    return [pid for pid in best if pid in allowed], best


def bm25_ranking(index: sqlite3.Connection, text: str, allowed: set[int]) -> list[int]:
    """Rank allowed postings by their best BM25 chunk score (FTS5: lower is better)."""
    match = fts_query(text)
    if not match:
        return []
    # FTS5 only allows bm25() in a plain query on the FTS table (no joins or aggregates,
    # even via a subquery), so chunks are mapped to postings in Python.
    scored = index.execute("SELECT rowid, bm25(fts_chunks) FROM fts_chunks WHERE fts_chunks MATCH ?",
                           (match,)).fetchall()
    if not scored:
        return []
    owner = dict(index.execute("SELECT chunk_id, posting_id FROM chunks").fetchall())
    best: dict[int, float] = {}
    for chunk_id, score in scored:
        pid = owner[chunk_id]
        best[pid] = min(score, best.get(pid, score))
    return sorted((pid for pid in best if pid in allowed), key=lambda pid: (best[pid], pid))


def rrf(rankings: list[list[int]]) -> dict[int, float]:
    """Reciprocal Rank Fusion: sum of 1 / (RRF_K + rank) over all rankings (rank starts at 1)."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, pid in enumerate(ranking, start=1):
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (RRF_K + rank)
    return scores


def load_hits(index: sqlite3.Connection, ids: list[int]) -> dict[int, Hit]:
    """Fetch display metadata for posting ids."""
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = index.execute(f"""SELECT posting_id, title, company, district, posted_date, first_seen_date,
                                    is_current, role_category, work_mode, hours_max, skills, source_url,
                                    summary
                             FROM postings WHERE posting_id IN ({marks})""", ids).fetchall()
    return {r["posting_id"]: Hit(**{**dict(r), "is_current": bool(r["is_current"])}) for r in rows}


def retrieve(index: sqlite3.Connection, embedder: Embedder, query: ParsedQuery, k: int = 5,
             mode: str = "hybrid", include_expired: bool = False,
             strict_skills: bool = False) -> RetrievalResult:
    """Return the top ``k`` postings for a parsed question.

    ``mode`` is ``hybrid`` (default), ``vector`` or ``bm25`` – the last two exist for the evaluation.
    """
    ids, applied, skills_applied = filter_candidates(index, query, include_expired, strict_skills)
    allowed = set(ids)
    if not allowed:
        return RetrievalResult(hits=[], applied_filters=applied, confident=False, candidates=0)

    vec_ranked, sims = ([], {}) if mode == "bm25" else vector_ranking(
        index, embedder, query.text, allowed)
    bm25_ranked = bm25_ranking(index, query.text, allowed) if mode != "vector" else []
    rankings = {"hybrid": [vec_ranked, bm25_ranked], "vector": [vec_ranked], "bm25": [bm25_ranked]}[mode]
    scores = rrf(rankings)
    if mode == "bm25" or (mode == "hybrid" and not vec_ranked):
        # Postings without any word match still pass the filters: list them after the matches,
        # so a pure filter question ("neue Stellen diese Woche") returns results.
        for pid in sorted(allowed - set(scores)):
            scores[pid] = 0.0

    top = sorted(scores, key=lambda pid: (-scores[pid], pid))[:k]
    meta = load_hits(index, top)
    vec_pos = {pid: i for i, pid in enumerate(vec_ranked, start=1)}
    bm25_pos = {pid: i for i, pid in enumerate(bm25_ranked, start=1)}
    hits = []
    for pid in top:
        hit = meta[pid]
        hit.score = round(scores[pid], 5)
        hit.vector_rank, hit.bm25_rank = vec_pos.get(pid), bm25_pos.get(pid)
        hit.vector_similarity = round(sims[pid], 4) if pid in sims else None
        hits.append(hit)

    filtered_by_question = skills_applied or bool(query.date_from or query.remote_or_hybrid)
    return RetrievalResult(hits=hits, applied_filters=applied, candidates=len(allowed),
                           confident=is_confident(hits, filtered_by_question))


def is_confident(hits: list[Hit], filtered_by_question: bool) -> bool:
    """Heuristic relevance gate used to answer "keine passenden Anzeigen gefunden".

    A result is trusted if a filter found in the question matched, one of the top three
    postings shares a word with the question, or the best similarity reaches
    ``MIN_TOP_SIMILARITY``. A heuristic: the evaluation reports how often it is right.
    """
    if not hits:
        return False
    if filtered_by_question or any(h.bm25_rank is not None for h in hits[:3]):
        return True
    return max((h.vector_similarity or 0.0) for h in hits) >= MIN_TOP_SIMILARITY


def today_from_index(index: sqlite3.Connection) -> date:
    """The reference "today" for time phrases: the date of the latest pipeline run in the index."""
    value = index.execute("SELECT value FROM meta WHERE key = 'source_last_run'").fetchone()
    return date.fromisoformat(value[0][:10]) if value and value[0] else date.today()
