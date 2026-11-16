"""Turn postings from the pipeline database into documents for the index.

Design decision: **one posting = one document**, written from the structured fields
(title, company, district, role, skills, work mode, hours, languages, date). These
fields exist in the public ``data/history.db``, contain no contact data, and are short
enough for the embedding model, so no splitting is needed.

Only in the optional local mode (``with_descriptions=True``, reading ``data/jobs.db``)
the scrubbed description text is added as extra chunks of ~350 words, because a full
posting (~900 tokens on average) is longer than the 512 tokens E5 can read. Each chunk
repeats title and company so it still makes sense on its own.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field

import yaml

from src.clean import DICT_DIR

WORK_MODE_TEXT = {"remote": "remote", "hybrid": "hybrid / Homeoffice möglich"}


@dataclass
class PostingDoc:
    """One posting with its searchable chunks and the metadata returned as a source."""

    posting_id: int
    dedup_key: str
    title: str
    company: str
    district: str
    posted_date: str | None
    first_seen_date: str
    last_seen_date: str
    is_current: bool
    role_category: str
    work_mode: str
    hours_max: int | None
    german_level: str | None
    english_level: str | None
    source_url: str
    skill_ids: list[str] = field(default_factory=list)
    skill_labels: list[str] = field(default_factory=list)
    chunks: list[str] = field(default_factory=list)   # chunk 0 = structured summary

    def content_hash(self, model_name: str) -> str:
        """Fingerprint of everything that is embedded; a change means re-embedding.

        Dates that change daily (last seen, current flag) are deliberately not part
        of the text, so a posting that is simply still online is not re-embedded.
        """
        payload = model_name + "\x1f" + "\x1f".join(self.chunks)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_role_labels() -> dict[str, tuple[str, str]]:
    """German and English label per role id, from the pipeline's role rules."""
    data = yaml.safe_load((DICT_DIR / "roles.yaml").read_text(encoding="utf-8"))
    labels = {c["id"]: (c["label_de"], c["label_en"]) for c in data["categories"]}
    labels[data["other"]["id"]] = (data["other"]["label_de"], data["other"]["label_en"])
    return labels


def load_hamburg_districts() -> set[str]:
    """Names of Hamburg's districts; other ``district`` values are towns around Hamburg."""
    data = yaml.safe_load((DICT_DIR / "hamburg_districts.yaml").read_text(encoding="utf-8"))
    return {name for _, _, name in data["ranges"]} | {"Hamburg"}


def location_text(district: str, hamburg_districts: set[str]) -> str:
    """"Hamburg-Nord, Hamburg" for a district, "Quickborn (Umgebung Hamburg)" for a nearby town."""
    if not district:
        return "Hamburg"
    if district in hamburg_districts:
        return district if district == "Hamburg" else f"{district}, Hamburg"
    return f"{district} (Umgebung Hamburg)"


def structured_text(doc: PostingDoc, role_labels: dict[str, tuple[str, str]],
                    hamburg_districts: set[str] | None = None) -> str:
    """Readable summary of the structured fields – the text that gets embedded.

    Role labels are given in German and English so English questions match too.
    """
    role_de, role_en = role_labels.get(doc.role_category, (doc.role_category, doc.role_category))
    location = location_text(doc.district, hamburg_districts or load_hamburg_districts())
    lines = [doc.title, f"Unternehmen: {doc.company}", f"Ort: {location}", f"Rolle: {role_de} ({role_en})"]
    if doc.skill_labels:
        lines.append("Skills: " + ", ".join(doc.skill_labels))
    if doc.work_mode in WORK_MODE_TEXT:
        lines.append("Arbeitsmodell: " + WORK_MODE_TEXT[doc.work_mode])
    if doc.hours_max:
        lines.append(f"Wochenstunden: bis {doc.hours_max}")
    languages = [f"{name} {level}" for name, level in (("Deutsch", doc.german_level),
                                                      ("Englisch", doc.english_level))
                 if level and level != "mentioned"]
    if languages:
        lines.append("Sprachen: " + ", ".join(languages))
    if doc.posted_date:
        lines.append(f"Veröffentlicht: {doc.posted_date}")
    return "\n".join(lines)


def chunk_words(text: str, size: int, overlap: int) -> list[str]:
    """Split text into windows of ``size`` words that overlap by ``overlap`` words."""
    if size <= overlap:
        raise ValueError("chunk size must be larger than the overlap")
    words = text.split()
    if not words:
        return []
    step = size - overlap
    return [" ".join(words[start:start + size])
            for start in range(0, max(len(words) - overlap, 1), step)]


POSTINGS_SQL = """
SELECT p.posting_id, p.dedup_key, p.title, p.company, p.district, p.posted_date,
       p.first_seen_date, p.last_seen_date, p.role_category, p.work_mode, p.hours_max,
       p.german_level, p.english_level, p.source_url, p.description,
       p.last_seen_date = (SELECT MAX(date(started_at)) FROM runs) AS is_current
FROM postings AS p
ORDER BY p.posting_id
"""

SKILLS_SQL = """
SELECT ps.posting_id, s.skill_id, s.label
FROM posting_skills AS ps
JOIN skills AS s USING (skill_id)
WHERE s.category <> 'language'          -- languages are covered by the level fields
ORDER BY ps.posting_id, s.label
"""


def build_documents(conn: sqlite3.Connection, with_descriptions: bool = False,
                    chunk_size: int = 350, chunk_overlap: int = 50) -> list[PostingDoc]:
    """Read every posting from the pipeline database and build its document."""
    conn.row_factory = sqlite3.Row
    skills: dict[int, list[tuple[str, str]]] = {}
    for row in conn.execute(SKILLS_SQL):
        skills.setdefault(row["posting_id"], []).append((row["skill_id"], row["label"]))
    role_labels, districts = load_role_labels(), load_hamburg_districts()

    docs: list[PostingDoc] = []
    for row in conn.execute(POSTINGS_SQL):
        doc = PostingDoc(
            posting_id=row["posting_id"], dedup_key=row["dedup_key"], title=row["title"],
            company=row["company"], district=row["district"] or "", posted_date=row["posted_date"],
            first_seen_date=row["first_seen_date"], last_seen_date=row["last_seen_date"],
            is_current=bool(row["is_current"]), role_category=row["role_category"],
            work_mode=row["work_mode"], hours_max=row["hours_max"],
            german_level=row["german_level"], english_level=row["english_level"],
            source_url=row["source_url"],
            skill_ids=[s for s, _ in skills.get(row["posting_id"], [])],
            skill_labels=[label for _, label in skills.get(row["posting_id"], [])],
        )
        doc.chunks = [structured_text(doc, role_labels, districts)]
        if with_descriptions and row["description"]:
            header = f"{doc.title} – {doc.company}"
            doc.chunks += [f"{header}\n{part}"
                           for part in chunk_words(row["description"], chunk_size, chunk_overlap)]
        docs.append(doc)
    return docs
