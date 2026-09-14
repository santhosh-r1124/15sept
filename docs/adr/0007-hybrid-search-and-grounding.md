# 0007 — Hybrid search via RRF (not a reranker model), and a retrieval-based grounding guardrail

- Status: Accepted
- Date: 2026-09-14
- Deciders: Platform team

## Context

Phase 4 needed to turn Phase 3's plain vector search into "production RAG":
hybrid (keyword + vector) search, reranking, and wiring retrieval into the
Phase 2 chat pipeline so answers are grounded in `legal_chunks` instead of the
model's own training data — the FRD's non-negotiable "grounded, not guessed"
rule (docs/roadmap.md).

The user's standing instruction from Phase 3 — no paid services for the rest
of this project — applies here too. The two usual ways to build "hybrid +
rerank" both cost money or infrastructure the platform doesn't have yet:

- A dedicated reranker model (Cohere Rerank, Voyage rerank-2, a self-hosted
  cross-encoder) — paid APIs, or a model to host and serve.
- An additional LLM call to have Claude re-score/re-order candidates —
  works, but doubles LLM spend per chat message for a step that a much
  cheaper technique already handles adequately.

## Decision

**Hybrid search + fusion, not hybrid search + a reranker model:**

- Two independent rankers over `legal_chunks`: pgvector cosine similarity
  (semantic), and Postgres full-text search over a generated `tsvector`
  column (`content_tsv`, GIN-indexed — migration 0005) via
  `plainto_tsquery`/`ts_rank` (lexical/keyword).
- The two ranked ID lists are combined with **Reciprocal Rank Fusion**
  (`app/services/rag/retrieval.py::reciprocal_rank_fusion`) —
  `score(d) = Σ 1/(k + rank_i(d))` across whichever lists `d` appears in,
  `k=60` (the constant from the original RRF paper; the paper found result
  quality insensitive to k in a wide range around that value, so it needs no
  corpus-specific tuning — useful here since there's no real corpus loaded
  yet to tune against).

This is the whole "hybrid search + rerank" stage. It costs nothing beyond one
extra Postgres query, needs no model or training data, and is a standard,
well-understood technique (used by Postgres/pgvector "hybrid search"
reference implementations, e.g. Supabase's, for the same reason).

**Grounding guardrail is retrieval-based, not a distance threshold:**

An obvious-looking alternative — "only answer if the top vector match's
cosine distance is below some threshold" — was considered and rejected: with
no real corpus loaded yet (Phase 3's known gap), there's no data to calibrate
a threshold against, and an uncalibrated number is worse than no guardrail at
all — it would either block good answers or wave through bad ones by
accident, for reasons nobody could point to.

Instead the guardrail is structural: `hybrid_search` returning **zero**
chunks (empty corpus, or a genuinely unrelated question) short-circuits
straight to `INSUFFICIENT_EVIDENCE_MESSAGE` — no LLM call at all. When it
returns chunks, they're the only thing the model is allowed to answer from:
the system prompt (`app.services.llm._GROUNDED_ANSWER_SYSTEM_PROMPT`) requires
every claim to carry a `[n]` citation into the supplied sources, and instructs
the model to say plainly what the sources don't cover rather than fill gaps —
a second, prompt-level layer behind the hard retrieval gate.

`GEMINI_API_KEY` unset (or the embeddings call failing) is treated the same
way as "no matching sources": from the user's side these are
indistinguishable ("the platform can't ground this answer right now"), so
`app/api/v1/routes/chat.py::_retrieve` catches `ServiceUnavailableError` from
retrieval and falls back to the insufficient-evidence message instead of
surfacing a raw 503. This is a deliberate trade: it's honest (no answer is
fabricated) and gives a clean UX either way, at the cost of hiding a
misconfiguration behind a generic reply — mitigated by logging
`retrieval_unavailable` with the error code for diagnosis.

**`hybrid_search` is additive, not a replacement for Phase 3's `semantic_search`:**

`app/services/ingestion/search.py::semantic_search` (the admin
`GET /admin/legal-sources/search` debug endpoint) is left as plain vector
search rather than upgraded to hybrid+RRF. It exists specifically so an admin
can sanity-check what a raw embedding actually retrieves; RRF re-ordering
would muddy that signal. The chat pipeline is the only caller of
`app.services.rag.retrieval.hybrid_search`.

**Citations are persisted, not just rendered:**

Each assistant `ChatMessage` gets a `sources` JSONB column (migration 0005) —
the `legal_chunks` that were actually handed to the model for that reply
(document id/title, section, article, source URL). This is `null` for
out-of-scope replies and `[]` when retrieval ran but found nothing, so the
three states (out of scope / insufficient evidence / grounded) are
distinguishable from the stored data alone, not just from the reply text.

## Consequences

- Chat now requires **both** `ANTHROPIC_API_KEY` (classification + generation)
  and `GEMINI_API_KEY` (retrieval) to produce anything beyond
  out-of-scope/insufficient-evidence replies — a real change from Phase 2,
  where only the Anthropic key was needed. This is documented in the
  roadmap/READMEs, not silent.
- Until a real corpus is bulk-ingested (still Phase 3's open follow-up),
  `hybrid_search` returns `[]` for essentially every query, so
  `INSUFFICIENT_EVIDENCE_MESSAGE` is the expected, correct answer to almost
  everything right now. That's the honest state of an empty knowledge base,
  not a bug — verified end-to-end by `test_hybrid_search_returns_empty_list_when_no_chunks_exist`.
- RRF is a heuristic, not a learned relevance model — it can't tell a
  genuinely on-topic keyword match from an accidental one the way a
  cross-encoder reranker could. Acceptable at this stage; revisit if/when
  retrieval quality on a real corpus turns out to need it and a free/self-hostable
  reranker becomes practical to run.
- `content_tsv` is a Postgres `GENERATED ALWAYS AS ... STORED` column, so it
  self-maintains for every insert/update to `content` — no ingestion pipeline
  changes were needed to keep it in sync.

## Alternatives considered

- **Cohere/Voyage rerank API** — best-in-class relevance, but paid; ruled out
  by the user's no-paid-services instruction.
- **Claude as the reranker** (feed candidates back to the LLM, ask it to
  reorder/score) — free in the sense of "no new vendor", but doubles LLM
  calls (and cost/latency) per chat message for a step RRF handles for
  free; revisit if RRF proves insufficient on a real corpus.
- **Hard cosine-distance threshold as the guardrail** — rejected: no real
  corpus exists yet to calibrate a number against (see above); the
  presence/absence of retrieved chunks plus a prompt-level "say what's
  missing" instruction is honest without needing a made-up constant.
- **Upgrade `semantic_search` in place to hybrid+RRF** instead of adding a
  separate `hybrid_search` — rejected to keep the admin debug tool's signal
  (what does this embedding alone retrieve?) uncontaminated by fusion.
