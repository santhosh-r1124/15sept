# syntax=docker/dockerfile:1.7
# Build context is the REPO ROOT:  docker build -f apps/advocate-portal/Dockerfile .
ARG NODE_VERSION=22

FROM node:${NODE_VERSION}-slim AS base
ENV PNPM_HOME=/pnpm PATH="/pnpm:$PATH"
RUN corepack enable
WORKDIR /repo

FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc* ./
COPY apps/web/package.json apps/web/
COPY apps/advocate-portal/package.json apps/advocate-portal/
COPY packages/shared/package.json packages/shared/
COPY packages/auth/package.json packages/auth/
COPY packages/database/package.json packages/database/
COPY packages/eslint-config/package.json packages/eslint-config/
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile

FROM base AS build
ENV NEXT_TELEMETRY_DISABLED=1 NEXT_OUTPUT=standalone
COPY --from=deps /repo/node_modules ./node_modules
COPY --from=deps /repo/apps/advocate-portal/node_modules ./apps/advocate-portal/node_modules
COPY . .
RUN pnpm --filter @legal-platform/advocate-portal build

FROM node:${NODE_VERSION}-slim AS runner
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
RUN groupadd --system nodejs && useradd --system --gid nodejs nextjs

COPY --from=build --chown=nextjs:nodejs /repo/apps/advocate-portal/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /repo/apps/advocate-portal/.next/static ./apps/advocate-portal/.next/static
COPY --from=build --chown=nextjs:nodejs /repo/apps/advocate-portal/public ./apps/advocate-portal/public

USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["node", "apps/advocate-portal/server.js"]
