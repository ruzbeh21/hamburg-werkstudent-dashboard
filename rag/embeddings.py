"""Text embeddings: the real multilingual E5 model, and a tiny deterministic stand-in for tests.

Why ``intfloat/multilingual-e5-small``: it runs locally on a CPU (free, no API key),
handles German and English in one vector space (so an English question finds German
postings), and its 384-dimensional vectors keep the index small. E5 was trained with
the prefixes ``query: `` and ``passage: `` – leaving them out measurably hurts retrieval.
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Protocol

import numpy as np

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

# Known output sizes, so the index schema can be created without loading the model.
KNOWN_DIMS = {"intfloat/multilingual-e5-small": 384, "intfloat/multilingual-e5-base": 768}


class Embedder(Protocol):
    """Anything that turns texts into L2-normalised float32 vectors."""

    name: str
    dim: int

    def embed_passages(self, texts: list[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


class E5Embedder:
    """Multilingual E5 via sentence-transformers. The model is loaded on first use."""

    def __init__(self, model_name: str = "intfloat/multilingual-e5-small", batch_size: int = 32) -> None:
        self.name = model_name
        self.batch_size = batch_size
        self._model: SentenceTransformer | None = None
        self.dim = KNOWN_DIMS.get(model_name) or self._load().get_embedding_dimension()

    def _load(self) -> SentenceTransformer:
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # heavy import, only when needed
            self._model = SentenceTransformer(self.name, device="cpu")
        return self._model

    def _encode(self, texts: list[str]) -> np.ndarray:
        vectors = self._load().encode(texts, batch_size=self.batch_size, normalize_embeddings=True,
                                      show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        """Embed documents (prefix ``passage: ``)."""
        return self._encode([f"passage: {t}" for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        """Embed a search question (prefix ``query: ``)."""
        return self._encode([f"query: {text}"])[0]


class HashingEmbedder:
    """Deterministic bag-of-words vectors via feature hashing – for tests and offline CI.

    Not semantically smart, but texts sharing words get similar vectors, which is
    enough to test indexing and retrieval logic without downloading a model.
    """

    def __init__(self, dim: int = 64) -> None:
        self.name = f"hashing-{dim}"
        self.dim = dim

    def _vector(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        for token in re.findall(r"\w+", text.lower()):
            bucket = int.from_bytes(hashlib.md5(token.encode()).digest()[:4], "little") % self.dim
            vec[bucket] += 1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm else vec

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return np.stack([self._vector(t) for t in texts]) if texts else np.zeros((0, self.dim), np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self._vector(text)


def get_embedder(kind: str, model_name: str) -> Embedder:
    """Factory used by the CLI and the API: ``e5`` (default) or ``hash``."""
    if kind == "hash":
        return HashingEmbedder()
    return E5Embedder(model_name)
