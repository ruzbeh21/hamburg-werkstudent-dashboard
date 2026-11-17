"""Tests for turning questions into filters."""

from __future__ import annotations

from datetime import date

import pytest

from rag.query_parser import parse_question, parse_time_range

MONDAY = date(2026, 11, 16)


def test_extracts_skills_with_synonyms_and_ignores_languages() -> None:
    q = parse_question("Werkstudent mit Python, PowerBI und guten Englischkenntnissen", MONDAY)
    assert q.skills == ["python", "power_bi"]          # dictionary order, no "english"


def test_question_without_filters() -> None:
    q = parse_question("Werkstudent im Marketing", MONDAY)
    assert (q.skills, q.date_from, q.remote_or_hybrid, q.notes) == ([], None, False, [])


@pytest.mark.parametrize("text, start, end", [
    ("Welche Stellen gibt es diese Woche?", date(2026, 11, 10), MONDAY),   # rolling 7 days
    ("new jobs this week", date(2026, 11, 10), MONDAY),
    ("Stellen der letzten Woche", date(2026, 11, 9), date(2026, 11, 15)),
    ("in den letzten 7 Tagen", date(2026, 11, 10), MONDAY),
    ("past 14 days", date(2026, 11, 3), MONDAY),
    ("in den letzten 2 Wochen", date(2026, 11, 3), MONDAY),
    ("diesen Monat", date(2026, 11, 1), MONDAY),
    ("heute neu", MONDAY, MONDAY),
])
def test_time_phrases_are_relative_to_the_given_day(text: str, start: date, end: date) -> None:
    assert parse_time_range(text, MONDAY)[:2] == (start, end)


def test_no_time_phrase() -> None:
    assert parse_time_range("Werkstudent Data", MONDAY) == (None, None, None)


@pytest.mark.parametrize("text", ["Data-Jobs mit Homeoffice", "remote working student", "mobiles Arbeiten"])
def test_work_mode_phrases(text: str) -> None:
    assert parse_question(text, MONDAY).remote_or_hybrid is True
