# 0004 — Domain logic lives in apps/api, not services/* (for now)

- Status: Accepted
- Date: 2026-09-11
- Deciders: Platform team

## Context

The Phase 0 architecture put domain logic in standalone `services/*` uv
projects (`rag`, `document-processing`, `legal-classifier`, `risk-engine`,
`notifications`), imported by `apps/api` as path dependencies. Phase 2 needed
query classification + generation; Phase 3 needs the ingestion pipeline. Both
are exactly the kind of logic `services/legal-classifier` and
`services/document-processing` were meant to hold.

Wiring a real path dependency from `apps/api` onto a sibling `services/*`
project requires either (a) a `uv` workspace spanning the repo, which in turn
requires (b) the API's Docker build context to be the repo root (like the
Next.js apps already are) instead of `apps/api` alone — `apps/api/Dockerfile`
currently only has access to `apps/api/`. That's a real, somewhat invasive
infra change (Dockerfile, docker-compose.yml, CI), not a small one.

## Decision

For Phase 2 and Phase 3, the actual logic lives directly in `apps/api`:

- Phase 2: `app/services/llm.py` (Claude classification + generation)
- Phase 3: `app/services/ingestion/*` (fetch/extract/clean/chunk/embed/search)

`services/legal-classifier`, `services/document-processing`, etc. remain
Phase-labeled stubs (`services/README.md`). This is a deliberate, tracked
deviation from the Phase 0 architecture doc, not silent drift.

## Consequences

- Momentum: Phase 2/3 shipped without a Docker/uv-workspace refactor as a
  prerequisite.
- Debt: `apps/api/app/services/` is accumulating logic that was meant to be
  modular and independently deployable. `services/rag` (Phase 4) is the
  natural point to pay this down, since it's the first service that plausibly
  needs to scale or be called from more than one place.
- When paid down: convert to a `uv` workspace (root `pyproject.toml` with
  `[tool.uv.workspace] members = ["apps/api", "services/*"]`), change
  `apps/api`'s Dockerfile + `docker-compose.yml` build context to the repo
  root (mirroring `apps/web`/`apps/advocate-portal`'s Dockerfiles already),
  and move `app/services/llm.py` → `services/legal-classifier` /
  `app/services/ingestion/` → `services/document-processing` behind the same
  function signatures so callers barely change.

## Alternatives considered

- **Do the workspace/Docker refactor now** — architecturally "correct" sooner,
  but a detour from delivering Phase 2/3 functionality, and premature before
  a second real consumer of these services exists.
- **Duplicate logic into both places** — worse: two copies to keep in sync,
  no actual benefit over picking one location honestly.
