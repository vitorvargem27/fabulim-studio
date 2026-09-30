// @ts-check
const eslint = require('@eslint/js');
const tseslint = require('typescript-eslint');
const angular = require('angular-eslint');

module.exports = tseslint.config(
  { ignores: ['dist/**', '.angular/**', 'node_modules/**', 'playwright-report/**', 'test-results/**'] },
  {
    files: ['**/*.ts'],
    extends: [eslint.configs.recommended, ...tseslint.configs.recommended, ...tseslint.configs.stylistic, ...angular.configs.tsRecommended],
    processor: angular.processInlineTemplates,
    rules: {
      '@angular-eslint/directive-selector': ['error', { type: 'attribute', prefix: 'fab', style: 'camelCase' }],
      '@angular-eslint/component-selector': ['error', { type: 'element', prefix: ['fab', 'app'], style: 'kebab-case' }],
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/consistent-type-definitions': 'off',
      '@typescript-eslint/no-inferrable-types': 'off',
      '@typescript-eslint/array-type': 'off',
    },
  },
  {
    files: ['**/*.html'],
    extends: [...angular.configs.templateRecommended, ...angular.configs.templateAccessibility],
    rules: {
      '@angular-eslint/template/click-events-have-key-events': 'off', // o backdrop da gaveta é decorativo (Esc e o botão fecham)
      '@angular-eslint/template/interactive-supports-focus': 'off',
    },
  },
  {
    files: ['e2e/**/*.ts', '**/*.spec.ts'],
    rules: { '@typescript-eslint/no-non-null-assertion': 'off' },
  },
);
