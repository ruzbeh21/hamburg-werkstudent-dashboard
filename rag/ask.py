"""Ask a question from the command line: ``python -m rag.ask "Welche Firmen suchen …?"``.

Uses Claude when ANTHROPIC_API_KEY is set, otherwise retrieval-only mode.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from rag import store
from rag.config import get_settings
from rag.embeddings import get_embedder
from rag.generate import Answer, Generator, answer_question


def format_answer(answer: Answer) -> str:
    """Human-readable output: answer, how it was produced, sources with links."""
    lines = [answer.answer, "", f"mode: {answer.mode}" + (f" ({answer.model})" if answer.model else "")]
    if answer.note:
        lines.append(f"note: {answer.note}")
    lines.append("filters: " + "; ".join(answer.applied_filters))
    for number, source in enumerate(answer.sources, start=1):
        lines.append(f"[{number}] {source.title} – {source.company} "
                     f"({source.posted_date or source.first_seen_date})  {source.source_url}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> Answer:
    """Command-line entry point."""
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Ask the job-postings assistant.")
    parser.add_argument("question")
    parser.add_argument("-k", type=int, default=settings.top_k, help="number of postings to retrieve")
    parser.add_argument("--include-expired", action="store_true",
                        help="also search postings no longer online")
    parser.add_argument("--embedder", choices=["e5", "hash"], default="e5")
    parser.add_argument("--json", action="store_true", help="print the full answer as JSON")
    args = parser.parse_args(argv)

    index = store.connect(settings.index_db)
    try:
        answer = answer_question(args.question, index, get_embedder(args.embedder, settings.embed_model),
                                 Generator(settings), k=args.k, include_expired=args.include_expired)
    finally:
        index.close()
    print(json.dumps(asdict(answer), ensure_ascii=False, indent=1) if args.json else format_answer(answer))
    return answer


if __name__ == "__main__":
    main()
