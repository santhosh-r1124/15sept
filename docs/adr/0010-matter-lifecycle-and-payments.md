# 0010 — Matter lifecycle, fee quoting, and a payments stub

- Status: Accepted
- Date: 2026-09-20
- Deciders: Platform team

## Context

Phase 8 turns advocate discovery (Phase 7) into an engagement: "booking -> payment ->
consultation -> matter closed" (roadmap), with FRD §9 offering 15/30/60-minute
consultations plus document services, and FRD §10 giving the advocate accept/reject, chat,
schedule and close. Four things needed deciding.

## Decisions

### 1. A pure state machine decides what's legal; routes only enforce it

`app/services/matters/lifecycle.py` holds one table of `(action, actor, from_status) ->
to_status` and two type-dependent rules (only consultations are scheduled; a consultation
can't close straight from PAID). The routes load the matter, work out the caller's role
*relative to that matter*, ask the table, then persist. No DB or I/O in the module, so
`test_matter_lifecycle.py` checks every action x actor x status x service-type combination
(terminal states allow nothing; every non-terminal state has a way forward) instead of
sampling happy paths.

Statuses: `REQUESTED -> ACCEPTED -> PAID -> SCHEDULED -> CLOSED`, plus `REJECTED` and
`CANCELLED`. Non-participants get a **404, not a 403** — a matter's existence isn't
something to leak. Admins can read any matter but not act on one.

**Paid matters can't be cancelled yet.** Cancelling after payment implies a refund, which is
Phase 10's job; until then a paid matter can only move forward (schedule / close).

### 2. Fee quoting: profile fee is the 60-minute price, prorated; advocates can override

`AdvocateProfile.consultation_fee` (Phase 1) is one number with no stated duration, while the
FRD offers three durations. Assumption: it is the price of a **60-minute** consultation,
prorated linearly to 15/30 minutes (`services/matters/pricing.py`, rounded half-up to paise).
This is only the *prefill*: the advocate confirms or overwrites it when accepting, and
document services have no formula at all (scope varies too much), so they must be quoted on
accept (422 otherwise). The consumer pays only after seeing the final quote. The profile page
states the assumption ("per hour, prorated for 15/30 min") so it isn't hidden. If the product
owner wants per-duration prices, that's a schema change on `AdvocateProfile`, not a rewrite.

### 3. Payments: an interface plus a free mock — the gateway is deliberately NOT chosen here

Booking needs *something* to charge, but which Indian payment gateway to use is a paid,
regulated decision that belongs to the project owner (and the standing instruction is no paid
services without asking). So `app/services/payments/` defines a `PaymentProvider` protocol and
ships a `MockPaymentProvider` that always succeeds, keyed by matter id for idempotency.
**The mock is refused when `APP_ENV=production`** (503 `payments_not_configured`), so it can
never take "payments" from real users. Phase 10 builds refunds, invoices and the payments
ledger on this same interface and is where the gateway decision gets surfaced.
`matters.payment_reference`/`paid_at` are convenience fields until Phase 10 adds a proper
`payments` table.

### 4. Scope: in-app chat and scheduling now; voice/video and file exchange later

FRD §9 lists in-app chat, voice, video and scheduling "depending on the platform
architecture". Shipped: a per-matter message thread (polled every 10s by the UI — no
websocket infrastructure yet) and advocate-set appointment times. **Not shipped:** voice/video
(WebRTC needs signalling and TURN infrastructure, and a provider choice — a Phase 15-adjacent
decision) and document upload/exchange ("request documents", "upload final documents"), which
roadmap Phase 9 assigns to the advocate portal. The thread is read-only once a matter reaches
a terminal state. `MatterMessage.created_at` uses `clock_timestamp()`, not `now()`, so thread
order is stable even for messages written in one transaction.

## Consequences

- Every transition is unit-tested exhaustively and integration-tested over real HTTP against
  real Postgres (`test_matters.py`: full consultation and document-service lifecycles, illegal
  transitions -> 409, timezone/future validation, outsider 404s, scoped listing, thread rules).
- The consumer UI (`/matters`, `/matters/[id]`, booking form on the advocate profile) is
  complete; the **advocate** side of the same actions exists in the API but has no UI until
  Phase 9.
- Anonymous booking isn't possible — a matter needs an identity for payment and messaging.

## Alternatives considered

- **Pay-before-accept** (charge on request, refund on reject): rejected — needs the refund
  machinery first, and an advocate quote can differ from any estimate.
- **Integrate a real gateway's test mode now**: rejected — picks a vendor (and its per-
  transaction fees) on the owner's behalf.
- **WebSockets for the thread**: rejected for now — polling meets the need with no new
  infrastructure; revisit with real load.
