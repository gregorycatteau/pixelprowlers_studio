// eslint.config.mjs — ESLint Flat Config pour Nuxt 4 + TS + Vue 3
import js from '@eslint/js'
import typescript from 'typescript-eslint'
import vue from 'eslint-plugin-vue'

export default [
  { ignores: ['node_modules', '.nuxt', '.output', 'dist'] },
  js.configs.recommended,
  ...typescript.configs.recommended,
  ...vue.configs['flat/recommended'],
  {
    files: ['**/*.ts', '**/*.vue'],
    languageOptions: {
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
        extraFileExtensions: ['.vue'],
      },
    },
    rules: {
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-debugger': 'warn',
      'vue/html-self-closing': [
        'warn',
        {
          html: { void: 'always', normal: 'never', component: 'always' },
        },
      ],
      'vue/no-mutating-props': 'error',
      'vue/require-default-prop': 'off',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/explicit-function-return-type': 'off',
    },
  },
]
