# 0008 — Risk scoring folded into the existing classification call, not a second LLM call

- Status: Accepted
- Date: 2026-09-15
- Deciders: Platform team

## Context

Phase 5 needed the risk engine named in the roadmap: score every query
LOW/MEDIUM/HIGH/CRITICAL (`packages/shared/src/legal.ts::RISK_LEVELS`, already
defined since Phase 0) and recommend an advocate for HIGH/CRITICAL
(`ADVOCATE_RECOMMENDATION_MESSAGE`, stubbed since Phase 2/3 for this exact
purpose).

Phase 2's `classify_query` already makes one forced-tool-call to Claude per
message to get `category`/`jurisdiction_scope`/`is_out_of_scope`. The
straightforward "services/legal-classifier + services/risk-engine" reading of
the roadmap could mean two independent LLM calls: one for category, a second
dedicated one for risk. That doubles classification-side LLM spend per chat
message for a signal that comes from reading the exact same input.

## Decision

**One classification call, four fields.** `risk_level` was added as a fourth
enum property on the existing `classify_legal_query` tool call
(`app/services/legal_classifier.py`) rather than introducing a second Claude
round trip. Rationale:

- Claude is already reading the full message to judge category and
  jurisdiction; asking it to also judge urgency on that same read adds a few
  output tokens, not a new request.
- A truly independent second call, reading the same message cold, could
  reach a different judgement than the first about the same input — two
  signals that can silently disagree are worse than one that can't.
- Consistent with the standing no-paid-services/minimize-cost instruction —
  see [[feedback-free-services-only]] — even though Claude itself isn't free,
  halving the classification-side call count for equivalent signal is the
  same instinct applied to API spend broadly.

**Module split still happened, just not as two LLM calls:**

- `app/services/legal_classifier.py` — owns the taxonomy (`LEGAL_CATEGORIES`,
  `JURISDICTION_SCOPES`, `RISK_LEVELS`), the tool schema, and the one Claude
  call. This is what Phase 2's `llm.py` docstring predicted ("Phase 5
  formalises this into a proper service... this module should delegate to it
  instead of reimplementing the taxonomy inline") — extracted out of `llm.py`
  verbatim, not rewritten.
- `app/services/risk_engine.py` — pure decision logic, no LLM, no I/O:
  `requires_advocate_recommendation(risk_level) -> bool`, mirroring
  `packages/shared/src/legal.ts::requiresAdvocate`. This is the actual
  "engine" — what to *do* with a risk level, kept separate from how the risk
  level was *produced* so either can change independently (e.g. a future
  rules-based override on top of the LLM's judgement wouldn't touch
  `legal_classifier.py` at all).
- `app/services/anthropic_client.py` — the `get_client()`
  configured/unconfigured check, extracted out of `llm.py` so
  `legal_classifier.py` doesn't duplicate it.
- `app/services/llm.py` — now only grounded answer generation (Phase 4);
  classification fully moved out, per the plan already on record.

**Fallback on an unparseable risk value is the conservative direction.**
Unlike `jurisdiction_scope`, `risk_level` has no "UNKNOWN" enum member — the
product only has four levels, all specific. When parsing fails (the model
didn't call the tool, or returned a value outside the enum — both already-rare
edge cases since it's a forced tool call), the fallback is `"HIGH"`, not a
made-up fifth value: under-escalating a genuinely urgent matter is a worse
failure than an unneeded advocate nudge.

**Where the recommendation gets appended:** in
`app/api/v1/routes/chat.py::send_message`, after the answer text is decided
(grounded answer or `INSUFFICIENT_EVIDENCE_MESSAGE`) but only on the in-scope
path — an out-of-scope reply already declines to help and isn't assessing
legal risk. HIGH/CRITICAL applies to *both* the grounded-answer and
insufficient-evidence outcomes: if anything, "we can't fully answer this *and*
it looks urgent" is exactly when the advocate nudge matters most.

## Consequences

- `ChatMessage.risk_level` (migration 0006) is a plain indexed string column,
  not a foreign key to some risk taxonomy table — matches the existing
  `legal_category`/`jurisdiction_scope` columns' shape. Indexed specifically
  for the Phase 12 admin "high-risk query review" queue named in the roadmap,
  not speculatively.
- Chat's LLM call count is unchanged from Phase 2/4: exactly one
  classification call, plus one generation call when in scope and grounded.
  Risk scoring added zero new round trips.
- A single call now has to get *four* things right instead of three. If
  future testing shows risk quality suffering because it's crowded into the
  same call as category/jurisdiction, splitting it into its own call is a
  contained change (a new tool + a second `classify_query`-shaped function in
  `legal_classifier.py`) — nothing about `risk_engine.py` or the callers in
  `chat.py` would need to change, since they only see a `risk_level` string.

## Alternatives considered

- **A second, dedicated Claude call for risk** — rejected: doubles
  classification-side LLM cost and latency per message for a signal read from
  the same input, and risks the two calls disagreeing about the same message.
- **A separate deterministic/keyword-based risk classifier** (e.g. regex for
  "arrested", "summons", "raid") instead of an LLM judgement — rejected as
  the sole mechanism: keyword lists are brittle and don't generalize across
  phrasing or the many legal categories in scope; nothing rules this out
  later as a *supplementary* rule layer on top of the LLM's `risk_level`
  (`risk_engine.py` is exactly where that would live), but wasn't needed to
  ship Phase 5.
- **Fold risk into `category`** (e.g. an `ADVOCATE_REQUIRED_CRITICAL`
  category) instead of a separate axis — rejected: category and risk are
  genuinely different questions (what kind of law vs. how urgent), and the
  FRD and `packages/shared/src/legal.ts` already model them as independent
  fields; conflating them would need undoing later when Phase 12's dashboard
  wants to filter by either independently.
