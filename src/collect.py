"""Step 1 – collect job postings from the Bundesagentur für Arbeit Jobsuche API.

Each run writes the raw search pages into ``data/raw/search/<timestamp>/`` and a
``manifest.json`` describing the run, so running the collector daily builds a
time series. Job details are cached per reference number in ``data/raw/details/``
and only fetched once.

Raw files may contain recruiter contact data and are git-ignored; ``clean.py``
scrubs them before anything leaves the machine.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from src.config import load_config

log = logging.getLogger(__name__)


class JobsucheClient:
    """Small HTTP client with a fixed pause between requests and simple retries."""

    def __init__(self, api_cfg: dict[str, Any]) -> None:
        self.base_url: str = api_cfg["base_url"]
        self.search_path: str = api_cfg["search_path"]
        self.detail_path: str = api_cfg["detail_path"]
        self.timeout: float = api_cfg["timeout_seconds"]
        self.sleep: float = api_cfg["sleep_seconds"]
        self.max_retries: int = api_cfg["max_retries"]
        self.headers = {
            "X-API-Key": api_cfg["client_id"],
            "User-Agent": "hamburg-werkstudent-dashboard (portfolio project)",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def reset_session(self) -> None:
        """Drop the connection pool and cookies and start a fresh session."""
        self.session.close()
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """GET a URL and return parsed JSON, or ``None`` on a 404."""
        for attempt in range(1, self.max_retries + 1):
            time.sleep(self.sleep)
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 404:
                return None
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                wait = self.sleep * 2**attempt
                log.warning("HTTP %s, retrying in %.0fs", resp.status_code, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        return None

    def search(self, term: str, location: str, radius_km: int, page: int, size: int,
               published_since_days: int) -> dict[str, Any]:
        """Return one page of search results."""
        params = {
            "was": term,
            "wo": location,
            "umkreis": radius_km,
            "page": page,
            "size": size,
            "veroeffentlichtseit": published_since_days,
        }
        return self._get(self.base_url + self.search_path, params) or {}

    def details(self, refnr: str) -> dict[str, Any] | None:
        """Return the detail record for a posting, addressed by base64(refnr)."""
        encoded = base64.b64encode(refnr.encode()).decode()
        return self._get(f"{self.base_url}{self.detail_path}/{encoded}")


def slugify(text: str) -> str:
    """Turn a search term into a safe file name part."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def write_json(path: Path, data: Any) -> None:
    """Write JSON with UTF-8 and stable indentation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def collect_term(client: JobsucheClient, term: str, search_cfg: dict[str, Any],
                 run_dir: Path) -> list[str]:
    """Page through all results for one term, save each page, return reference numbers."""
    refs: list[str] = []
    for page in range(1, search_cfg["max_pages_per_term"] + 1):
        data = client.search(term, search_cfg["location"], search_cfg["radius_km"], page,
                             search_cfg["page_size"], search_cfg["published_since_days"])
        results = data.get("ergebnisliste", [])
        write_json(run_dir / f"{slugify(term)}_p{page}.json", data)
        refs += [job["referenznummer"] for job in results if "referenznummer" in job]
        total = data.get("maxErgebnisse", 0)
        if len(results) < search_cfg["page_size"] or page * search_cfg["page_size"] >= total:
            break
    return refs


def collect_details(client: JobsucheClient, refs: set[str], details_dir: Path,
                    retry_passes: int = 2, retry_wait: float = 30.0) -> Counter[str]:
    """Fetch details for reference numbers not cached yet.

    A posting that search returned seconds ago should have a detail page, so a
    404 or error is retried in up to ``retry_passes`` extra passes, each after a
    pause and with a fresh session. Returns counts of ``fetched``, ``cached``,
    ``not_found`` and ``error`` (the last two after all retries).
    """
    stats: Counter[str] = Counter()
    pending = []
    for refnr in sorted(refs):
        if (details_dir / f"{slugify(refnr)}.json").exists():
            stats["cached"] += 1
        else:
            pending.append(refnr)

    outcome: dict[str, str] = {}
    for attempt in range(retry_passes + 1):
        if attempt:
            if not pending:
                break
            log.info("Retrying %d missing details in %.0fs (pass %d)", len(pending), retry_wait, attempt)
            time.sleep(retry_wait)
            client.reset_session()
        still_missing = []
        for refnr in pending:
            try:
                detail = client.details(refnr)
            except requests.RequestException as exc:
                outcome[refnr] = "error"
                log.debug("Detail fetch failed for %s: %s", refnr, exc)
                still_missing.append(refnr)
                continue
            if detail is None:
                outcome[refnr] = "not_found"
                still_missing.append(refnr)
                continue
            write_json(details_dir / f"{slugify(refnr)}.json", detail)
            stats["fetched"] += 1
        pending = still_missing

    for refnr in pending:
        stats[outcome[refnr]] += 1
    return stats


def detail_coverage(stats: Counter[str]) -> float:
    """Share of postings that have a detail page (fetched now or cached earlier)."""
    total = sum(stats.values())
    return (stats["fetched"] + stats["cached"]) / total if total else 1.0


def warn_if_low_coverage(stats: Counter[str], threshold: float = 0.8) -> None:
    """Log a warning – and a GitHub Actions annotation in CI – if many details are missing."""
    coverage = detail_coverage(stats)
    if coverage >= threshold:
        return
    message = (f"Only {coverage:.0%} of postings have a detail page "
               f"({stats['not_found']} not found, {stats['error']} errors). "
               "Skills for the missing postings will be extracted later or not at all.")
    log.warning(message)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning title=Low detail coverage::{message}")


def run() -> Path:
    """Run one collection and return the directory with this run's raw files."""
    cfg = load_config()
    client = JobsucheClient(cfg["api"])
    started = datetime.now(timezone.utc)
    raw_dir: Path = cfg["paths"]["raw_dir"]
    run_dir = raw_dir / "search" / started.strftime("%Y-%m-%dT%H%M%SZ")

    per_term: dict[str, int] = {}
    all_refs: set[str] = set()
    for term in cfg["search"]["terms"]:
        refs = collect_term(client, term, cfg["search"], run_dir)
        per_term[term] = len(refs)
        all_refs.update(refs)
        log.info("%-25s %4d postings", term, len(refs))

    if not all_refs:
        # An outage or API change would otherwise mark every posting as offline
        # and publish an empty dashboard. Fail loudly instead.
        raise RuntimeError("API returned no postings for any search term – aborting run")

    stats: Counter[str] = Counter()
    if cfg["details"]["fetch"]:
        stats = collect_details(client, all_refs, raw_dir / "details",
                                cfg["details"]["retry_passes"], cfg["details"]["retry_wait_seconds"])
        warn_if_low_coverage(stats)

    write_json(run_dir / "manifest.json", {
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "location": cfg["search"]["location"],
        "radius_km": cfg["search"]["radius_km"],
        "postings_per_term": per_term,
        "unique_postings": len(all_refs),
        "details_fetched": stats["fetched"],
        "details": {key: stats[key] for key in ("fetched", "cached", "not_found", "error")},
    })
    log.info("Unique postings: %d, details fetched %d, cached %d, not found %d, errors %d",
             len(all_refs), stats["fetched"], stats["cached"], stats["not_found"], stats["error"])
    return run_dir


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
