"""Probe the Jobsuche API from the current network and print what each variant returns.

Used to find out why detail pages fail from GitHub Actions runners while they
work locally. Prints only status codes, content types and response sizes –
never posting content – so the output is safe to keep in public CI logs.

Usage: python scripts/diagnose_api.py            # endpoint variants
       python scripts/diagnose_api.py --burst 40 1  # 40 details, 1 s apart
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


def burst(n: int, pause: float, use_session: bool = False) -> None:
    """Fetch ``n`` details in a row like the pipeline does and print the status sequence.

    With ``use_session`` one ``requests.Session`` is reused (keep-alive + cookies),
    exactly like ``collect.py``; otherwise every request is independent.

    Then waits and retries the first failure, to tell rate limiting apart from
    postings that really are gone.
    """
    cfg = load_config()
    api = cfg["api"]
    headers = {"X-API-Key": api["client_id"], "User-Agent": "hamburg-werkstudent-dashboard (portfolio project)"}
    http = requests.Session() if use_session else requests
    refs: set[str] = set()
    for term in cfg["search"]["terms"]:
        time.sleep(1.0)
        data = http.get(api["base_url"] + api["search_path"], headers=headers, timeout=30, params={
            "was": term, "wo": cfg["search"]["location"], "umkreis": cfg["search"]["radius_km"],
            "size": 50, "page": 1}).json()
        refs.update(j["referenznummer"] for j in data.get("ergebnisliste", []))
    ordered = sorted(refs)[:n]
    print(f"Burst: {len(ordered)} details, {pause}s apart, {'one shared Session' if use_session else 'independent requests'}")
    if use_session:
        print("  cookies set by search responses (names only):", sorted(c.name for c in http.cookies) or "none")
    codes: list[int] = []
    for i, refnr in enumerate(ordered):
        time.sleep(pause)
        enc = base64.b64encode(refnr.encode()).decode()
        resp = http.get(f"{api['base_url']}{api['detail_path']}/{enc}", headers=headers, timeout=30)
        codes.append(resp.status_code)
        if resp.status_code != 200 and codes.count(resp.status_code) == 1:
            retry_after = resp.headers.get("retry-after", "-")
            print(f"  first {resp.status_code} at request {i + 1} (retry-after: {retry_after})")
    print("  sequence:", " ".join(str(c) for c in codes))
    failed = [r for r, c in zip(ordered, codes) if c != 200]
    if failed:
        print("  waiting 60s, then retrying the first failure …")
        time.sleep(60)
        enc = base64.b64encode(failed[0].encode()).decode()
        resp = requests.get(f"{api['base_url']}{api['detail_path']}/{enc}", headers=headers, timeout=30)
        print(f"  retry after 60s: {resp.status_code}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--burst":
        burst(int(sys.argv[2]) if len(sys.argv) > 2 else 40,
              float(sys.argv[3]) if len(sys.argv) > 3 else 1.0,
              use_session="--session" in sys.argv)
    else:
        main()
