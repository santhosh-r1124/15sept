# 0011 - Advocate portal: document exchange, local file storage, earnings rules

- Status: Accepted
- Date: 2026-09-20
- Deciders: Platform team

## Context

Phase 9 makes the advocate side of Phase 8's matters usable: a dashboard, the actions
(accept / schedule / close / message), document exchange ("request documents", "upload final
documents", FRD 10) and earnings. The actions already existed as API endpoints; this phase is
the portal UI plus three new backend concerns, each with a decision worth recording.

## Decisions

### 1. Document exchange: requests + files, with an explicit permission model

Two tables: `matter_document_requests` ("please send me X", raised by the advocate, flipped to
FULFILLED when a file is attached to it) and `matter_files` (metadata only). Rules, enforced
server-side and tested over real HTTP:

- Only the **advocate** can request documents or upload a *final* deliverable.
- Documents change hands only while the matter is ACCEPTED / PAID / SCHEDULED - not before the
  advocate has taken it on, and never after it ends. A final deliverable additionally needs the
  client to have **paid** (PAID / SCHEDULED).
- Participants read and download; **admins may read and download but never write**; everyone
  else gets a 404 (same "don't leak existence" rule as the rest of the matter API). A file id is
  only reachable through the matter it belongs to.

### 2. Uploads are validated, and the client never chooses where bytes go

`app/services/storage` - on a legal platform, uploaded files are the highest-risk input:

- **Allowlist + magic bytes**: PDF, Word (.doc/.docx), PNG, JPEG, plain text. The declared type
  must be allowed *and* the leading bytes must match it (an executable renamed `.pdf` is
  rejected); text must be real UTF-8 without NUL bytes. Empty files are rejected; oversized files
  are a 413 (`upload_max_bytes`, 10 MB) - the request reads one byte past the cap so it never
  buffers an unbounded upload.
- **Storage keys are server-generated** random hex names. The client's file name is kept only for
  display and the download header - it never touches the filesystem. `LocalFileStorage` also
  refuses any key that isn't `<32 hex>.<ext>`, so a traversal string can't become a path.
- **Downloads** send `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff` and
  `Cache-Control: private, no-store`. The header carries a sanitised ASCII `filename` **and** the
  RFC 5987 `filename*=UTF-8''...` form, so a Hindi or Tamil file name downloads as itself instead
  of a row of underscores (found while testing: the first version flattened non-Latin names).
- Because the API needs the Bearer token, the frontends download by `fetch` -> blob -> save,
  not a plain link.

**Storage backend is local disk for now** (free, zero setup; `apps/api/uploads/`, gitignored).
It is not suitable for a multi-instance deployment - production should swap in object storage
(S3 / Supabase Storage) behind the same `FileStorage` protocol. That's a Phase 15 deployment
decision and is *not* made here. **Malware scanning** of uploads is Phase 13 (the validation
above is a first line, not a substitute).

### 3. Earnings: paid-and-delivered is "earned"; the platform fee is configured, defaults to 0

`services/matters/earnings.py` (pure, unit-tested): **earned** = CLOSED matters, **pending** =
PAID / SCHEDULED (paid, work still in progress); unpaid, cancelled and rejected matters earn
nothing. The platform's cut (`PLATFORM_FEE_PERCENT`) applies to *earned* only and defaults to
**0**, because the FRD leaves the commission model open ("subject to the applicable professional
and regulatory framework", section 16). **This needs the project owner's decision before
launch** - it is surfaced in the roadmap and the launch checklist rather than guessed. Money is
`Decimal` end to end (strings on the wire), quantised half-up to paise.

### 4. The dashboard is a read-only summary over existing data

`GET /advocates/me/dashboard` counts new requests, awaiting-payment, paid-but-unscheduled
consultations, open document requests, **client replies waiting** (open matters whose latest
message is the client's - a `DISTINCT ON` over `matter_messages`, no read-receipt table needed),
the next appointments, and the earnings summary. No new state was added for it.

## Consequences

- The advocate can run a matter entirely from the portal (verified live in a browser against real
  Postgres: accept -> request document -> client uploads -> download -> schedule -> final upload
  -> close -> earnings). The consumer web app got the client's half (see requests, upload,
  download the final document).
- Voice/video and real-time messaging remain out of scope (polling every 10 s).
- The portal reuses the API's existing auth; there is no separate advocate-only backend.

## Alternatives considered

- **Store file bytes in Postgres** (bytea): simpler to back up, but bloats the DB and its backups
  and scales poorly; rejected in favour of a storage interface.
- **A `read_at` receipt per message** to power "unread": more state and writes for a signal the
  latest-message rule already gives ("waiting for your reply").
- **Deduct the platform fee from pending as well**: rejected - a fee on work not yet delivered
  would need clawback logic if the matter is cancelled/refunded (Phase 10).
