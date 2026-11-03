"""Step 3 – extract skills and language levels with a transparent keyword dictionary.

The dictionary lives in ``dictionaries/skills.yaml``. Matching is plain regular
expressions on title + description, so every hit can be explained – and it is
approximate by design (a company describing itself as an "AI company" counts
as an AI mention).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.config import PROJECT_ROOT

SKILLS_FILE = PROJECT_ROOT / "dictionaries" / "skills.yaml"


@dataclass(frozen=True)
class Skill:
    """One entry of the skill dictionary with compiled patterns."""

    id: str
    label: str
    category: str
    patterns: tuple[re.Pattern[str], ...] = field(repr=False)

    def search(self, text: str) -> bool:
        """Return True if any synonym pattern matches the text."""
        return any(p.search(text) for p in self.patterns)


@dataclass
class SkillResult:
    """Skills found in one posting, plus required language levels."""

    skills: dict[str, str]          # skill id -> "title" or "description"
    german_level: str | None
    english_level: str | None


def load_skills(path: Path = SKILLS_FILE) -> list[Skill]:
    """Load and compile the skill dictionary."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        Skill(
            id=item["id"],
            label=item["label"],
            category=item["category"],
            patterns=tuple(re.compile(p, re.IGNORECASE) for p in item["patterns"]),
        )
        for item in data["skills"]
    ]


def extract_skills(title: str, description: str, skills: list[Skill]) -> dict[str, str]:
    """Return matched skill ids, noting whether the title or only the description matched."""
    found: dict[str, str] = {}
    for skill in skills:
        if skill.search(title):
            found[skill.id] = "title"
        elif skill.search(description):
            found[skill.id] = "description"
    return found


# --------------------------------------------------------------------------- #
# Language levels
# --------------------------------------------------------------------------- #

LANGUAGE_MENTION = {
    "german": re.compile(r"\bdeutsch(?:-|kenntnisse|e[nr]?\s+sprache|sprachig|\b)|\bgerman\b", re.IGNORECASE),
    "english": re.compile(r"\benglisch(?:-|kenntnisse|e[nr]?\s+sprache|sprachig|\b)|\benglish\b", re.IGNORECASE),
}
# Checked from the highest level down; the first hit in a clause decides.
LEVEL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("C2", re.compile(r"\bc2\b|mutterspr|native", re.IGNORECASE)),
    ("C1", re.compile(
        r"\bc1\b|verhandlungssicher|flie(?:ß|ss)end|fluent|sehr\s+gute?[nrs]?\b|excellent|proficient|"
        r"business[- ]level|exzellent|hervorragend", re.IGNORECASE)),
    ("B2", re.compile(r"\bb2\b|\bgute?[nrs]?\b|\bgood\b|solid", re.IGNORECASE)),
    ("B1", re.compile(r"\bb1\b|\ba[12]\b|grundkenntnisse|basic", re.IGNORECASE)),
]
LEVEL_ORDER = ["mentioned", "B1", "B2", "C1", "C2"]
CLAUSE_SPLIT_RE = re.compile(r"\n|(?<=[.;!?])\s+|•")


def language_level(text: str, language: str) -> str | None:
    """Find the highest required level for a language.

    The text is split into clauses (lines, sentences, bullet points). For every
    clause that mentions the language, the level words in that same clause
    decide the level, e.g. "Sehr gute Deutsch- und Englischkenntnisse" gives C1
    for both. A mention without a level word returns ``"mentioned"``; no mention
    returns ``None``.
    """
    best: str | None = None
    for clause in CLAUSE_SPLIT_RE.split(text):
        if not LANGUAGE_MENTION[language].search(clause):
            continue
        level = next((lvl for lvl, pat in LEVEL_PATTERNS if pat.search(clause)), "mentioned")
        if best is None or LEVEL_ORDER.index(level) > LEVEL_ORDER.index(best):
            best = level
    return best


def analyse_posting(title: str, description: str, skills: list[Skill]) -> SkillResult:
    """Extract skills and language levels for one posting."""
    text = f"{title}\n{description}"
    return SkillResult(
        skills=extract_skills(title, description, skills),
        german_level=language_level(text, "german"),
        english_level=language_level(text, "english"),
    )
