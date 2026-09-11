import js from '@eslint/js';
import eslintConfigPrettier from 'eslint-config-prettier';
import turbo from 'eslint-plugin-turbo';
import tseslint from 'typescript-eslint';
import globals from 'globals';

/**
 * Shared flat ESLint config for TypeScript packages in the monorepo.
 * TS-specific rules are scoped to TS files so config files (`*.mjs`) and plain
 * JS are not run through the TS parser.
 */
export const baseConfig = tseslint.config(
  { ignores: ['dist/**', '.next/**', '.turbo/**', 'coverage/**', 'node_modules/**'] },
  js.configs.recommended,
  {
    files: ['**/*.{ts,tsx,mts,cts}'],
    extends: [tseslint.configs.recommended],
    plugins: { turbo },
    rules: {
      'turbo/no-undeclared-env-vars': 'warn',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/consistent-type-imports': [
        'error',
        { prefer: 'type-imports', fixStyle: 'inline-type-imports' },
      ],
    },
  },
  {
    languageOptions: { globals: { ...globals.node } },
  },
  eslintConfigPrettier,
);

export default baseConfig;
