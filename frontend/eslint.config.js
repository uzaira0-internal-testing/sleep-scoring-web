import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      // Bug-catching rules
      'no-constant-binary-expression': 'error',
      'no-constructor-return': 'error',
      'no-self-compare': 'error',
      'no-template-curly-in-string': 'warn',
      'no-unmodified-loop-condition': 'error',
      'no-unreachable-loop': 'error',
      'require-atomic-updates': 'warn',
      'array-callback-return': 'error',
      'no-await-in-loop': 'warn',
      'no-promise-executor-return': 'error',
      'eqeqeq': ['error', 'smart'],
    },
  },
])
