"""Gemini-backed embedding client (Google AI Studio — free tier).

Chosen over paid providers (Voyage/OpenAI) so the platform is runnable at zero
cost; see docs/adr/0005-embedding-provider.md. Configure ``GEMINI_API_KEY`` to
enable it — unset by default, same "build now, key later" pattern as
``ANTHROPIC_API_KEY`` (Phase 2): calls 503 with a clear error until then.

Gemini's embeddings are task-asymmetric — the model is told whether it's
embedding something to store (``RETRIEVAL_DOCUMENT``) or a search query
(``RETRIEVAL_QUERY``); using the right one measurably improves retrieval.
"""

from __future__ import annotations

from google import genai
from google.genai import types as genai_types

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.core.logging import get_logger

logger = get_logger("app.embeddings")

# The API accepts multiple contents per call; keep batches modest to stay
# comfortably inside free-tier rate/size limits.
_MAX_BATCH = 50


def _client(settings: Settings) -> genai.Client:
    if not settings.gemini_api_key:
        raise ServiceUnavailableError(
            "Embeddings aren't configured yet (missing GEMINI_API_KEY).",
            code="embeddings_not_configured",
        )
    return genai.Client(api_key=settings.gemini_api_key)


async def embed_texts(
    texts: list[str], *, settings: Settings, task_type: str = "RETRIEVAL_DOCUMENT"
) -> list[list[float]]:
    if not texts:
        return []

    client = _client(settings)
    vectors: list[list[float]] = []
    for start in range(0, len(texts), _MAX_BATCH):
        batch = texts[start : start + _MAX_BATCH]
        try:
            response = await client.aio.models.embed_content(
                model=settings.embedding_model,
                contents=batch,
                config=genai_types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=settings.embedding_dimensions,
                ),
            )
        except Exception as exc:  # Google SDK: network/auth/rate-limit/quota/etc.
            logger.warning("embedding_failed", error=str(exc))
            raise ServiceUnavailableError(
                "Could not reach the embedding service. Please try again shortly.",
                code="embeddings_error",
            ) from exc

        embeddings = response.embeddings or []
        if len(embeddings) != len(batch):
            raise ServiceUnavailableError(
                "The embedding service returned an unexpected number of results.",
                code="embeddings_error",
            )
        vectors.extend(list(item.values or []) for item in embeddings)

    return vectors


async def embed_query(query: str, *, settings: Settings) -> list[float]:
    vectors = await embed_texts([query], settings=settings, task_type="RETRIEVAL_QUERY")
    return vectors[0]
