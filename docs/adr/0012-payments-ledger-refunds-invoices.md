# 0012 - Payments: ledger, refunds, invoices (provider-agnostic)

- Status: Accepted
- Date: 2026-09-20
- Deciders: Platform team

## Context

Phase 8 shipped a stub: paying flipped a matter to PAID and nothing was recorded. Phase 10 makes
money a first-class, auditable thing - a payment record, refunds, invoices - and defines who may
cancel a paid matter. The one thing it deliberately does **not** do is pick a payment gateway:
Indian gateways are paid, regulated (KYC / PA-PG licensing) and need the project owner's
accounts, and the standing instruction is to use free options unless asked. So the gateway stays
behind the `PaymentProvider` protocol, with a free mock for development.

## Decisions

### 1. One payment per matter, a separate refund ledger

`payments` (unique `matter_id`) records what was charged; `refunds` is append-only, one row per
refund. `payments.refunded_amount` is a running total kept in the same transaction as the refund
row, and `payments.status` is derived from it (`SUCCEEDED` -> `PARTIALLY_REFUNDED` -> `REFUNDED`,
`rules.status_after_refund`). A refund can never exceed the remainder
(`rules.resolve_refund_amount`); an omitted amount means "refund whatever is left".

All money rules are pure functions in `services/payments/rules.py` with unit tests; the ledger
(`ledger.py`) is the only place that writes. Money is `Decimal` (strings on the wire), quantised
half-up to paise.

### 2. Provider abstraction; the mock is refused in production

`PaymentProvider` now has `charge` and `refund`. `MockPaymentProvider` always succeeds and is
**refused when `APP_ENV=production`**, so a misconfigured deploy fails loudly instead of taking
"payments" that move no money. The real gateway (Razorpay / Cashfree / Stripe India ...) plugs in
behind the same protocol - **an owner decision, see Consequences**.

### 3. A provider failure must not leave a half-cancelled matter

Cancelling a paid matter refunds it in the *same* database transaction
(`refund_matter_in_full`). If the provider's refund call raises, the transaction rolls back and
the matter stays PAID - the user sees an error and can retry, rather than a CANCELLED matter that
was never refunded. Every status-changing matter route also takes a row lock
(`load_matter(..., for_update=True)`) so two concurrent cancel/pay requests can't both act on the
same state (a double refund is impossible: the second sees the updated status).

### 4. Who may cancel a paid matter (policy, enforced in the lifecycle state machine)

| Status      | Consumer                | Advocate |
| ----------- | ----------------------- | -------- |
| PAID        | consultations only      | yes      |
| SCHEDULED   | no (talk to the advocate / admin) | yes |

The advocate can always cancel and the client is refunded in full: if they can't deliver, the
client shouldn't pay for it. A consumer can back out of a paid consultation before it is
scheduled, but **not** a document service (work may already have started) - that goes through the
advocate or an admin refund, which can be partial (`POST /admin/payments/{id}/refund`, admin roles
only, amount optional, reason required). This is a product policy chosen for now; it is a
one-line change in `lifecycle._TRANSITIONS` if the owner wants a different one.

### 5. Earnings are net of refunds

`services/matters/earnings.py` rows are `(status, amount, refunded)`; gross earned is the sum of
`amount - refunded` over CLOSED matters. A cancelled-and-refunded matter therefore earns nothing,
and a *partially* refunded closed matter earns the remainder (the platform fee applies to that
net figure). The portal shows "(-X refunded)" per line.

### 6. Invoices are snapshots, numbered from a database sequence

`invoices` copies the description, client / advocate names, amount and currency at payment time,
so a later profile edit or matter rename can't rewrite history. Numbers come from
`invoice_number_seq` (`INV-2026-000001`): gap-tolerant, never reused, safe under concurrency.

The HTML view is served by the API with `Content-Security-Policy: default-src 'none'`,
`nosniff`, `no-store`, every interpolated value HTML-escaped (a name like `<script>` is inert), and
it requires the Bearer token - so the frontends fetch it and open a blob URL, injecting the same
CSP as a `<meta>` tag first (a blob page has no HTTP headers). Only the matter's participants (and
admins) can read it; others get 404.

**No tax is computed.** The invoice says so explicitly: "GST and other tax treatment is not
calculated on this document." Whether the platform (or the advocates) must charge GST, and on what
base, is a legal / accounting question - **an owner decision** - and a wrong number on an invoice is
worse than an honest caveat.

## Consequences

- The full money loop works end to end and was verified live in a browser against real Postgres:
  pay -> payment card + invoice on both sides -> consumer cancels a paid consultation -> refunded
  in full; advocate cancels a paid matter -> refunded in full and the earnings drop out.
- `GET /payments/mine` lists what you paid (consumer) or received (advocate); admins have
  `GET /admin/payments` and can refund fully or partially.
- **Needs the owner before launch**: (a) the payment gateway (paid, KYC/regulatory); (b) GST /
  tax treatment on invoices; (c) whether advocate payouts are handled by the gateway (route /
  split settlement) or offline - nothing in this phase moves money to advocates.
- Webhooks / async payment confirmation aren't modelled: the mock is synchronous. A real gateway
  adds a `PENDING` state and a webhook handler; the ledger is shaped to allow it.

## Alternatives considered

- **Refund amount stored on the matter**: simpler, but loses the per-refund history that
  reconciliation and disputes need.
- **Deriving `refunded_amount` by summing refunds on every read**: removes a denormalised column but
  makes the status, earnings and locking logic slower and less obvious; the running total is
  updated in the same transaction and covered by tests.
- **Sequential invoice numbers computed as `max()+1`**: races under concurrency; a DB sequence is
  the standard answer.
- **Computing GST now with a hard-coded rate**: rejected - guessing tax is worse than declining to.
