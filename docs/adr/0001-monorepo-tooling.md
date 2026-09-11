# 0001 — Monorepo tooling

- Status: Accepted
- Date: 2026-09-10
- Deciders: Platform team

## Context

The platform is polyglot: two Next.js apps and shared TypeScript packages on one
side, a FastAPI app and several Python domain services on the other. We want one
repository, fast incremental installs/builds, and a cached task graph, without
adopting a heavyweight build system.

## Decision

- **JavaScript/TypeScript**: pnpm workspaces (`pnpm-workspace.yaml`) for
  linking + installs, **Turborepo** (`turbo.json`) for the task graph
  (`build`, `lint`, `typecheck`, `test`) with caching.
- **Python**: **uv** per project (`apps/api`, each `services/*`), lockfile
  committed. No shared Python virtualenv across projects.
- Shared TS packages ship **raw source** (no build step); Next compiles them via
  `transpilePackages`, and path aliases point at `src/` for typechecking.

## Consequences

- One `pnpm install` bootstraps the JS side; `uv sync` per Python project.
- CI runs two lanes (JS via Turborepo, Python via uv) — see `.github/workflows/ci.yml`.
- Turborepo remote caching can be enabled later with zero code change.
- Contributors need both Node/pnpm and Python/uv installed.

## Alternatives considered

- **Nx** — more power (generators, graph) but heavier config and a learning
  curve we don't need yet.
- **pnpm workspaces only** (no Turborepo) — fine now, but we'd add task
  orchestration/caching again soon; cheap to include up front.
- **Bazel / Pants** (single system for both languages) — strong hermeticity,
  disproportionate operational cost for this team size.
