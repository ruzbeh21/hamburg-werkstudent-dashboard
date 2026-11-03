"""Tests for detail fetching: retries, outcome counts and the coverage warning."""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from src.collect import collect_details, detail_coverage, slugify, warn_if_low_coverage


class FakeClient:
    """Answers detail requests from a script: one outcome per call and reference number."""

    def __init__(self, script: dict[str, list[str]]) -> None:
        self.script = script
        self.resets = 0

    def details(self, refnr: str) -> dict | None:
        outcome = self.script[refnr].pop(0)
        if outcome == "error":
            raise requests.ConnectionError("boom")
        return None if outcome == "404" else {"referenznummer": refnr}

    def reset_session(self) -> None:
        self.resets += 1


def test_retries_recover_transient_failures(tmp_path: Path) -> None:
    (tmp_path / f"{slugify('CACHED-1')}.json").write_text("{}")
    client = FakeClient({
        "OK-1": ["200"],
        "FLAKY-1": ["404", "200"],            # recovers in the first retry pass
        "FLAKY-2": ["error", "error", "200"],  # recovers in the second
        "GONE-1": ["404", "404", "404"],       # really missing
    })
    stats = collect_details(client, {"OK-1", "FLAKY-1", "FLAKY-2", "GONE-1", "CACHED-1"},
                            tmp_path, retry_passes=2, retry_wait=0)
    assert stats == {"fetched": 3, "cached": 1, "not_found": 1}
    assert client.resets == 2
    assert (tmp_path / f"{slugify('FLAKY-2')}.json").exists()


def test_no_retry_pass_when_everything_worked(tmp_path: Path) -> None:
    client = FakeClient({"A": ["200"], "B": ["200"]})
    stats = collect_details(client, {"A", "B"}, tmp_path, retry_passes=2, retry_wait=0)
    assert stats["fetched"] == 2 and client.resets == 0
    assert detail_coverage(stats) == 1.0


def test_low_coverage_emits_github_annotation(monkeypatch: pytest.MonkeyPatch,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    from collections import Counter
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    warn_if_low_coverage(Counter(fetched=1, not_found=101))
    assert "::warning title=Low detail coverage::" in capsys.readouterr().out
    warn_if_low_coverage(Counter(fetched=95, cached=5))
    assert capsys.readouterr().out == ""
