"""Tests for the cleaning step. Examples are modelled on real postings (anonymised)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.clean import (
    Posting,
    classify_role,
    detect_work_mode,
    district_for,
    html_to_text,
    load_district_ranges,
    load_role_rules,
    load_search_results,
    merge_reposts,
    normalise_company,
    parse_weekly_hours,
    pick_location,
    scrub_contact_data,
    title_key,
)


def make_posting(**overrides: object) -> Posting:
    """Build a Posting with sensible defaults for tests."""
    base: dict[str, object] = dict(
        id="1", title="Werkstudent IT (m/w/d)", company="ACME GmbH", city="Hamburg",
        postcode="20095", district="Hamburg-Mitte", posted_date="2026-10-01",
        first_seen_date="2026-11-01", last_seen_date="2026-11-01", offer_type="Arbeit",
        working_time="Teilzeit", contract="Befristet", hours_min=None, hours_max=None,
        work_mode="not_stated", role_category="it_ops", source_url="https://example.org",
    )
    base.update(overrides)
    return Posting(**base)  # type: ignore[arg-type]


# --- contact data ---------------------------------------------------------- #

def test_scrub_drops_contact_lines_and_name_above() -> None:
    text = "Wir freuen uns auf dich!\nMaxi Muster\nE-Mail: maxi.muster@firma.de\nTel.: 040 123 456 78"
    out = scrub_contact_data(text)
    assert "@" not in out and "123 456" not in out and "Muster" not in out
    assert out == "Wir freuen uns auf dich!"


def test_scrub_inline_for_long_single_line_text() -> None:
    long_text = "Aufgaben " * 50 + "Fragen beantwortet Frau Beispiel unter jobs@firma.de gern."
    out = scrub_contact_data(long_text)
    assert out.startswith("Aufgaben")                      # text is kept
    assert "Beispiel" not in out and "jobs@firma.de" not in out
    assert "[Name entfernt]" in out and "[Kontakt entfernt]" in out


def test_scrub_handles_obfuscated_email_and_contact_intro() -> None:
    out = scrub_contact_data("Ansprechpartnerin: Erika Mustermann, bewerbung(at)firma(dot)de, " + "x" * 300)
    assert "Mustermann" not in out and "firma(dot)de" not in out


def test_scrub_keeps_dates_and_postcodes() -> None:
    text = "Start: 01.10.2026 in 20095 Hamburg, 16-20 Std./Woche"
    assert scrub_contact_data(text) == text


def test_html_to_text_handles_entities_and_nbsp() -> None:
    assert html_to_text("<p>Python&nbsp;&amp;\xa0SQL</p><br>Git") == "Python & SQL\n\nGit"
    assert html_to_text(None) == ""


# --- normalisation and deduplication --------------------------------------- #

@pytest.mark.parametrize("raw, expected", [
    ("Airbus Operations GmbH Werk Bremen", "Airbus Operations GmbH"),
    ("Tchibo GmbH Abteilung HRO/HRO-P", "Tchibo GmbH"),
    ("FERCHAU GmbH Niederlassung Hamburg-City", "FERCHAU GmbH"),
    ("The Quality Group Gmbh", "The Quality Group GmbH"),
    (None, "Unbekannt"),
])
def test_normalise_company(raw: str | None, expected: str) -> None:
    assert normalise_company(raw) == expected


def test_title_key_ignores_gender_markers_and_ad_numbers() -> None:
    a = title_key("Werkstudent*in Produktmanagement (m/w/d)")
    b = title_key("Werkstudentin Produktmanagement (w/m/d) 315")
    c = title_key("Werkstudent:in Produktmanagement m/w/d")
    assert a == b == c == "werkstudent produktmanagement"


def test_merge_reposts_keeps_earliest_dates_and_latest_version() -> None:
    old = make_posting(id="A", posted_date="2026-08-05", first_seen_date="2026-08-06",
                       title="Werkstudent*in Produktmanagement (m/w/d)", hours_min=16, hours_max=20)
    new = make_posting(id="B", posted_date="2026-11-03", first_seen_date="2026-11-03",
                       last_seen_date="2026-11-04", title="Werkstudentin Produktmanagement (w/m/d)")
    other = make_posting(id="C", title="Werkstudent Data Analytics (m/w/d)")
    merged = {p.id: p for p in merge_reposts([old, new, other])}
    assert set(merged) == {"B", "C"}
    assert merged["B"].posted_date == "2026-08-05"
    assert merged["B"].first_seen_date == "2026-08-06"
    assert merged["B"].last_seen_date == "2026-11-04"
    assert merged["B"].n_versions == 2
    assert (merged["B"].hours_min, merged["B"].hours_max) == (16, 20)   # filled from older version


def test_same_title_at_different_companies_is_not_merged() -> None:
    a = make_posting(id="A", company="ACME GmbH")
    b = make_posting(id="B", company="Other AG")
    assert len(merge_reposts([a, b])) == 2


def test_load_search_results_dedups_across_terms_and_runs(tmp_path: Path) -> None:
    job = {"referenznummer": "10001-1-S", "stellenangebotsTitel": "Werkstudent IT"}
    for run, term in [("2026-11-01T060000Z", "it"), ("2026-11-01T060000Z", "data"),
                      ("2026-11-03T060000Z", "it")]:
        folder = tmp_path / "search" / run
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{term}_p1.json").write_text(json.dumps({"ergebnisliste": [job]}))
    result = load_search_results(tmp_path)
    assert list(result) == ["10001-1-S"]
    assert result["10001-1-S"]["first_seen"] == "2026-11-01"
    assert result["10001-1-S"]["last_seen"] == "2026-11-03"


# --- field extraction ------------------------------------------------------ #

@pytest.mark.parametrize("text, expected", [
    ("Du arbeitest 16-20 Std./Woche bei uns.", (16, 20)),
    ("eine 20-Stunden-Woche mit Gleitzeit", (20, 20)),
    ("zwischen 3 und 19,5 Stunden pro Woche (in den Semesterferien sogar bis zu 40 Stunden)", (3, 20)),
    ("in Teilzeit (20,0 Stunden/Woche)", (20, 20)),
    ("Working student, part-time, 20 hours", (20, 20)),
    ("bis zu 20 Stunden pro Woche. Als Praktikant hast du eine 37-Stunden-Woche.", (20, 20)),
    ("Gehalt: 16EUR/h im ersten Jahr", (None, None)),
    ("24 h Support-Hotline", (None, None)),
])
def test_parse_weekly_hours(text: str, expected: tuple[int | None, int | None]) -> None:
    assert parse_weekly_hours(text) == expected


@pytest.mark.parametrize("text, flag, expected", [
    ("Wir arbeiten 100% remote", False, "remote"),
    ("Hybrides Arbeiten und mobiles Arbeiten möglich", False, "hybrid"),
    ("Büro in der HafenCity", True, "hybrid"),
    ("Büro in der HafenCity", False, "not_stated"),
])
def test_detect_work_mode(text: str, flag: bool, expected: str) -> None:
    assert detect_work_mode(text, flag) == expected


@pytest.mark.parametrize("title, expected", [
    ("Werkstudent Data Analytics (m/w/d)", "data"),
    ("Werkstudent KI & Prozessoptimierung", "data"),
    ("Werkstudent Softwareentwicklung (m/w/d)", "software"),
    ("Werkstudent - Java OpenJDK (m/w/divers)", "software"),
    ("Werkstudent IT-Support (m/w/d)", "it_ops"),
    ("Werkstudent Net-Sec-Automation & Monitoring", "it_ops"),
    ("Werkstudent (m/w/d) im Bereich Prozessautomatisierung RPA", "software"),
    ("Werkstudent im Bereich Tax / Steuerberatung", "other"),
    ("Working Student Brand Marketing (gn)", "other"),
])
def test_classify_role(title: str, expected: str) -> None:
    assert classify_role(title, load_role_rules()) == expected


def test_district_mapping_and_fallback() -> None:
    ranges = load_district_ranges()
    assert district_for("20457", "Hamburg", ranges) == "Hamburg-Mitte"
    assert district_for("22769", "Hamburg", ranges) == "Altona"
    assert district_for("25451", "Quickborn, Kreis Pinneberg", ranges) == "Quickborn"
    assert district_for("", "", ranges) == "Unbekannt"


def test_pick_location_prefers_hamburg() -> None:
    munich = {"adresse": {"ort": "München"}, "breite": 48.14, "laenge": 11.58}
    hamburg = {"adresse": {"ort": "Hamburg"}, "breite": 53.56, "laenge": 9.99}
    no_coords = {"adresse": {"ort": "Irgendwo"}}
    assert pick_location([munich, no_coords, hamburg])["ort"] == "Hamburg"
    assert pick_location([]) == {}
