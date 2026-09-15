# 0009 — Document Assistant: static questionnaire, not RAG-grounded, failures not persisted

- Status: Accepted
- Date: 2026-09-15
- Deciders: Platform team

## Context

Phase 6's deliverable (FRD §7) is a consumer Legal Document Assistant: the
user picks a document type, answers a structured questionnaire, and gets a
draft plus an explanation of what's normally required. Three design
questions had to be settled before writing any code, because each one is a
deliberate departure from a pattern already established elsewhere in the
codebase.

## Decisions

### 1. The questionnaire is a static, hard-coded schema per document type — not LLM-generated

`app/services/document_assistant/questions.py::QUESTION_SETS` is a plain
Python dict, one fixed list of `Question`s per `AssistantDocumentType`. An
alternative would have Claude generate the question list per request (or per
document type, cached). Rejected: the FRD's own worked example (Affidavit ->
Purpose, Name, Address, Jurisdiction, Facts to declare, Supporting documents)
is already a fixed field list, the right questions for "a rental agreement"
don't change between users, and an LLM call to reproduce a static answer adds
latency/cost for nothing — same reasoning as
[0008](0008-risk-scoring.md) and
[0007](0007-hybrid-search-and-grounding.md): don't spend an LLM call where a
deterministic answer is just as correct. Every set includes a `state_code`
question specifically, since FRD §12 requires flagging that
execution/stamping/registration rules vary by state.

### 2. Draft generation is NOT run through `hybrid_search` — no citations, no grounding gate

Chat (`app.services.llm.generate_grounded_answer`) answers a legal *question*
from retrieved `legal_chunks` and cites them; if retrieval finds nothing, it
refuses rather than guess (docs/adr/0007). The Document Assistant does not
call `app.services.rag.retrieval.hybrid_search` at all. This is a real
question, not an oversight: the platform's "grounded, not guessed" rule is
about legal information claims, and it was worth checking whether drafting a
document falls under it too. It doesn't fit the same shape:

- Retrieval finds *facts about Indian law* (Acts, judgments). A document
  draft is assembled from *facts the user just typed in* (names, dates,
  amounts) plus standard document structure/conventions — there's nothing in
  `legal_chunks` to retrieve that would ground "here is a rental agreement
  with your landlord's name in it."
- The FRD's own §7 doesn't mention sources/citations for this feature at
  all, unlike §5 (Public Legal Chat: "Retrieve relevant Indian legal
  sources... Display sources").
- Gating draft generation on a non-empty `legal_chunks` result would make
  the Document Assistant produce `INSUFFICIENT_EVIDENCE_MESSAGE` for
  *every* request right now (no bulk corpus is loaded — carried over from
  Phase 3/4), which would ship a feature that's permanently broken rather
  than one that's honestly out of RAG's scope.

Safety instead comes from the prompt directly (`generation.py`'s
`_SYSTEM_PROMPT`): state explicitly that execution/notarization/stamping/
registration requirements vary by state, document type and circumstances
(never a single national rule); label the output a DRAFT, not a legally
executed document; never invent specific facts beyond what was answered
(placeholder text instead); recommend advocate review. Plus the same
`MANDATORY_DISCLAIMER` chat already returns.

If/when a real template or clause-library corpus is ingested (a genuinely
different kind of source than the Acts/judgments `legal_chunks` holds today),
this decision is worth revisiting — but that corpus doesn't exist yet, so
grounding against it isn't an option now, only a future one.

### 3. A failed draft generation 503s the request — it is never persisted

`document_requests` (migration 0007) has no `status` or `generation_error`
column, unlike `legal_documents` (Phase 3, `ingestion_status`/
`ingestion_error`). This mirrors chat, not ingestion, on purpose:

- Ingestion is an admin batch operation over external URLs — a genuinely
  I/O-heavy, failure-prone step where the admin needs to *see why* a
  specific source failed without the whole request erroring (roadmap
  Phase 12: "Track ingestion failures").
- Document draft generation is a single interactive request, like chat: the
  user is sitting there waiting for one Claude call over their own just-typed
  answers. `app.services.llm` doesn't record failed chat turns either — it
  raises `ServiceUnavailableError` (503, `llm_not_configured` /`llm_error`)
  straight to the caller, and nothing is committed. `generate_draft` (and
  therefore `POST /documents`) does the same.
- Consequence: every row in `document_requests` is a successfully generated
  draft. No dead/incomplete rows to filter out later, no status enum to keep
  in sync with reality.

## Consequences

- No new external service or API key: draft generation reuses
  `app.services.anthropic_client` (the same `ANTHROPIC_API_KEY` chat already
  requires) — consistent with the project's standing no-paid-services default.
- The questionnaire is entirely stateless server-side:
  `GET /documents/types` returns the full schema once, the frontend collects
  every answer client-side (a multi-step form), and `POST /documents` submits
  the complete set. There is no "save a partially-filled questionnaire and
  resume later" endpoint — an honestly-flagged simplification, the same way
  Phase 3 flagged "no bulk corpus loaded yet" rather than silently doing
  less than the roadmap implied.
- Adding a twelfth document type is a `QUESTION_SETS` entry, a
  `packages/shared/src/legal.ts::DOCUMENT_TYPES` entry, and an
  `AssistantDocumentType` enum member (+ migration) — no prompt-engineering
  or classifier retraining involved.

## Alternatives considered

- **LLM-driven dynamic questionnaire** — rejected for cost/latency/
  unpredictability with no benefit over a fixed schema (§1 above).
- **Gate drafts on `hybrid_search` like chat** — rejected: no matching
  source data exists to retrieve (a template corpus is not the same thing
  as the Acts/judgments corpus), and it would make the feature permanently
  non-functional given today's empty knowledge base (§2 above).
- **Persist failed generations with a status/error column, like ingestion**
  — rejected: this is a synchronous interactive request, not a batch
  pipeline; a 503 is the honest, immediate answer, and there is no admin
  audit use case for it the way there is for ingestion failures (§3 above).
