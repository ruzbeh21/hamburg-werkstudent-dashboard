"""Tests for skill extraction and language-level detection."""

from __future__ import annotations

import pytest

from src.skills import extract_skills, language_level, load_skills

SKILLS = load_skills()


def found(text: str, title: str = "") -> set[str]:
    """Skill ids found in a title + description."""
    return set(extract_skills(title, text, SKILLS))


@pytest.mark.parametrize("text, expected", [
    ("Erste Erfahrung mit PYTHON und pandas", {"python"}),
    ("Kenntnisse in SQL, MySQL oder PostgreSQL", {"sql"}),
    ("Power BI oder PowerBI", {"power_bi"}),
    ("Microsoft Excel und MS-Office", {"excel", "ms_office"}),
    ("C#/.NET sowie C++", {"csharp", "cpp"}),
    ("React mit TypeScript", {"js_ts"}),
    ("PowerApps und Power Automate", {"power_platform"}),
    ("Erfahrung mit Git und GitLab CI/CD", {"git", "ci_cd"}),
    ("Künstliche Intelligenz und Machine Learning", {"ai", "ml"}),
    ("Erfahrung mit ChatGPT oder Copilot", {"ai"}),
    ("Grundlagen in R, Python", {"r", "python"}),
])
def test_synonyms_and_case(text: str, expected: set[str]) -> None:
    assert expected <= found(text)


@pytest.mark.parametrize("text, not_expected", [
    ("Erfahrung mit JavaScript", "java"),           # JavaScript is not Java
    ("Kenntnisse in NoSQL-Datenbanken", "sql"),       # NoSQL is not SQL
    ("Wir bieten exzellente Bedingungen", "excel"),   # "exzellent" is not Excel
    ("Spannende Networking-Events und ein globales Netzwerk", "networking"),
    ("Abteilung R&D in Deutschland", "r"),            # R&D is not the language R
    ("Standort Deutschland", "german"),               # country, not language
    ("Wir sind ein Mainstream-Unternehmen", "ml"),
    ("Wir nutzen KI-Tools im Alltag", "ml"),          # AI tool use is not ML
    ("Studium der Informatik, Data Science o. ä.", "ml"),   # degree subject, not a skill
])
def test_false_positives_are_avoided(text: str, not_expected: str) -> None:
    assert not_expected not in found(text)


def test_title_match_is_recorded_before_description() -> None:
    result = extract_skills("Werkstudent Data Analytics mit Python", "Du nutzt SQL.", SKILLS)
    assert result["python"] == "title"
    assert result["sql"] == "description"


@pytest.mark.parametrize("text, language, expected", [
    ("Sehr gute Deutsch- und Englischkenntnisse", "german", "C1"),
    ("Sehr gute Deutsch- und Englischkenntnisse", "english", "C1"),
    ("Deutsch fließend in Wort und Schrift", "german", "C1"),
    ("Deutschkenntnisse auf C2-Niveau", "german", "C2"),
    ("Gute Englischkenntnisse runden dein Profil ab", "english", "B2"),
    ("Fluent German and good English", "german", "C1"),
    ("Englisch von Vorteil", "english", "mentioned"),
    ("Arbeitsort in Deutschland", "german", None),
])
def test_language_levels(text: str, language: str, expected: str | None) -> None:
    assert language_level(text, language) == expected


def test_highest_level_wins_across_clauses() -> None:
    text = "Englisch von Vorteil.\nVerhandlungssichere Englischkenntnisse für Kundentermine."
    assert language_level(text, "english") == "C1"
