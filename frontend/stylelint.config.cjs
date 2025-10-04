module.exports = {
  extends: [
    'stylelint-config-standard',
    'stylelint-config-recommended-vue',
    'stylelint-config-tailwindcss',
  ],
  rules: {
    'color-hex-length': 'short',
    'declaration-block-trailing-semicolon': null,
    'no-descending-specificity': null,
  },
  overrides: [
    {
      files: ['**/*.vue', '**/*.css'],
      customSyntax: 'postcss-html',
    },
  ],
  ignoreFiles: ['node_modules', '.nuxt', '.output', 'dist'],
}
