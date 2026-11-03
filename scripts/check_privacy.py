"""Pre-publish check: scan files that would be committed for personal data and secrets.

Uses ``git ls-files`` (tracked + untracked, respecting .gitignore) when inside a
git repository, otherwise walks the project and skips ignored folders.
Exits with status 1 if anything suspicious is found.
"""

from __future__ import annotations

import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.clean import EMAIL_RE, PHONE_RE  # noqa: E402

SKIP_DIRS = {".git", "data", "__pycache__", ".pytest_cache", ".venv"}
TEXT_SUFFIXES = {".py", ".sql", ".yaml", ".yml", ".json", ".csv", ".md", ".html", ".css", ".js", ".txt", ""}
# Fake addresses used in tests and docs.
ALLOWED_EMAIL_DOMAINS = ("firma.de", "example.org", "example.com", "users.noreply.github.com",
                         "anthropic.com")
SECRET_RE = re.compile(
    r"(?:api[_-]?key|secret|token|password|passwort)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"
    r"|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----",
    re.IGNORECASE,
)


def files_to_check() -> list[Path]:
    """List files that git would publish, or all project files outside ignored dirs."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
        return [ROOT / line for line in out.splitlines() if line]
    except (subprocess.CalledProcessError, FileNotFoundError):
        files = [p for p in ROOT.rglob("*")
                 if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(ROOT).parts)]
        # data/ is skipped as a whole, but the history database is meant to be published.
        history = ROOT / "data" / "history.db"
        return files + [history] if history.exists() else files


def scan_database(path: Path) -> list[str]:
    """A published SQLite file must not contain any description text."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        with_text = conn.execute(
            "SELECT COUNT(*) FROM postings WHERE description IS NOT NULL AND description <> ''"
        ).fetchone()[0]
        conn.close()
    except sqlite3.Error as exc:
        return [f"could not inspect database: {exc}"]
    return [f"{with_text} posting(s) still contain description text"] if with_text else []


def scan(path: Path) -> list[str]:
    """Return human-readable findings for one file."""
    if path.suffix == ".db" and path.exists():
        return scan_database(path)
    if path.suffix not in TEXT_SUFFIXES or not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    findings: list[str] = []
    without_urls = re.sub(r"https?://\S+", "", text)
    for match in EMAIL_RE.finditer(without_urls):
        address = re.sub(r"\s*[(\[]dot[)\]]\s*", ".", match.group().lower())
        if not address.endswith(ALLOWED_EMAIL_DOMAINS):
            findings.append(f"email-like text: {match.group()[:3]}…")
    if path.suffix not in {".py", ".sql"}:          # code contains digit-heavy regexes
        for match in PHONE_RE.finditer(without_urls):
            findings.append(f"phone-like number: {match.group()[:4]}…")
    for match in SECRET_RE.finditer(text):
        findings.append(f"possible secret: {match.group()[:12]}…")
    return findings


def main() -> int:
    """Scan all files and print a report; return the process exit code."""
    problems = {p: f for p in files_to_check() if (f := scan(p))}
    for path, findings in problems.items():
        for finding in findings:
            print(f"{path.relative_to(ROOT)}: {finding}")
    if problems:
        print(f"\n{sum(len(f) for f in problems.values())} finding(s). Do not publish.")
        return 1
    print("Privacy check passed: no emails, phone numbers or secrets found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
