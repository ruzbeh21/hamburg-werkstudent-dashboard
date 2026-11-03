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
import re
import time
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
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-API-Key": api_cfg["client_id"],
                "User-Agent": "hamburg-werkstudent-dashboard (portfolio project)",
            }
        )

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


def collect_details(client: JobsucheClient, refs: set[str], details_dir: Path) -> int:
    """Fetch details for reference numbers not cached yet; return how many were fetched."""
    fetched = 0
    for refnr in sorted(refs):
        target = details_dir / f"{slugify(refnr)}.json"
        if target.exists():
            continue
        try:
            detail = client.details(refnr)
        except requests.RequestException as exc:
            log.warning("Detail fetch failed for %s: %s", refnr, exc)
            continue
        if detail is not None:
            write_json(target, detail)
            fetched += 1
    return fetched


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

    details_fetched = 0
    if cfg["details"]["fetch"]:
        details_fetched = collect_details(client, all_refs, raw_dir / "details")

    write_json(run_dir / "manifest.json", {
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "location": cfg["search"]["location"],
        "radius_km": cfg["search"]["radius_km"],
        "postings_per_term": per_term,
        "unique_postings": len(all_refs),
        "details_fetched": details_fetched,
    })
    log.info("Unique postings: %d, new details fetched: %d", len(all_refs), details_fetched)
    return run_dir


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
