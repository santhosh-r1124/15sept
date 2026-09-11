# Product Roadmap

16 phases from architecture to production launch. Each phase has a concrete
deliverable and builds on the previous one.

| Phase | Name                          | Deliverable                                                        |
| ----- | ----------------------------- | ---------------------------------------------------------------- |
| 0     | Architecture                  | Running production-style skeleton: frontend + backend + database |
| 1     | Authentication                | Full auth + RBAC (CONSUMER, ADVOCATE, ADMIN, LEGAL_ADMIN, ENTERPRISE_USER) |
| 2     | Public AI Chat                | Working public Indian legal-information chatbot                   |
| 3     | Indian Legal Knowledge Base   | Searchable, source-grounded legal repository (ingestion pipeline) |
| 4     | RAG Engine                    | Production Indian legal RAG (hybrid search + rerank + guardrails) |
| 5     | Classification & Guardrails   | Legal category classifier + LOW/MEDIUM/HIGH/CRITICAL risk engine  |
| 6     | Document Assistant            | Consumer legal-document questionnaire + draft/template generation |
| 7     | Advocate Marketplace          | Advocate discovery with filters + profiles                       |
| 8     | On-Demand Consultation        | End-to-end booking → payment → consultation → matter closed      |
| 9     | Advocate Portal               | Advocate operating dashboard (requests, matters, docs, earnings)  |
| 10    | Payments                      | Consultation + document-service payments, refunds, invoices       |
| 11    | Notifications                 | Email / SMS / OTP / in-app across all lifecycle events            |
| 12    | Admin & Legal Ops Dashboard   | User/advocate/RAG-source management, high-risk query review       |
| 13    | Security & Compliance         | Hardening: rate limiting, prompt-injection defence, audit logs, tenant isolation |
| 14    | Testing                       | Unit + integration + browser E2E coverage                        |
| 15    | Production Deployment          | Cloud hosting, managed Postgres/Redis, monitoring, CI/CD, backups |
| 16    | Launch                        | MVP: Chat + Document Assistant + Advocate Search + Booking        |

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
