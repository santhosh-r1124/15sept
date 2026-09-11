import globals from 'globals';
import { baseConfig } from './base.js';

/**
 * ESLint flat config for Next.js apps. Extends the shared base with browser
 * globals. The Next.js plugin rules are applied via each app's own
 * `eslint.config.mjs` (it ships with `eslint-config-next`).
 * @type {import("eslint").Linter.Config[]}
 */
export const nextConfig = [
  ...baseConfig,
  {
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
  },
];

export default nextConfig;
