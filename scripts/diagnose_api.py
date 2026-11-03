"""Probe the Jobsuche API from the current network and print what each variant returns.

Used to find out why detail pages fail from GitHub Actions runners while they
work locally. Prints only status codes, content types and response sizes –
never posting content – so the output is safe to keep in public CI logs.

Usage: python scripts/diagnose_api.py
"""

from __future__ import annotations

import base64
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config  # noqa: E402

BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


def probe(label: str, url: str, headers: dict[str, str], params: dict | None = None) -> int:
    """Request a URL once and print a one-line summary; return the status code."""
    time.sleep(1.0)
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
    except requests.RequestException as exc:
        print(f"  {label:<38} ERROR {type(exc).__name__}")
        return 0
    kind = resp.headers.get("content-type", "-").split(";")[0]
    print(f"  {label:<38} {resp.status_code}  {kind:<18} {len(resp.content):>7} bytes")
    return resp.status_code


def main() -> None:
    """Search once, then try several detail-endpoint variants for the first few results."""
    cfg = load_config()
    api = cfg["api"]
    base = api["base_url"]
    key = api["client_id"]
    ours = {"X-API-Key": key, "User-Agent": "hamburg-werkstudent-dashboard (portfolio project)"}

    print("Search:")
    search = requests.get(base + api["search_path"], headers=ours, timeout=30, params={
        "was": "Werkstudent IT", "wo": cfg["search"]["location"],
        "umkreis": cfg["search"]["radius_km"], "size": 5, "page": 1})
    print(f"  {'v6 search':<38} {search.status_code}")
    refs = [j["referenznummer"] for j in search.json().get("ergebnisliste", [])][:3]
    if not refs:
        print("No reference numbers returned – cannot test details.")
        return

    variants = {
        "v4 detail, project UA": ("/pc/v4/jobdetails/{enc}", ours),
        "v4 detail, browser UA": ("/pc/v4/jobdetails/{enc}", {"X-API-Key": key, "User-Agent": BROWSER_UA}),
        "v4 detail, X-API-KEY header": ("/pc/v4/jobdetails/{enc}", {"X-API-KEY": key, "User-Agent": BROWSER_UA}),
        "v3 detail": ("/pc/v3/jobdetails/{enc}", ours),
        "v4 app detail": ("/pc/v4/app/jobdetails/{enc}", ours),
        "v2 detail": ("/pc/v2/jobdetails/{enc}", ours),
    }
    for refnr in refs:
        enc = base64.b64encode(refnr.encode()).decode()
        print(f"Details for posting #{refs.index(refnr) + 1}:")
        for label, (path, headers) in variants.items():
            probe(label, base + path.format(enc=enc), headers)


if __name__ == "__main__":
    main()
