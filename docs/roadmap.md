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
| 6     | Document Assistant            | Consumer legal-document questionnaire + draft/template generation | ✅ Done |
| 7     | Advocate Marketplace          | Advocate discovery with filters + profiles                       | ✅ Done |
| 8     | On-Demand Consultation        | End-to-end booking → payment → consultation → matter closed      | ✅ Done (incl. voice/video calls — see "Voice & video" below) |
| 9     | Advocate Portal               | Advocate operating dashboard (requests, matters, docs, earnings)  | ✅ Done (files on local disk; platform fee defaults to 0 — needs owner decision) |
| 10    | Payments                      | Consultation + document-service payments, refunds, invoices       | ✅ Done (ledger/refunds/invoices; gateway is a mock until the owner picks one; no tax computed) |
| 11    | Notifications                 | Email / SMS / OTP / in-app across all lifecycle events            | ✅ Done (in-app + email; SMS/OTP deliberately not built — paid provider, owner decision) |
| 12    | Admin & Legal Ops Dashboard   | User/advocate/RAG-source management, high-risk query review       | ✅ Done (UI in apps/web `/admin`; no audit trail until Phase 13) |
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

## Phase 6 — what shipped

- `GET /api/v1/documents/types` — all 11 document types from
  `packages/shared/src/legal.ts::DOCUMENT_TYPES` (Rental Agreement,
  Employment Agreement, NDA, Affidavit, Declaration, Business Agreement,
  Partnership Document, Authorization Letter, Service Agreement, Legal
  Notice, Other), each with a fixed questionnaire
  (`apps/api/app/services/document_assistant/questions.py`) — matches the
  FRD §7 worked example, every set asks for the Indian state (FRD §12).
- `POST /api/v1/documents` — validates the answers against that type's
  required questions (422 with per-field details if any are missing), then
  one Claude call (`document_assistant/generation.py::generate_draft`)
  produces a labeled DRAFT plus a Notes section (what's normally required,
  common clauses, likely supporting documents, what professional
  verification may be required) and persists it. Works anonymously or
  logged in, same as chat.
- **Not RAG-grounded** — no `hybrid_search` call, no citations. This was a
  deliberate scope decision, not an oversight:
  see [`docs/adr/0009-document-assistant-scope.md`](adr/0009-document-assistant-scope.md).
  Safety comes from the prompt (state-variance + professional-verification
  language, DRAFT-only framing, no invented facts) and the standard
  `MANDATORY_DISCLAIMER`, not citations.
- **Failed generations aren't persisted** — unlike ingestion's
  `ingestion_status=FAILED` rows, a Claude failure here 503s the request
  directly (same pattern as chat); every `document_requests` row is a
  successfully generated draft (docs/adr/0009).
- `GET /documents` (your own requests) / `GET /documents/{id}`
  (ownership-checked, readable anonymously if it has no owner) — same shape
  as chat's conversation endpoints.
- Requires `ANTHROPIC_API_KEY` only — no new API key, no `GEMINI_API_KEY`
  dependency, since there's no retrieval step.
- Frontend: `apps/web` gets `/documents` — pick a type, fill the
  questionnaire, get the draft.

## Phase 7 — what shipped

- `GET /api/v1/advocates` — public directory search over `AdvocateProfile`
  (built in Phase 1), filterable by `practice_area`, `state_code`, `city`,
  `language`, `min_experience_years`, `max_consultation_fee`; paginated,
  ordered most-experienced-first. Only ever returns `VERIFIED` advocates —
  pending/rejected profiles are excluded, not just hidden.
- `GET /api/v1/advocates/{id}` — single verified advocate's public profile.
  Same 404 whether the id doesn't exist or exists but isn't verified, so an
  unverified advocate's profile isn't discoverable even by guessing its id.
- Public responses (`AdvocateDirectoryEntry`) are a narrower shape than the
  advocate's own `AdvocateProfileOut`: adds `display_name` (joined from
  `User`, not a column on the profile itself) and omits
  `verification_note` (an internal admin moderation note).
- **Two FRD §8 filters aren't implemented**: "consultation type" and
  ratings/reviews. Neither exists as real data yet — both only make sense
  once Phase 8 introduces actual consultations (a type to declare, a
  completed matter to review) — so they weren't faked with placeholder
  fields.
- No schema changes — Phase 1's `advocate_profiles` table already had every
  field this phase needed (`practice_areas`, `state_code`, `city`,
  `languages`, `consultation_fee`, `experience_years`, `availability`,
  `verification_status`).
- Frontend: `apps/web` gets `/advocates` (filterable search) and
  `/advocates/[id]` (profile view) — read-only; booking a consultation is
  Phase 8, so the profile page says so rather than showing a dead button.

## Phase 8 — what shipped

- **Matters** (`/api/v1/matters`): a consumer books a verified advocate for a 15/30/60-minute
  consultation or a document service (draft / review / modification / affidavit assistance /
  agreement review). Lifecycle: `REQUESTED -> ACCEPTED -> PAID -> SCHEDULED -> CLOSED`, plus
  `REJECTED` / `CANCELLED`. The rules live in one pure, exhaustively unit-tested state machine
  (`app/services/matters/lifecycle.py`); illegal moves return 409, non-participants get 404.
- **Quoting**: consultations are prefilled from the advocate's fee (treated as the 60-minute
  price, prorated); the advocate confirms or overrides on accept, and document services must be
  quoted by the advocate. The consumer pays only after seeing the quote.
- **Payment is a stub**: a `PaymentProvider` interface plus a free mock that always succeeds and
  is **refused in production**. The real Indian gateway is a Phase 10 decision that needs the
  project owner's input (paid, regulated) — see
  [`docs/adr/0010-matter-lifecycle-and-payments.md`](adr/0010-matter-lifecycle-and-payments.md).
- **Messaging**: a per-matter thread between consumer and advocate (polled by the UI), read-only
  once the matter ends. **Voice/video** was added afterwards (see "Voice & video consultations"
  below) and document upload/exchange came with Phase 9, the advocate portal.
- Frontend (`apps/web`): booking form on the advocate profile, `/matters`, `/matters/[id]` (status,
  pay / cancel, message thread). The advocate-side UI for accept/schedule/close is Phase 9 — the
  API actions already exist.
- Migration `0008_matters`; `packages/shared/src/matter.ts` mirrors the enums.
- Also new: `python -m app.scripts.seed_demo` (demo consumer/admin/advocates, refuses production)
  and Docker-free local Postgres helpers in `apps/api/dev/` (see `apps/api/README.md`).
- **Found while verifying against a real database for the first time**: chat had been broken since
  Phase 2 (enum persisted as `USER` instead of `user`), the auth tests could never have passed
  (`.test` emails rejected), and the DB test fixtures leaked event-loop-bound connections. All
  fixed (commit `e06d949`); the suite went from "116 passed, 73 skipped" to all-real.

## Phase 9 — what shipped

- **Advocate portal** (`apps/advocate-portal`): a dashboard (new requests, to schedule, awaiting
  payment, client replies waiting, documents requested, upcoming appointments, earnings), a
  filterable matters list, and a matter page with everything an advocate does — accept with a fee
  quote (prefilled for consultations) or reject with a note, schedule / reschedule, close, message
  the client, request documents, upload files and the final deliverable. Plus an earnings page.
- **Document exchange** (`/api/v1/matters/{id}/documents`, `/document-requests`, `/files`):
  advocate requests, either party uploads, participants download. Only the advocate can request or
  upload a *final* document (and only once the client has paid); admins can read but not write;
  outsiders get 404. The client side is in `apps/web` (see requests, upload, download the final).
- **Upload safety** (`app/services/storage`): type allowlist + magic-byte check + size cap (413),
  server-generated storage keys (the client's name never becomes a path), `nosniff` /
  `attachment` / `no-store` on downloads, and RFC 5987 UTF-8 filenames so Indian-script names
  survive. Rationale and limits: [`docs/adr/0011`](adr/0011-advocate-portal-documents-and-earnings.md).
- **Earnings** (`/api/v1/advocates/me/earnings`, `/dashboard`): *earned* = closed matters,
  *pending* = paid and in progress; the platform fee (`PLATFORM_FEE_PERCENT`) applies to earned only.
- **Needs your decision before launch**: the platform fee defaults to **0%** because the FRD leaves
  the commission model open (section 16). Files are stored on **local disk** — fine for development,
  not for a multi-instance deployment; object storage is a Phase 15 choice. Upload malware
  scanning is Phase 13.
- Migration `0009_matter_documents`. Verified live in a browser against real Postgres:
  accept -> request document -> client uploads -> download -> schedule -> final upload -> close ->
  earnings.

## Phase 10 — what shipped

- **Payment ledger**: one `payments` row per matter, an append-only `refunds` table, and a
  snapshotted `invoices` row (numbered `INV-2026-000001` from a database sequence). Pure money
  rules in `app/services/payments/rules.py`; the only writer is `ledger.py`.
- **Refunds**: cancelling a paid matter refunds it in full *in the same transaction* (a provider
  failure rolls the cancel back, so a matter is never cancelled-but-unrefunded); admins can refund
  fully or partially (`POST /api/v1/admin/payments/{id}/refund`). Status-changing matter routes now
  take a row lock, so concurrent cancels can't double-refund.
- **Who can cancel a paid matter**: the advocate always (client refunded in full); the consumer only
  a paid *consultation* before it is scheduled - not a document service, and not once scheduled.
- **Invoices**: HTML view served with a locked-down CSP, `nosniff`, `no-store`, everything
  escaped, participants + admins only. **No GST/tax is computed** - the invoice says so.
- **Earnings are net of refunds**; the portal shows the refund on each line.
- Frontends: payment card + invoice link on both matter pages, a consumer `/payments` page, and a
  "Cancel & refund client" action in the portal.
- **Needs your decision before launch**: the payment gateway (paid, KYC/regulated), GST/tax
  treatment, and how advocate payouts are settled - nothing here moves money to advocates.
  Rationale: [`docs/adr/0012`](adr/0012-payments-ledger-refunds-invoices.md). Migration `0010_payments`.
  Verified live in a browser against real Postgres: pay -> invoice -> consumer cancel -> refunded;
  advocate cancel -> refunded and earnings drop out.

## Phase 11 — what shipped

- **In-app notifications** (`/api/v1/notifications`): a feed, unread count (the header bell), mark
  one / all read, and an email on/off preference. Written in the *same transaction* as the action
  they announce, so a rolled-back action never leaves a phantom notification.
- **Events covered**: booking request, accepted, rejected, cancelled (with refund), paid, scheduled,
  closed, new message, document requested / uploaded, admin refund, advocate verified / rejected.
- **Email** through the existing `EmailSender` protocol, now with a real `SmtpEmailSender`
  (`EMAIL_BACKEND=smtp`; any SMTP server - a free Gmail/Outlook app-password account works - and no
  paid service is required). The default `console` backend just logs.
- **Emails carry no matter details** - a generic sentence plus a link into the right app (portal for
  advocates, web for clients). Titles, fees, dates and message text stay in-app behind login.
- **Outbox**: the email is a column set on the notification row; delivery happens after commit, a
  failure leaves it PENDING (retried by `python -m app.scripts.send_pending_emails`, given up on
  after 5 tries) and pauses inline sending for a minute, so a dead mail server never breaks or slows
  requests. Bursts of chat messages collapse into one unread bell entry.
- Frontends: `NotificationBell` in both headers (polls every 30 s - no push channel yet) and a
  `/notifications` page in both apps. Migration `0011_notifications`.
- **Not built, on purpose**: SMS and phone OTP. Every Indian route is a paid, DLT-registered
  provider - an owner decision. Email-link verification (Phase 1) already covers account
  verification at no cost. Reminders ("your consultation is in 1 hour") need a scheduler, which
  arrives with deployment in Phase 15.
  Rationale: [`docs/adr/0013`](adr/0013-notifications-in-app-and-email-outbox.md).

## Phase 12 — what shipped

- **Admin dashboard** at `/admin` in `apps/web` (role-gated, `ADMIN` / `LEGAL_ADMIN`; the server
  re-checks every call): an **overview** of what needs attention (queries to review, advocates
  awaiting verification, failed notification emails) plus breakdowns of users, advocates, matters,
  the knowledge base and payments; **risk review**; **advocates** (verify / reject with a note - the
  advocate is notified); **users** (search, suspend / reactivate); **matters** (read-only oversight);
  **payments** (full or partial refund, the client is notified); **legal sources** (add by URL,
  re-index, remove).
- **High-risk query review** (`/api/v1/admin/reviews`): the HIGH / CRITICAL chat queries from Phase 5,
  worst first, with the assistant's answer and how many sources grounded it. Reviewers see the
  question, answer and classification but **never who asked**. Marking a query reviewed records who
  and when (migration `0012_query_review`).
- New API: `/admin/overview`, `/admin/matters`, `/admin/advocates` (all statuses, with name + email),
  `/admin/reviews`, `?q=` search on `/admin/users`. An admin cannot suspend their own account.
- **Bug found while verifying, fixed**: timestamps stored as naive UTC (`created_at`, `updated_at`)
  were shown 5½ hours early in India on every screen since Phase 1, because they are serialised
  without an offset and browsers read that as local time. Fixed in `formatDateTime` (both apps, with
  a unit test). The root cause - naive `timestamp` columns - is recorded for Phase 13/15.
- **Known gap**: no audit trail yet for admin actions or for reading chat content - `audit_logs` is
  Phase 13. Not built: bulk actions, role changes in the UI, editing advocate profiles, uploading
  a source file. Rationale: [`docs/adr/0014`](adr/0014-admin-and-legal-ops-dashboard.md).

## Voice & video consultations (Phase 8 follow-up)

- **Video and voice calls** between the client and the advocate for a paid consultation - the actual
  consultation, not just its booking. WebRTC **browser to browser**: audio/video are encrypted end to end
  and never touch our servers, **calls are not recorded**, and there is no per-minute cost (free STUN by
  default; a self-hosted coturn TURN relay optional).
- **API**: `POST /matters/{id}/call/session` (a one-minute, single-use ticket + ICE servers), `GET
  /matters/{id}/call` (is the room open, who is in it, past calls) and the signaling WebSocket `WS
  /matters/{id}/call/ws`. Only the two participants can join; the room opens 10 minutes before the booked
  time and closes 30 minutes after it (paid-but-unscheduled consultations can be opened ad hoc, capped at 3 h).
  The first person in notifies the other ("waiting in the consultation room").
- **UI** (both apps): a call card on the matter page and a `/matters/[id]/call` room - join with video or
  audio-only, mute / camera toggles, timer, leave, automatic reconnect and re-negotiation if the other side
  refreshes. Calls are recorded as metadata only (`matter_calls`: who opened, when both were connected, how
  long, why it ended). Migration `0013_matter_calls`.
- **Verified** with 90 new backend tests (rules, ICE/TURN credentials against an independent OpenSSL
  computation, tickets, hub, REST + database gatekeeper, and real WebSocket frames) and a live two-tab
  check exchanging real WebRTC audio + video, leave / rejoin, and the recorded call. **Not yet tried on real
  cameras / phones / different networks** - do that on staging.
- **Needs**: HTTPS in production (browsers only allow the camera on secure origins), a TURN server if the
  platform must work behind strict firewalls or hide IP addresses (`infrastructure/deployment/coturn.conf.example`),
  and sticky routing (or a Redis relay) if the API runs on more than one instance. Not built: recording,
  screen share, group calls, pre-call reminders. Rationale: [`docs/adr/0015`](adr/0015-voice-video-consultations.md).

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
