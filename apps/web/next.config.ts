import path from 'node:path';
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Standalone output for small Docker images. Opt-in via env because the
  // standalone tracer creates symlinks, which need elevated rights on Windows.
  // The Dockerfiles set NEXT_OUTPUT=standalone; local `pnpm build` stays normal.
  output: process.env.NEXT_OUTPUT === 'standalone' ? 'standalone' : undefined,
  // Monorepo: trace workspace deps from the repo root when bundling standalone.
  outputFileTracingRoot: path.join(import.meta.dirname, '../../'),
  // Compile workspace TS packages that ship raw source.
  transpilePackages: ['@legal-platform/shared', '@legal-platform/auth'],
  eslint: {
    // Lint is a separate CI job (`pnpm lint`); don't run it during `next build`.
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: false,
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        ],
      },
    ];
  },
};

export default nextConfig;
