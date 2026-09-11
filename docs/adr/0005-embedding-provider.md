# 0005 — Embedding provider: Gemini (free tier)

- Status: Accepted
- Date: 2026-09-11
- Deciders: Platform team (user decision)

## Context

Phase 3's ingestion pipeline needs to turn legal text chunks into vectors for
pgvector similarity search. The obvious pairings are Voyage AI (Anthropic's
own recommended embeddings partner, paid) or OpenAI's `text-embedding-3-*`
(paid, needs a second LLM vendor account). The user explicitly asked to avoid
any paid services going forward.

## Decision

Use **Google's Gemini embeddings** (`gemini-embedding-001` via the
`google-genai` SDK, Google AI Studio) — usable on a free tier without a
billing account. Output truncated to **768 dimensions** (Matryoshka
representation learning — the model supports 128–3072; 768 is Google's
documented efficiency/quality tradeoff point) to keep the pgvector index
compact.

Config: `GEMINI_API_KEY` (`apps/api/.env`), unset by default — same "build
now, key later" pattern as `ANTHROPIC_API_KEY` in Phase 2. Ingestion/search
calls fail with a clear `embeddings_not_configured` error (recorded on the
`LegalDocument` row for ingestion, or 503 for search) until a key is added,
rather than silently guessing or blocking development.

## Consequences

- Two LLM/AI vendors in play: Anthropic (chat) + Google (embeddings). Neither
  is billed by default; the platform runs at zero cost until keys are added.
- The embedding dimension (768) is baked into the `legal_chunks.embedding`
  pgvector column at migration time (`EMBEDDING_DIM` in
  `app/models/legal_document.py`, migration `0004_legal_sources`). Switching
  embedding models or dimensions later means a new migration **and**
  re-embedding every existing chunk — there's no in-place conversion.
- Gemini's free tier has request-rate and daily-volume limits (enforced by
  Google, not configured here) — fine for development and modest ingestion
  volumes; bulk ingestion of the full source list (Phase 3's "initial
  knowledge base") may need to be paced or the tier upgraded.
- Gemini embeddings are task-asymmetric (`RETRIEVAL_DOCUMENT` vs
  `RETRIEVAL_QUERY`) — `app/services/ingestion/embed.py` always passes the
  right one; get this wrong and retrieval quality degrades silently.

## Alternatives considered

- **Voyage AI** — Anthropic's recommended pairing, but paid (no free tier
  suitable for production use).
- **OpenAI `text-embedding-3-small/large`** — very common, well-documented,
  but paid and a second LLM vendor beyond what Gemini already is.
- **Local (`sentence-transformers`)** — no API key or per-call cost, but adds
  a heavy ML dependency (PyTorch) to the FastAPI container and is lower
  quality / slower than a hosted model; reconsider if free-tier API limits
  become a real constraint.
