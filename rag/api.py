"""HTTP API for the assistant: ``uvicorn rag.api:app``.

* ``POST /ask``  – question in, grounded answer plus cited postings out.
* ``GET /health`` – index size, data freshness and whether generation is available.

Design decisions:
* The embedding model is loaded **once at startup** (lifespan), so the first request is
  not slowed down by loading it; the index is opened read-only **per request**, because
  SQLite connections should not be shared across FastAPI's worker threads.
* Request and response bodies are Pydantic models – they validate input (length, k range)
  and document the API automatically at ``/docs``.
* The question text is never logged; only the mode, number of sources and latency.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from rag import store
from rag.config import Settings, get_settings
from rag.embeddings import Embedder, get_embedder
from rag.generate import Answer, Generator, answer_question
from rag.retrieve import Hit

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- models

class AskRequest(BaseModel):
    """A question, optionally with the number of postings to retrieve."""

    question: str = Field(min_length=3, max_length=500,
                          examples=["Welche Firmen in Hamburg suchen Werkstudenten mit Python und Power BI?"])
    k: int = Field(default=6, ge=1, le=20, description="number of postings to retrieve")
    include_expired: bool = Field(default=False, description="also search postings no longer online")


class Source(BaseModel):
    """A cited posting, with a link to the original ad on the Bundesagentur für Arbeit job board."""

    title: str
    company: str
    district: str | None
    posted_date: str | None
    first_seen_date: str
    is_current: bool
    skills: list[str]
    url: str
    score: float

    @classmethod
    def from_hit(cls, hit: Hit) -> Source:
        return cls(title=hit.title, company=hit.company, district=hit.district, posted_date=hit.posted_date,
                   first_seen_date=hit.first_seen_date, is_current=hit.is_current,
                   skills=[s for s in hit.skills.split(", ") if s], url=hit.source_url, score=hit.score)


class AskResponse(BaseModel):
    """The answer, how it was produced, and its sources."""

    answer: str
    mode: Literal["llm", "retrieval_only", "no_results"]
    sources: list[Source]
    applied_filters: list[str]
    confident: bool
    model: str | None = None
    note: str | None = None

    @classmethod
    def from_answer(cls, answer: Answer) -> AskResponse:
        return cls(answer=answer.answer, mode=answer.mode,
                   sources=[Source.from_hit(h) for h in answer.sources],
                   applied_filters=answer.applied_filters, confident=answer.confident, model=answer.model,
                   note=answer.note)


class IndexInfo(BaseModel):
    postings: int
    current: int
    chunks: int
    embed_model: str | None
    data_last_run: str | None


class HealthResponse(BaseModel):
    status: Literal["ok", "no_index"]
    index: IndexInfo | None
    llm_available: bool
    llm_model: str


# --------------------------------------------------------------------------- app

def create_app(settings: Settings | None = None, embedder: Embedder | None = None,
               generator: Generator | None = None) -> FastAPI:
    """Build the app; tests inject a small embedder and a mocked generator."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        kind = os.environ.get("RAG_EMBEDDER", "e5")          # "hash" for tests and quick local checks
        app.state.embedder = embedder or get_embedder(kind, settings.embed_model)
        app.state.generator = generator or Generator(settings)
        app.state.embedder.embed_query("warm-up")           # load the model now, not on the first request
        yield

    app = FastAPI(title="Hamburg Werkstudent Q&A", version="1.0",
                  description="Answers questions about Werkstudent postings in Hamburg, grounded in the "
                              "daily-collected postings of the Bundesagentur für Arbeit job board.",
                  lifespan=lifespan)

    @app.get("/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        state = request.app.state
        try:
            conn = store.connect_readonly(state.settings.index_db)
        except FileNotFoundError:
            return HealthResponse(status="no_index", index=None, llm_available=state.generator.available,
                                  llm_model=state.settings.llm_model)
        try:
            info = IndexInfo(**store.counts(conn), embed_model=store.get_meta(conn, "embed_model"),
                             data_last_run=store.get_meta(conn, "source_last_run"))
        finally:
            conn.close()
        return HealthResponse(status="ok", index=info, llm_available=state.generator.available,
                              llm_model=state.settings.llm_model)

    @app.post("/ask", response_model=AskResponse)
    def ask(body: AskRequest, request: Request) -> AskResponse:
        state = request.app.state
        started = time.perf_counter()
        try:
            conn = store.connect_readonly(state.settings.index_db)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail="index not built yet") from exc
        try:
            answer = answer_question(body.question, conn, state.embedder, state.generator, k=body.k,
                                     include_expired=body.include_expired)
        finally:
            conn.close()
        log.info("ask: mode=%s sources=%d ms=%d", answer.mode, len(answer.sources),
                 (time.perf_counter() - started) * 1000)
        return AskResponse.from_answer(answer)

    return app


app = create_app()
