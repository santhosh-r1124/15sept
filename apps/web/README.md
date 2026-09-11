# @legal-platform/web

Consumer-facing Next.js 15 app (App Router, React 19, Tailwind v4).

```bash
cp .env.example .env.local
pnpm --filter @legal-platform/web dev     # http://localhost:3000
```

Needs the API running (`pnpm stack:up` or `pnpm api:dev`). Health wiring:
`/` renders `<SystemStatus>` → `GET /api/health` (route handler) → API
`GET /health/ready`.

- `src/lib/env.ts` — zod-validated public env (fails fast on misconfig)
- `src/lib/api-client.ts` — typed fetch wrapper, parses the shared error envelope
- `src/app/api/health/route.ts` — aggregated web+api health for the UI
