# Architecture Decision Records

Short, dated records of decisions that are expensive to reverse. One file per
decision, numbered sequentially. Status: `Proposed` → `Accepted` →
(`Superseded by NNNN` | `Deprecated`).

| #    | Title                          | Status   |
| ---- | ----------------------------- | -------- |
| 0001 | Monorepo tooling               | Accepted |
| 0002 | Database provisioning          | Accepted |
| 0003 | Schema ownership and migrations | Accepted |

## Template

```markdown
# NNNN — Title

- Status: Proposed | Accepted | Superseded by NNNN
- Date: YYYY-MM-DD
- Deciders: …

## Context
What forces are at play? What problem are we solving?

## Decision
What we're doing.

## Consequences
Trade-offs accepted; what becomes easier/harder; follow-ups.

## Alternatives considered
Option — why not.
```
