import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

const fromHere = (rel: string) => fileURLToPath(new URL(rel, import.meta.url));

export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    globals: true,
  },
  resolve: {
    alias: {
      '@': fromHere('./src'),
      '@legal-platform/shared': fromHere('../../packages/shared/src/index.ts'),
      '@legal-platform/auth': fromHere('../../packages/auth/src/index.ts'),
    },
  },
});
