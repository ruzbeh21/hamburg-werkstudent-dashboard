"""Tests for environment overrides in the config loader."""

from __future__ import annotations

import pytest

from src.config import PROJECT_ROOT, load_config


def test_defaults_without_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("JOBSUCHE_API_KEY", "JOBS_DATABASE", "KEEP_DESCRIPTIONS"):
        monkeypatch.delenv(name, raising=False)
    cfg = load_config()
    assert cfg["api"]["client_id"] == "jobboerse-jobsuche"
    assert cfg["paths"]["database"] == PROJECT_ROOT / "data" / "jobs.db"
    assert cfg["database"]["keep_descriptions"] is True


def test_empty_secret_does_not_blank_the_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBSUCHE_API_KEY", "")       # unset GitHub Secret arrives as ""
    assert load_config()["api"]["client_id"] == "jobboerse-jobsuche"


def test_ci_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_DATABASE", "data/history.db")
    monkeypatch.setenv("KEEP_DESCRIPTIONS", "false")
    cfg = load_config()
    assert cfg["paths"]["database"] == PROJECT_ROOT / "data" / "history.db"
    assert cfg["database"]["keep_descriptions"] is False
