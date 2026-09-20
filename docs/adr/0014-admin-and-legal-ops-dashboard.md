# 0014 - Admin & legal-ops dashboard

- Status: Accepted
- Date: 2026-09-20
- Deciders: Platform team

## Context

By Phase 11 most admin *capabilities* existed as API endpoints - user list / suspend, the advocate
verification queue, legal-source ingestion, payment refunds - but no UI, and two things legal ops
needs were missing entirely: an overview of what needs attention, and a way to review the chat
queries the risk engine (Phase 5) flagged HIGH or CRITICAL. Phase 12 adds those and the UI.

## Decisions

### 1. The dashboard lives in `apps/web` under `/admin`, not in a third app

A new Next.js workspace app would need `pnpm install` to link it, which the development machine's
Application Control policy blocks (see `docs/roadmap.md`, toolchain note). More importantly it would
duplicate the auth provider and API client for no functional gain. So `/admin/*` is a route group in
the consumer app behind a role gate (`hasAdminAccess`), and Next code-splits by route, so ordinary
users never download the admin code.

The gate only decides what to *show*. Every admin API call is authorised again on the server
(`require_roles(ADMIN, LEGAL_ADMIN)`), and a test asserts that consumers and advocates get 403 (and
anonymous callers 401) on every admin endpoint. If the admin surface ever needs its own origin (an
IP allow-list, stricter CSP), it can move to its own app without touching the API.

### 2. Reviewers see the query, never the asker

`GET /admin/reviews` lists user chat messages with `risk_level` HIGH / CRITICAL, worst first then
longest-waiting, with the assistant's answer, how many sources grounded it (0 = "insufficient
evidence"), and the classification. The response has **no user id, email or name** - only a
`registered` flag - and a test asserts that neither the keys nor the asker's id appear. Reviewers
need to judge whether the *answer* was safe and whether the query should have routed to an advocate,
not to identify the person. Anonymous chats have no identity to expose anyway.

Review state is three nullable columns on the user's own message (`reviewed_at`, `reviewed_by_id`,
`review_note`; migration 0012) with a partial index over unreviewed high-risk rows, so the queue
stays cheap however large `chat_messages` grows. Reviewing is idempotent: a second reviewer can amend
the note, but the first reviewer and time stand. Only HIGH/CRITICAL *user* messages can be reviewed;
anything else (LOW, unclassified, an assistant message, an unknown id) is a 404.

**Known gap**: an admin reading private chat content is exactly what an audit trail is for, and
there is none yet - `audit_logs` is Phase 13 and will record review reads and the other admin
actions here (suspend, verify, refund) together.

### 3. Small server-side additions, each with a reason

- `GET /admin/overview`: counts by role / advocate status / matter status / knowledge-base status,
  payment totals, and the things a person must act on (advocates awaiting verification, queries to
  review, failed / pending notification emails). Every breakdown is zero-filled so the UI never
  guesses at missing keys.
- `GET /admin/advocates?status=`: the existing `/pending` list returns the public profile shape,
  which has no name or email - useless for deciding whom to verify. The new list includes both and
  covers every status (so a rejected advocate can be reconsidered).
- `GET /admin/matters`: read-only oversight with both parties' names.
- `GET /admin/users?q=`: substring search on email / name. LIKE wildcards are escaped, so searching
  `%` matches a literal `%`, not everyone.
- **An admin cannot suspend their own account** (409): it could lock out the last person able to undo
  it. Suspension itself already worked - a suspended user is rejected at login, refresh and on every
  authenticated request.

### 4. A bug found by looking at real data: timestamps shown 5½ hours early

Checking the review queue against real rows showed "created 8:03 AM" next to "reviewed 1:36 PM" for
the same minute. Columns declared as plain `datetime` (`created_at` / `updated_at` on most tables) are
`timestamp without time zone` holding UTC; Pydantic serialises them **without an offset**
(`2026-09-20T08:05:12`), and `new Date()` reads an offset-less string as *local* time - so every such
time was wrong by the viewer's UTC offset (5½ h in India), on every screen since Phase 1, while
timezone-aware columns (`paid_at`, `scheduled_at`, notifications) were right.

Fixed at the single choke point, `formatDateTime` in both frontends: a string with no offset is now
parsed as UTC (`parseApiDate`, unit-tested). The **root cause remains** - the naive columns - and the
proper fix is migrating them to `timestamptz`; that touches every table and is recorded for Phase
13/15 rather than slipped into this change.

## Consequences

- Legal ops can work a queue: verify or reject advocates (who are notified), review risky queries,
  suspend accounts, refund, and manage the knowledge base (add a source by URL, re-index, remove) from
  the browser. Verified live against real Postgres: overview counts, review queue ordering, marking
  reviewed (and the "Reviewed" tab), verifying an advocate (notification sent), a partial refund
  (status "Partially Refunded", client notified), user search, and the self-suspension guard.
- **Not built**: bulk actions, role changes in the UI (`app.scripts.create_admin` promotes accounts),
  editing advocate profiles, uploading a source file (URL only), pagination controls (lists show the
  first 50-100), and any reporting or export beyond the overview.
- Source ingestion is still synchronous, so "Add & index" waits (the client allows 3 minutes). A
  background queue is a deployment-phase concern.

## Alternatives considered

- **A separate `apps/admin` app**: cleaner isolation, but blocked locally and duplicates plumbing (see
  above). Reversible later.
- **Show reviewers who asked**: convenient for follow-up, but puts a name next to a legal query
  ("my husband wants custody...") for everyone with an admin role. Rejected in favour of the minimum
  needed to do the job.
- **Fix the timestamps by making the API emit `Z` for naive columns**: right in principle, but a
  global serialiser change is broader than this phase; the frontend fix is contained and testable,
  and the column migration is the real answer.
