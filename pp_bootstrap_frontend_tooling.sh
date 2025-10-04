#!/usr/bin/env bash
# pp_bootstrap_frontend_tooling.sh
# Purpose: Installer et configurer ESLint + Prettier + Stylelint côté frontend,
#          brancher les hooks pre-commit au niveau racine, et poser les configs.
# Usage:
#   chmod +x pp_bootstrap_frontend_tooling.sh
#   ./pp_bootstrap_frontend_tooling.sh

set -euo pipefail

ROOT_DIR="$(pwd)"
FE_DIR="${ROOT_DIR}/frontend"

if [ ! -d "$FE_DIR" ]; then
  echo "❌ Dossier 'frontend' introuvable à la racine: ${FE_DIR}"
  exit 1
fi

echo "➡️  Frontend: ${FE_DIR}"

# 1) Fichiers de config FRONTEND (ESLint/Prettier/Stylelint)
echo "📝 Création configs ESLint/Prettier/Stylelint…"

cat > "${FE_DIR}/eslint.config.mjs" <<'ESLINTCONF'
// eslint.config.mjs — ESLint Flat Config pour Nuxt 4 + TS + Vue 3
import js from "@eslint/js"
import typescript from "typescript-eslint"
import vue from "eslint-plugin-vue"

export default [
  { ignores: ["node_modules", ".nuxt", ".output", "dist"] },
  js.configs.recommended,
  ...typescript.configs.recommended,
  ...vue.configs["flat/recommended"],
  {
    files: ["**/*.ts", "**/*.vue"],
    languageOptions: {
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        extraFileExtensions: [".vue"],
      },
    },
    rules: {
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "no-debugger": "warn",
      "vue/html-self-closing": ["warn", {
        html: { void: "always", normal: "never", component: "always" }
      }],
      "vue/no-mutating-props": "error",
      "vue/require-default-prop": "off",
      "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
      "@typescript-eslint/explicit-function-return-type": "off"
    },
  },
]
ESLINTCONF

cat > "${FE_DIR}/.prettierrc.json" <<'PRETTIER'
{
  "semi": false,
  "singleQuote": true,
  "printWidth": 100,
  "trailingComma": "all",
  "plugins": ["prettier-plugin-tailwindcss"]
}
PRETTIER

cat > "${FE_DIR}/.prettierignore" <<'PRETTIERIGNORE'
node_modules
.nuxt
.output
dist
PRETTIERIGNORE

cat > "${FE_DIR}/stylelint.config.cjs" <<'STYLELINT'
module.exports = {
  extends: [
    "stylelint-config-standard",
    "stylelint-config-recommended-vue",
    "stylelint-config-tailwindcss"
  ],
  rules: {
    "color-hex-length": "short",
    "declaration-block-trailing-semicolon": null,
    "no-descending-specificity": null
  },
  overrides: [
    {
      files: ["**/*.vue", "**/*.css"],
      customSyntax: "postcss-html"
    }
  ],
  ignoreFiles: ["node_modules", ".nuxt", ".output", "dist"]
}
STYLELINT

cat > "${FE_DIR}/.stylelintignore" <<'STYLEIGNORE'
node_modules
.nuxt
.output
dist
STYLEIGNORE

# 2) Dépendances dev FRONTEND
echo "📦 Installation deps dev (frontend)…"
cd "$FE_DIR"

# pnpm si présent, sinon npm
if command -v pnpm >/dev/null 2>&1; then
  PKG_MGR="pnpm"
else
  PKG_MGR="npm"
fi

# installe les packages (idempotent)
$PKG_MGR add -D \
  eslint @eslint/js typescript typescript-eslint eslint-plugin-vue \
  prettier prettier-plugin-tailwindcss eslint-config-prettier \
  stylelint stylelint-config-standard stylelint-config-recommended-vue \
  stylelint-config-tailwindcss postcss >/dev/null

# 3) Ajout/MAJ scripts dans package.json (via Node pour éviter jq)
echo "🛠  Ajout des scripts npm (lint/format/stylelint/typecheck)…"
node - <<'NODE'
const fs = require('fs');
const path = require('path');
const pkgPath = path.join(process.cwd(), 'package.json');
const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));

pkg.scripts = Object.assign({}, pkg.scripts, {
  "dev": pkg.scripts?.dev ?? "nuxt dev",
  "build": pkg.scripts?.build ?? "nuxt build",
  "start": pkg.scripts?.start ?? "node .output/server/index.mjs",
  "lint": "eslint .",
  "lint:fix": "eslint . --fix",
  "format": "prettier -w .",
  "stylelint": "stylelint \"**/*.{vue,css}\"",
  "typecheck": "tsc --noEmit"
});

fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + "\n");
console.log("✅ package.json scripts mis à jour");
NODE

cd "$ROOT_DIR"

# 4) Met à jour le .pre-commit-config.yaml racine (on réécrit: version complète)
echo "🔗 Mise à jour .pre-commit-config.yaml (racine)…"
cat > "${ROOT_DIR}/.pre-commit-config.yaml" <<'PRECOMMIT'
repos:
  # --- Formatage Python ---
  - repo: https://github.com/psf/black
    rev: 24.3.0
    hooks:
      - id: black
        language_version: python3

  # --- Organisation imports Python ---
  - repo: https://github.com/PyCQA/isort
    rev: 5.13.2
    hooks:
      - id: isort
        name: isort (python)

  # --- Lint Python ---
  - repo: https://github.com/PyCQA/flake8
    rev: 7.0.0
    hooks:
      - id: flake8

  # --- Analyse sécurité Python ---
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.8
    hooks:
      - id: bandit
        args: ["-r", "backend"]

  # --- Secrets détecteur ---
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets

  # --- Formatage JS/TS/Vue/JSON/MD/CSS (miroir officiel) ---
  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v4.0.0-alpha.8
    hooks:
      - id: prettier
        files: \.(js|ts|vue|json|md|css|scss)$

  # --- ESLint pour Nuxt ---
  - repo: https://github.com/pre-commit/mirrors-eslint
    rev: v8.57.0
    hooks:
      - id: eslint
        files: \.(js|ts|vue)$
        args: ["--max-warnings=0"]

  # --- Vérification fichiers lourds ---
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: check-added-large-files
        args: ["--maxkb=1000"]

  # --- Hooks locaux: déclenchent les outils frontend dans le sous-dossier ---
  - repo: local
    hooks:
      - id: frontend-eslint
        name: frontend eslint (fix)
        entry: bash -lc "cd frontend && npm run -s lint:fix"
        language: system
        pass_filenames: false

      - id: frontend-prettier
        name: frontend prettier (write)
        entry: bash -lc "cd frontend && npm run -s format"
        language: system
        pass_filenames: false

      - id: frontend-stylelint
        name: frontend stylelint (check)
        entry: bash -lc "cd frontend && npm run -s stylelint"
        language: system
        pass_filenames: false
PRECOMMIT

# 5) (Ré)installer les hooks puis premier run
echo "🔧 Installation des hooks pre-commit…"
pre-commit install
pre-commit autoupdate || true
pre-commit run --all-files || true

echo "✅ Frontend tooling opérationnel. Tu peux lancer :"
echo "   - cd frontend && pnpm lint:fix && pnpm format && pnpm stylelint && pnpm typecheck"
