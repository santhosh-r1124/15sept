# Product Roadmap

16 phases from architecture to production launch. Each phase has a concrete
deliverable and builds on the previous one.

| Phase | Name                          | Deliverable                                                        | Status |
| ----- | ----------------------------- | ---------------------------------------------------------------- | ------ |
| 0     | Architecture                  | Running production-style skeleton: frontend + backend + database | ✅ Done |
| 1     | Authentication                | Full auth + RBAC (CONSUMER, ADVOCATE, ADMIN, LEGAL_ADMIN, ENTERPRISE_USER) | ✅ Done |
| 2     | Public AI Chat                | Working public Indian legal-information chatbot                   | ✅ Done (no retrieval grounding yet — see below) |
| 3     | Indian Legal Knowledge Base   | Searchable, source-grounded legal repository (ingestion pipeline) | ✅ Done (pipeline + storage; bulk corpus population is follow-up) |
| 4     | RAG Engine                    | Production Indian legal RAG (hybrid search + rerank + guardrails) | ✅ Done (wired into chat; most answers are "insufficient evidence" until a corpus is loaded) |
| 5     | Classification & Guardrails   | Legal category classifier + LOW/MEDIUM/HIGH/CRITICAL risk engine  | ✅ Done |
| 6     | Document Assistant            | Consumer legal-document questionnaire + draft/template generation | ⬜ Not started |
| 7     | Advocate Marketplace          | Advocate discovery with filters + profiles                       | ⬜ Not started |
| 8     | On-Demand Consultation        | End-to-end booking → payment → consultation → matter closed      | ⬜ Not started |
| 9     | Advocate Portal               | Advocate operating dashboard (requests, matters, docs, earnings)  | ⬜ Not started |
| 10    | Payments                      | Consultation + document-service payments, refunds, invoices       | ⬜ Not started |
| 11    | Notifications                 | Email / SMS / OTP / in-app across all lifecycle events            | ⬜ Not started |
| 12    | Admin & Legal Ops Dashboard   | User/advocate/RAG-source management, high-risk query review       | ⬜ Not started |
| 13    | Security & Compliance         | Hardening: rate limiting, prompt-injection defence, audit logs, tenant isolation | ⬜ Not started |
| 14    | Testing                       | Unit + integration + browser E2E coverage                        | 🟡 Scaffolding only |
| 15    | Production Deployment          | Cloud hosting, managed Postgres/Redis, monitoring, CI/CD, backups | 🟡 Scaffolding only |
| 16    | Launch                        | MVP: Chat + Document Assistant + Advocate Search + Booking        | ⬜ Not started |

## Phase 1 — what shipped

- Consumer: register, login, logout, email verification, password reset, profile
  (state, preferred language).
- Advocate: self-registration with practice areas/state/city/languages/fee/bio,
  own-profile view + edit, verification status.
- Admin: RBAC-gated user list/suspend and advocate verification queue
  (approve/reject) via `/api/v1/admin/*` — no dedicated UI yet, that's Phase 12.
  Bootstrap the first admin with `uv run python -m app.scripts.create_admin`.
- JWT access tokens + DB-backed, rotating refresh tokens (revocable — real
  logout). RBAC via `require_roles(...)` dependency.
- Frontend: `apps/web` has `/register /login /verify-email /reset-password
  /profile`; `apps/advocate-portal` has `/register /login /profile`.

## Phase 2 — what shipped

- `POST /api/v1/chat/messages` — works anonymously (Tier 1 / public, per the
  FRD) or logged in. One Claude call classifies the message (legal category,
  jurisdiction scope, in/out of scope), a second generates the answer only if
  in scope; out-of-scope messages get a fixed reply without a second call.
- Conversations + messages persisted in Postgres (`conversations`,
  `chat_messages`); anonymous threads are addressable by ID, logged-in threads
  are also listable (`GET /chat/conversations`) and ownership-checked.
- **No retrieval grounding yet** — deliberately deferred to Phase 3
  (ingestion) / Phase 4 (RAG). The system prompt instructs the model to defer
  to an advocate rather than invent specifics, which is the closest honest
  stand-in until real sources exist; treat pre-Phase-4 answers as informational
  only, not citation-backed.
- Requires `ANTHROPIC_API_KEY` (`apps/api/.env`) — unset by design until you
  add one; the endpoint 503s with a clear `llm_not_configured` error until then.
- Frontend: `apps/web` gets `/chat` — message thread, suggested questions
  (the FRD's example queries), new-conversation, and (when logged in) a
  history panel. Mandatory disclaimer shown on every page.

## Phase 3 — what shipped

- Ingestion pipeline (`apps/api/app/services/ingestion/`): fetch (HTTP, 25 MB
  cap) → extract (PDF via pypdf, HTML via BeautifulSoup) → clean (whitespace,
  page-number lines, Unicode noise) → chunk (size-based sliding window,
  ~1500 chars, 200 overlap) → embed (Gemini, free tier) → persist (pgvector,
  HNSW cosine index).
- `legal_documents` + `legal_chunks` tables track ingestion status
  (PENDING/PROCESSING/COMPLETED/FAILED) and the failure reason — one bad
  source never 500s the request.
- Admin API (`/api/v1/admin/legal-sources/*`, RBAC-gated): ingest, list,
  get, delete, re-index, and semantic search. No UI yet — that's Phase 12;
  usable now via `/docs`.
- Requires `GEMINI_API_KEY` (`apps/api/.env`) — unset by design, same
  "build now, key later" pattern as Phase 2; ingestion records a FAILED
  status with `embeddings_not_configured` until you add one.
- **`section`/`article` metadata is not populated** — an early attempt at
  heading-detection proved unreliable against real PDF-extracted text and
  was dropped; see
  [`docs/adr/0006-chunking-strategy.md`](adr/0006-chunking-strategy.md).
- **No documents are pre-loaded.** The roadmap's "initial knowledge base"
  (IT Act, DPDP Act, Companies Act, etc.) is a bulk-ingestion follow-up, not
  done in this pass — the pipeline was validated by actually fetching and
  processing the real IT Act 2000 and DPDP Act 2023 PDFs during development
  (that's also how the chunking bug in the ADR above was found), not by
  populating the repository.
- Chat (Phase 2) is **not yet wired to this** — that integration (hybrid
  search, reranking, cited answers) is Phase 4.

## Phase 4 — what shipped

- Hybrid retrieval (`apps/api/app/services/rag/retrieval.py::hybrid_search`):
  pgvector cosine similarity + Postgres full-text search (a generated
  `tsvector` column, GIN-indexed — migration 0005) over `legal_chunks`,
  fused with Reciprocal Rank Fusion (RRF) rather than a paid/ML reranker —
  see [`docs/adr/0007-hybrid-search-and-grounding.md`](adr/0007-hybrid-search-and-grounding.md)
  for why, including the no-paid-services constraint.
- `POST /api/v1/chat/messages` now runs retrieval for in-scope questions and
  answers only from what it finds (`llm.py::generate_grounded_answer`),
  citing sources with `[n]` markers. Citations are also persisted on the
  assistant `ChatMessage` (`sources` JSONB — document, section/article,
  source URL) and rendered as a source list in `apps/web`'s chat UI.
- **Guardrail**: retrieval returning nothing — empty corpus, an unrelated
  question, or `GEMINI_API_KEY` unset — short-circuits to
  `INSUFFICIENT_EVIDENCE_MESSAGE` without a second Claude call, rather than
  guessing. A hard cosine-distance threshold was considered and rejected:
  there's no real corpus yet to calibrate one against.
- **Chat now needs both API keys** to produce a grounded answer:
  `ANTHROPIC_API_KEY` (unchanged from Phase 2) and `GEMINI_API_KEY` (new —
  same key Phase 3's ingestion uses). Missing `ANTHROPIC_API_KEY` still 503s;
  missing `GEMINI_API_KEY` degrades to the insufficient-evidence reply
  instead, since that failure mode is indistinguishable from "no sources
  matched" on the user's side.
- **Still no bulk corpus loaded** (carried over from Phase 3) — so in the
  platform's current state, hybrid search returns nothing for essentially
  every query and almost all chat answers are correctly
  "insufficient evidence". This is the honest behavior of an empty knowledge
  base, not a regression; verified end-to-end by
  `test_hybrid_search_returns_empty_list_when_no_chunks_exist` and
  `test_insufficient_evidence_short_circuits_generation`.
- The Phase 3 admin debug endpoint (`GET /admin/legal-sources/search`,
  plain vector search) is unchanged — kept deliberately separate from the
  chat pipeline's hybrid search so an admin can inspect raw embedding
  similarity without RRF re-ordering muddying the signal.

## Phase 5 — what shipped

- `risk_level` (LOW/MEDIUM/HIGH/CRITICAL) is now a fourth field on the same
  forced-tool-call classification Phase 2 already made — not a second Claude
  call. See [`docs/adr/0008-risk-scoring.md`](adr/0008-risk-scoring.md) for
  why (cost, and two independent judgements of the same message risking
  disagreement).
- Classification moved out of `llm.py` into its own module
  (`apps/api/app/services/legal_classifier.py`) — completing the split
  `llm.py`'s Phase 2/4 docstrings had already flagged as coming. A new
  `risk_engine.py` holds the pure decision logic
  (`requires_advocate_recommendation`), separate from how the risk level was
  produced.
- HIGH/CRITICAL messages get `ADVOCATE_RECOMMENDATION_MESSAGE` appended to
  the assistant reply — whether it's a grounded answer or an
  insufficient-evidence one; out-of-scope replies are unaffected (they're not
  assessing legal risk at all).
- `chat_messages.risk_level` (migration 0006, indexed) persists the level
  alongside the existing `legal_category`/`jurisdiction_scope` columns, ready
  for the Phase 12 admin "high-risk query review" queue.
- No new API keys or settings — risk scoring rides on the same
  `ANTHROPIC_API_KEY` classification call Phase 2 already required.

## MVP scope (Phase 16)

Consumer Legal Chat · Legal Document Assistant · Advocate Search · Consultation
Booking. Payments, video consultation, premium subscription, enterprise assistant
and advanced compliance follow progressively.

## Non-negotiable product rules

- **Grounded, not guessed.** Answers come from retrieved verified Indian legal
  sources. Insufficient evidence → say so, don't invent. No fabricated citations.
- **Information, not representation.** The AI never claims to be an advocate or to
  create an advocate-client relationship. High-risk matters route to an advocate.
- **Jurisdiction-aware.** Distinguish central vs state vs local; never quote a
  single national figure for state-varying things (e.g. stamp duty).
- **Disclaimer always visible** wherever AI legal information is shown
  (`@legal-platform/shared` → `MANDATORY_DISCLAIMER`).
- The professional-services / payment model must be reviewed against applicable
  Indian legal and professional rules before commercial launch.

Source: FRD 1 — Indian IT & Legal Advisor + Advocate Connect Platform.
