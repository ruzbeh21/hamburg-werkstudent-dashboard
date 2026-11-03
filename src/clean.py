"""Step 2 – turn raw API responses into one tidy, deduplicated, scrubbed table.

Deduplication happens in two passes:

1. by reference number, because the same posting shows up under several search
   terms and in every daily run;
2. by normalised title + company, because some employers re-post the same job
   every few weeks under a new reference number.

Contact data (emails, phone numbers, recruiter names) is removed from the
description text here, before anything is stored in the database.
"""

from __future__ import annotations

import csv
import html
import json
import logging
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import yaml

from src.collect import slugify
from src.config import PROJECT_ROOT, load_config

log = logging.getLogger(__name__)

DICT_DIR = PROJECT_ROOT / "dictionaries"
BA_DETAIL_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"
NAME_PLACEHOLDER = "[Name entfernt]"
CONTACT_PLACEHOLDER = "[Kontakt entfernt]"


@dataclass
class Posting:
    """One logical job posting after cleaning and deduplication."""

    id: str
    title: str
    company: str
    city: str
    postcode: str
    district: str
    posted_date: str
    first_seen_date: str
    last_seen_date: str
    offer_type: str
    working_time: str
    contract: str
    hours_min: int | None
    hours_max: int | None
    work_mode: str
    role_category: str
    source_url: str
    n_versions: int = 1
    description: str = field(default="", repr=False)


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #

def html_to_text(raw: str | None) -> str:
    """Strip HTML tags and entities and normalise whitespace, keeping line breaks."""
    if not raw:
        return ""
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>", "\n", raw)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


# Spaces around "@"/"(at)" are allowed for obfuscated addresses, but not line breaks.
EMAIL_RE = re.compile(
    r"[\w.+-]+[ \t]*(?:@|\(at\)|\[at\])[ \t]*[\w-]+(?:[ \t]*(?:\.|\(dot\)|\[dot\])[ \t]*[\w-]+)+",
    re.IGNORECASE,
)
PHONE_RE = re.compile(r"(?:\+49|\(0\d+\)|\b0\d{2,5})[\s/().-]*\d[\d\s/().-]{4,}\d")
TITLE_NAME_RE = re.compile(
    r"\b(Frau|Herrn?|Mr\.?|Mrs\.?|Ms\.?)\s+(?:Dr\.\s+)?[A-ZÄÖÜ][\w'-]+(?:\s+[A-ZÄÖÜ][\w'-]+)?"
)
CONTACT_INTRO_RE = re.compile(
    r"\b(Ansprechpartner(?:in)?|Ansprechperson|Kontaktperson|Recruiter(?:in)?|"
    r"Contact person|Your contact)\s*:?\s*[A-ZÄÖÜ][\w'-]+(?:\s+[A-ZÄÖÜ][\w'-]+)?"
)
LOOKS_LIKE_NAME_RE = re.compile(r"^(?:(?:Frau|Herr|Dr\.)\s+)*[A-ZÄÖÜ][\w'-]+(?:\s+[A-ZÄÖÜ][\w'-]+){1,2}$")
LONG_LINE = 300


def scrub_contact_data(text: str) -> str:
    """Remove emails, phone numbers and recruiter names from a description.

    Short lines that contain an email or phone number are dropped completely,
    because they usually also hold a name or a street address. A short line
    that looks like a bare name directly above such a line is dropped too.
    Long lines (descriptions without line breaks) are scrubbed inline instead.
    """
    kept: list[str] = []
    for line in text.splitlines():
        has_contact = bool(EMAIL_RE.search(line) or PHONE_RE.search(line))
        if has_contact and len(line) <= LONG_LINE:
            if kept and LOOKS_LIKE_NAME_RE.match(kept[-1]):
                kept.pop()
            continue
        line = EMAIL_RE.sub(CONTACT_PLACEHOLDER, line)
        line = PHONE_RE.sub(CONTACT_PLACEHOLDER, line)
        line = CONTACT_INTRO_RE.sub(lambda m: f"{m.group(1)}: {NAME_PLACEHOLDER}", line)
        line = TITLE_NAME_RE.sub(NAME_PLACEHOLDER, line)
        kept.append(line)
    return "\n".join(kept).strip()


COMPANY_SUFFIX_RE = re.compile(
    r"\s+(?:Werk|Abteilung|Niederlassung|Zweigniederlassung|Standort|Geschäftsbereich|c/o)\b.*$",
    re.IGNORECASE,
)


def normalise_company(name: str | None) -> str:
    """Remove plant/department suffixes and fix common legal-form casing."""
    if not name:
        return "Unbekannt"
    name = COMPANY_SUFFIX_RE.sub("", name.strip())
    name = re.sub(r"\bGmbh\b", "GmbH", name)
    return re.sub(r"\s+", " ", name).strip(" ,-")


def title_key(title: str) -> str:
    """Normalise a job title for duplicate detection (gender markers, brackets, numbers)."""
    key = title.lower()
    key = re.sub(r"\([^)]*\)", " ", key)                      # (m/w/d), (gn), (a*) …
    key = re.sub(r"\b[mwdfx]\s*/\s*[mwdfx](?:\s*/\s*[mwdfx])?\b", " ", key)
    key = re.sub(r"[*:_/]?inn?en\b|[*:_/]in\b", "", key)      # Werkstudent*in, -innen
    key = re.sub(r"werkstudentin\b", "werkstudent", key)
    key = re.sub(r"\b\d+\b", " ", key)                         # trailing ad numbers
    return re.sub(r"[^a-z0-9äöüß]+", " ", key).strip()


# --------------------------------------------------------------------------- #
# Field extraction
# --------------------------------------------------------------------------- #

HOUR_UNIT = r"(?:std\.?|stunden|h|hours|hrs)"
NUMBER = r"(\d{1,2}(?:[.,]\d)?)"
WEEK_CONTEXT_RE = re.compile(
    r"woche|wöchentl|/\s*w\b|per week|a week|weekly|teilzeit|part[- ]time", re.IGNORECASE
)
# Checked only in the text *before* a match: "in den Semesterferien bis zu 40 Std."
EXCLUDE_BEFORE_RE = re.compile(
    r"semesterferien|vorlesungsfrei|ferien|semester break|holidays|praktikant|praktikum|intern\b",
    re.IGNORECASE,
)
HOURS_RE = re.compile(
    rf"(?<![\d.,]){NUMBER}(?:\s*(?:-|–|bis|und|to|and)\s*{NUMBER})?[\s-]*{HOUR_UNIT}(?![a-zäöü])",
    re.IGNORECASE,
)
MIN_HOURS, MAX_HOURS = 1, 40


def parse_weekly_hours(text: str) -> tuple[int | None, int | None]:
    """Find weekly hours like "16-20 Std./Woche", "19,5 Stunden" or "20-Stunden-Woche".

    Only numbers with a week or part-time reference within 40 characters count;
    semester-break and internship clauses just before a number are ignored.
    Returns rounded ``(min, max)`` or ``(None, None)``.
    """
    values: list[int] = []
    for match in HOURS_RE.finditer(text):
        before = text[max(0, match.start() - 40): match.start()]
        context = before + text[match.start(): match.end() + 40]
        if not WEEK_CONTEXT_RE.search(context) or EXCLUDE_BEFORE_RE.search(before):
            continue
        for group in match.groups():
            if group and MIN_HOURS <= (hours := float(group.replace(",", "."))) <= MAX_HOURS:
                values.append(round(hours))
    if not values:
        return None, None
    return min(values), max(values)


FULL_REMOTE_RE = re.compile(
    r"(?:100\s*%|vollständig|komplett|full(?:y)?)\s*remote|remote[- ]first|ortsunabhängig", re.IGNORECASE
)
HYBRID_RE = re.compile(r"remote|hybrid|home[- ]?office|mobile[sn]?\s+arbeiten", re.IGNORECASE)


def detect_work_mode(text: str, homeoffice_flag: bool) -> str:
    """Return ``remote``, ``hybrid`` or ``not_stated`` (on-site cannot be confirmed)."""
    if FULL_REMOTE_RE.search(text):
        return "remote"
    if homeoffice_flag or HYBRID_RE.search(text):
        return "hybrid"
    return "not_stated"


HAMBURG_CENTRE = (53.5511, 9.9937)
CONTRACT_LABELS = {"BEFRISTET": "Befristet", "UNBEFRISTET": "Unbefristet"}


def pick_location(locations: list[dict[str, Any]]) -> dict[str, Any]:
    """Choose the address closest to Hamburg from a multi-location posting.

    Uses squared lat/lon distance, which is enough to rank locations; entries
    without coordinates are only used if nothing else is available.
    """
    def distance(loc: dict[str, Any]) -> float:
        if loc.get("breite") is None or loc.get("laenge") is None:
            return float("inf")
        return (loc["breite"] - HAMBURG_CENTRE[0]) ** 2 + (loc["laenge"] - HAMBURG_CENTRE[1]) ** 2

    return min(locations, key=distance).get("adresse", {}) if locations else {}


def working_time(job: dict[str, Any]) -> str:
    """Summarise the API's working-time flags."""
    if any(v for k, v in job.items() if k.startswith("arbeitszeitTeilzeit")):
        return "Teilzeit"
    if job.get("arbeitszeitVollzeit"):
        return "Vollzeit"
    return "keine Angabe"


def load_role_rules(path: Path = DICT_DIR / "roles.yaml") -> list[tuple[str, list[re.Pattern[str]]]]:
    """Compile the ordered role rules from YAML."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        (cat["id"], [re.compile(kw, re.IGNORECASE) for kw in cat["keywords"]])
        for cat in data["categories"]
    ]


def classify_role(title: str, rules: list[tuple[str, list[re.Pattern[str]]]]) -> str:
    """Assign the first role category whose keyword matches the title."""
    for category, patterns in rules:
        if any(p.search(title) for p in patterns):
            return category
    return "other"


def load_district_ranges(path: Path = DICT_DIR / "hamburg_districts.yaml") -> list[tuple[int, int, str]]:
    """Load postcode ranges for Hamburg districts."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [(int(lo), int(hi), name) for lo, hi, name in data["ranges"]]


def district_for(postcode: str, city: str, ranges: list[tuple[int, int, str]]) -> str:
    """Map a postcode to a Hamburg district; outside Hamburg return the town name."""
    if postcode.isdigit():
        code = int(postcode)
        for lo, hi, name in ranges:
            if lo <= code <= hi:
                return name
    return city.split(",")[0].strip() if city else "Unbekannt"


# --------------------------------------------------------------------------- #
# Loading and deduplication
# --------------------------------------------------------------------------- #

def run_date(run_dir: Path) -> str:
    """Convert a run folder name like ``2026-11-03T184618Z`` to an ISO date."""
    return datetime.strptime(run_dir.name, "%Y-%m-%dT%H%M%SZ").date().isoformat()


def load_search_results(raw_dir: Path) -> dict[str, dict[str, Any]]:
    """Read every run and deduplicate by reference number (pass 1).

    Returns one entry per reference number with the latest listing data and
    the first/last run dates on which it was seen.
    """
    by_ref: dict[str, dict[str, Any]] = {}
    for run_dir in sorted((raw_dir / "search").glob("*T*Z")):
        seen_on = run_date(run_dir)
        for page in sorted(run_dir.glob("*_p*.json")):
            for job in json.loads(page.read_text(encoding="utf-8")).get("ergebnisliste", []):
                ref = job.get("referenznummer")
                if not ref:
                    continue
                entry = by_ref.setdefault(ref, {"first_seen": seen_on})
                entry.update(job=job, last_seen=seen_on)
    return by_ref


def load_detail(raw_dir: Path, refnr: str) -> dict[str, Any]:
    """Return the cached detail record for a reference number, or an empty dict."""
    path = raw_dir / "details" / f"{slugify(refnr)}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def build_posting(refnr: str, entry: dict[str, Any], detail: dict[str, Any],
                  role_rules: list[tuple[str, list[re.Pattern[str]]]],
                  district_ranges: list[tuple[int, int, str]]) -> Posting:
    """Combine listing and detail data for one reference number into a ``Posting``."""
    job = {**entry["job"], **{k: v for k, v in detail.items() if v is not None}}
    title = re.sub(r"\s+", " ", job.get("stellenangebotsTitel", "")).strip()
    description = scrub_contact_data(html_to_text(job.get("stellenangebotsBeschreibung")))
    address = pick_location(job.get("stellenlokationen") or [])
    city, postcode = address.get("ort", ""), address.get("plz", "")
    hours_min, hours_max = parse_weekly_hours(description)
    posted = job.get("datumErsteVeroeffentlichung") or job.get("veroeffentlichungszeitraum", {}).get("von", "")

    return Posting(
        id=refnr,
        title=title,
        company=normalise_company(job.get("firma")),
        city=city,
        postcode=postcode,
        district=district_for(postcode, city, district_ranges),
        posted_date=posted,
        first_seen_date=entry["first_seen"],
        last_seen_date=entry["last_seen"],
        offer_type=(job.get("stellenangebotsart") or "").title(),
        working_time=working_time(job),
        contract=CONTRACT_LABELS.get(job.get("vertragsdauer") or "", "Keine Angabe"),
        hours_min=hours_min,
        hours_max=hours_max,
        work_mode=detect_work_mode(f"{title}\n{description}", bool(job.get("homeofficemoeglich"))),
        role_category=classify_role(title, role_rules),
        source_url=BA_DETAIL_URL.format(refnr=refnr),
        description=description,
    )


def merge_reposts(postings: Iterable[Posting]) -> list[Posting]:
    """Collapse re-posts of the same job (pass 2: same normalised title + company).

    The most recently published version supplies the title, link and text; the
    earliest posted/first-seen dates and the latest last-seen date are kept.
    """
    groups: dict[tuple[str, str], list[Posting]] = {}
    for p in postings:
        groups.setdefault((title_key(p.title), p.company.lower()), []).append(p)

    merged: list[Posting] = []
    for versions in groups.values():
        versions.sort(key=lambda p: (p.posted_date, p.id))
        latest = versions[-1]
        latest.posted_date = min(p.posted_date for p in versions if p.posted_date) if any(
            p.posted_date for p in versions) else ""
        latest.first_seen_date = min(p.first_seen_date for p in versions)
        latest.last_seen_date = max(p.last_seen_date for p in versions)
        if latest.hours_max is None:
            with_hours = [p for p in versions if p.hours_max is not None]
            if with_hours:
                latest.hours_min, latest.hours_max = with_hours[-1].hours_min, with_hours[-1].hours_max
        latest.n_versions = len(versions)
        merged.append(latest)
    return sorted(merged, key=lambda p: (p.posted_date, p.id), reverse=True)


def clean(raw_dir: Path) -> list[Posting]:
    """Run the full cleaning step and return deduplicated postings."""
    role_rules, district_ranges = load_role_rules(), load_district_ranges()
    by_ref = load_search_results(raw_dir)
    postings = [
        build_posting(ref, entry, load_detail(raw_dir, ref), role_rules, district_ranges)
        for ref, entry in by_ref.items()
    ]
    merged = merge_reposts(postings)
    log.info("Reference numbers: %d, after merging re-posts: %d", len(postings), len(merged))
    return merged


def write_interim(postings: list[Posting], out_dir: Path) -> None:
    """Write a CSV without descriptions (for inspection) and JSONL with them."""
    out_dir.mkdir(parents=True, exist_ok=True)
    columns = [f.name for f in fields(Posting) if f.name != "description"]
    with open(out_dir / "postings.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(asdict(p) for p in postings)
    with open(out_dir / "postings.jsonl", "w", encoding="utf-8") as fh:
        for p in postings:
            fh.write(json.dumps(asdict(p), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    result = clean(cfg["paths"]["raw_dir"])
    write_interim(result, cfg["paths"]["raw_dir"].parent / "interim")
