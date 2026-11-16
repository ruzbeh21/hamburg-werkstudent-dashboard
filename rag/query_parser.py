"""Turn a free-text question into metadata filters (skills, time range, work mode).

Rule-based on purpose: it works without an API key, is fully testable and reuses the
pipeline's own skill dictionary (``dictionaries/skills.yaml``), so "Power BI" in a
question means exactly what "Power BI" means in the postings.

Time phrases filter on *when a posting appeared*: its first publication date or the
day the collector first saw it, whichever is in the range. So "diese Woche" means
"new this week", not "still online this week" (that is the default anyway).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from src.skills import Skill, load_skills

WORK_MODE_RE = re.compile(
    r"home[- ]?office|remote|hybrid|mobile[sn]?\s+arbeiten|von zu hause|work from home", re.IGNORECASE)
LAST_N_DAYS_RE = re.compile(
    r"(?:letzten|vergangenen|last|past)\s+(\d{1,3})\s+(?:tagen?|days?)", re.IGNORECASE)
LAST_N_WEEKS_RE = re.compile(
    r"(?:letzten|vergangenen|last|past)\s+(\d{1,2})\s+(?:wochen|weeks)", re.IGNORECASE)


@dataclass
class ParsedQuery:
    """A question plus the filters found in it."""

    text: str
    skills: list[str] = field(default_factory=list)       # skill ids, all must match (AND)
    date_from: date | None = None
    date_to: date | None = None
    remote_or_hybrid: bool = False
    notes: list[str] = field(default_factory=list)        # human-readable, returned to the caller


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def parse_time_range(text: str, today: date) -> tuple[date | None, date | None, str | None]:
    """Find a time phrase and return (from, to, description). ``today`` makes it reproducible."""
    lower = text.lower()
    if match := LAST_N_DAYS_RE.search(lower):
        days = int(match.group(1))
        return today - timedelta(days=days - 1), today, f"last {days} days"
    if match := LAST_N_WEEKS_RE.search(lower):
        weeks = int(match.group(1))
        return today - timedelta(days=7 * weeks - 1), today, f"last {weeks} weeks"
    if re.search(r"\b(letzte[nr]?|vergangene[nr]?) woche\b|\blast week\b", lower):
        start = _week_start(today) - timedelta(days=7)
        return start, start + timedelta(days=6), "last week"
    if re.search(r"\b(diese[rn]?|in dieser) woche\b|\bthis week\b", lower):
        return _week_start(today), today, "this week"
    if re.search(r"\b(diese[nm]?|in diesem) monat\b|\bthis month\b", lower):
        return today.replace(day=1), today, "this month"
    if re.search(r"\bheute\b|\btoday\b", lower):
        return today, today, "today"
    return None, None, None


def parse_question(text: str, today: date, skills: list[Skill] | None = None) -> ParsedQuery:
    """Extract skill, time and work-mode filters from a question."""
    query = ParsedQuery(text=text)
    for skill in skills if skills is not None else load_skills():
        if skill.category != "language" and skill.search(text):
            query.skills.append(skill.id)
    if query.skills:
        query.notes.append("skills: " + ", ".join(query.skills))

    query.date_from, query.date_to, label = parse_time_range(text, today)
    if label:
        query.notes.append(f"time: {label} ({query.date_from} – {query.date_to})")

    if WORK_MODE_RE.search(text):
        query.remote_or_hybrid = True
        query.notes.append("work mode: remote or hybrid")
    return query
