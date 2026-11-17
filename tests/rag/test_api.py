"""Tests for the FastAPI app (offline embedder, mocked LLM)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

pytest.importorskip("sqlite_vec")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from rag import store  # noqa: E402
from rag.api import create_app  # noqa: E402
from rag.config import Settings  # noqa: E402
from rag.embeddings import HashingEmbedder  # noqa: E402
from rag.generate import NO_RESULTS, Generator  # noqa: E402
from rag.index import update_index  # noqa: E402
from tests.rag.test_generate import FakeClient  # noqa: E402


@pytest.fixture
def index_file(source, tmp_path: Path) -> Path:
    path = tmp_path / "rag_index.db"
    conn = store.connect(path)
    update_index(source, conn, HashingEmbedder())
    conn.close()
    return path


def client_for(index_file: Path, llm: FakeClient | None = None) -> TestClient:
    settings = Settings(index_db=index_file)
    return TestClient(create_app(settings, HashingEmbedder(), Generator(settings, llm)))


def test_health_reports_index_and_llm_status(index_file, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with client_for(index_file) as client:
        body = client.get("/health").json()
    assert body["status"] == "ok" and body["llm_available"] is False
    assert body["llm_model"] == "claude-opus-5-5"
    assert body["index"]["postings"] == 3 and body["index"]["current"] == 2
    assert body["index"]["data_last_run"].startswith("2026-11-03")


def test_health_without_index(tmp_path) -> None:
    with client_for(tmp_path / "missing.db") as client:
        assert client.get("/health").json()["status"] == "no_index"
        assert client.post("/ask", json={"question": "Werkstudent Java"}).status_code == 503
    assert not (tmp_path / "missing.db").exists()            # read-only: no empty file created


def test_ask_retrieval_only(index_file, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with client_for(index_file) as client:
        body = client.post("/ask", json={"question": "Werkstudent mit Python und Power BI"}).json()
    assert body["mode"] == "retrieval_only" and body["confident"] is True
    source = body["sources"][0]
    assert set(source) == {"title", "company", "district", "posted_date", "first_seen_date", "is_current",
                           "skills", "url", "score"}                    # no description, no contact data
    assert source["company"] == "Hafen Daten GmbH" and "Power BI" in source["skills"]


def test_ask_with_llm(index_file) -> None:
    llm = FakeClient({"found": True, "answer": "Elbe Software AG sucht … [1]", "used_sources": [1]})
    with client_for(index_file, llm) as client:
        body = client.post("/ask", json={"question": "Werkstudent Softwareentwicklung Java", "k": 3}).json()
    assert body["mode"] == "llm" and body["model"] == "claude-opus-5-5"
    assert [s["company"] for s in body["sources"]] == ["Elbe Software AG"]


def test_ask_no_results(index_file) -> None:
    with client_for(index_file, FakeClient()) as client:
        body = client.post("/ask", json={"question": "Bäckerei Brötchen backen"}).json()
    assert body == {"answer": NO_RESULTS, "mode": "no_results", "sources": [], "confident": False,
                    "applied_filters": ["only postings online in the latest run"],
                    "model": None, "note": None}


@pytest.mark.parametrize("payload", [{"question": "ab"}, {"question": "x" * 501},
                                     {"question": "Werkstudent Java", "k": 0},
                                     {"question": "Werkstudent Java", "k": 21}, {}])
def test_invalid_requests_are_rejected(index_file, payload) -> None:
    with client_for(index_file) as client:
        assert client.post("/ask", json=payload).status_code == 422


def test_question_text_is_not_logged(index_file, caplog) -> None:
    secret = "Werkstudent Java für Max Mustermann aus Altona"
    with caplog.at_level(logging.DEBUG), client_for(index_file, FakeClient({"found": False, "answer": "",
                                                                           "used_sources": []})) as client:
        client.post("/ask", json={"question": secret})
    assert "ask: mode=" in caplog.text and "Mustermann" not in caplog.text
