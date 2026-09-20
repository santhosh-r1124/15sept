# 0013 - Notifications: in-app + an email outbox, privacy-first, no SMS

- Status: Accepted
- Date: 2026-09-20
- Deciders: Platform team

## Context

Phases 8-10 made a matter move through a lifecycle involving two people, and neither is told when
the other acts - the advocate has to poll the portal for new requests, the client for a quote. The
roadmap's Phase 11 lists email / SMS / OTP / in-app. The standing constraint is *free services only*
unless the owner says otherwise, and legal matters are sensitive. Three decisions follow.

## Decisions

### 1. The notification is written in the same transaction as the action; email is an outbox

`notify()` adds a `notifications` row to the caller's session, so it commits - or rolls back -
together with the state change. That is tested directly: a cancel whose refund fails is rolled
back and produces no "cancelled" notification and no email.

The email is *columns on that row* (`email_status` PENDING/SENT/FAILED/SKIPPED, subject, body,
attempts), i.e. a transactional outbox:

- after commit, the request makes **one attempt** to send only *its own* rows;
- a failure leaves the row PENDING (attempts + 1) and **pauses inline sending for 60 s**, so a dead
  mail server costs one timeout, not one per request, and never fails or noticeably slows an action;
- `python -m app.scripts.send_pending_emails` (cron) drains PENDING rows; after 5 attempts a row is
  FAILED and left for a human;
- selection uses `FOR UPDATE SKIP LOCKED`, so overlapping workers never double-send.

No queue, broker or new infrastructure - Postgres is the queue. If volume ever justifies a real
queue, the outbox rows are already the message format.

*Known limits*: delivery still happens on the request path for the one attempt (bounded by the
10 s SMTP timeout); moving it to a background worker is a Phase 15 deployment choice. Email is
at-least-once: a crash between "SMTP accepted" and "row marked SENT" would resend one.

### 2. Emails say almost nothing on purpose

The **in-app** text may name the matter ("Adv. Rao accepted 'Divorce petition'. Fee: ₹2,500.") - it
is shown only inside the recipient's logged-in session. The **email** is a generic sentence and a
link ("An advocate accepted your request. Log in to review the quote."). Titles, names, fees,
dates, notes and message text never travel by email, because email is neither private nor
authenticated and a legal matter's title is itself sensitive. This is enforced by a test that
renders every notification kind and asserts none of those strings appear. Chat-like events (a new
message, an uploaded file) send no email at all; the bell covers them.

Emails to an advocate link into the portal (`PORTAL_BASE_URL`), emails to a client into the web app
(`FRONTEND_BASE_URL`). Users can switch notification emails off; account emails (verify, reset) are
not optional.

### 3. Free channels only - in-app and email; SMS/OTP is deliberately not built

Email uses the existing `EmailSender` protocol plus an `SmtpEmailSender` (stdlib `smtplib` in a worker
thread with a timeout; header values containing CR/LF are refused, so a crafted address or subject
can't inject headers). Any SMTP server works - a free Gmail/Outlook app-password account is enough to
start, and a provider's free tier later. The default backend just logs, so development needs nothing.

**SMS and phone OTP are not implemented.** Every Indian SMS route is a paid, DLT-registered provider
(template and sender-ID registration) - exactly the kind of paid service that should be the owner's
call, not something to wire up speculatively. Account verification already works by emailed link
(Phase 1), so OTP isn't needed to launch. If the owner chooses a provider, it slots in behind a
sender protocol like email's, and `notify()` grows a channel.

Also **not built**: time-based reminders ("your consultation is in an hour"). They need a scheduler
process; that arrives with deployment (Phase 15) and can reuse the same outbox.

## Consequences

- Both sides see what happened without polling the matter page; the header bell shows an unread count
  (polled every 30 s - there is no push/WebSocket channel yet, in line with the rest of the app).
- A burst of chat messages is **one** unread bell entry until it is read (`coalesce`), so an active
  thread can't bury the feed.
- Verified live: book -> advocate's bell shows 1 and the (logged) email links into the portal;
  accept -> the client's bell and email link into the web app; the email contained no matter title;
  opening a notification marks it read and the badge drops; mark-all-read and the email toggle persist.
- **Needs the owner**: an SMTP account for production (`EMAIL_BACKEND=smtp` - with the default
  `console`, verification and reset emails only reach the log; the app logs a warning at startup in
  production), and a decision on SMS/OTP if it is wanted.

## Alternatives considered

- **Send the email inline in the route and ignore failures**: loses the email whenever SMTP hiccups,
  and can email about an action that then rolls back.
- **FastAPI `BackgroundTasks`**: keeps delivery off the response path but runs outside the
  transaction, so it can't be retried and can announce rolled-back actions; the outbox gives both.
- **Celery/RQ + Redis**: real infrastructure for a volume the platform doesn't have.
- **A `kind` Postgres enum**: every new event would need a migration; a validated string doesn't.
- **Full message text in emails**: convenient, but puts privileged legal communication into mailboxes
  and mail logs.
