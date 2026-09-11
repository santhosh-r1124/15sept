# Product Roadmap

16 phases from architecture to production launch. Each phase has a concrete
deliverable and builds on the previous one.

| Phase | Name                          | Deliverable                                                        | Status |
| ----- | ----------------------------- | ---------------------------------------------------------------- | ------ |
| 0     | Architecture                  | Running production-style skeleton: frontend + backend + database | ✅ Done |
| 1     | Authentication                | Full auth + RBAC (CONSUMER, ADVOCATE, ADMIN, LEGAL_ADMIN, ENTERPRISE_USER) | ✅ Done |
| 2     | Public AI Chat                | Working public Indian legal-information chatbot                   | ⬜ Not started |
| 3     | Indian Legal Knowledge Base   | Searchable, source-grounded legal repository (ingestion pipeline) | ⬜ Not started |
| 4     | RAG Engine                    | Production Indian legal RAG (hybrid search + rerank + guardrails) | ⬜ Not started |
| 5     | Classification & Guardrails   | Legal category classifier + LOW/MEDIUM/HIGH/CRITICAL risk engine  | ⬜ Not started |
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
