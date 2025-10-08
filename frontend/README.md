# Nuxt Minimal Starter

Look at the [Nuxt documentation](https://nuxt.com/docs/getting-started/introduction) to learn more.

## Setup

Make sure to install dependencies:

```bash
# npm
npm install

# pnpm
pnpm install

# yarn
yarn install

# bun
bun install
```

## Development Server

Start the development server on `http://localhost:3000`:

```bash
# npm
npm run dev

# pnpm
pnpm dev

# yarn
yarn dev

# bun
bun run dev
```

## Production

Build the application for production:

```bash
# npm
npm run build

# pnpm
pnpm build

# yarn
yarn build

# bun
bun run build
```

Locally preview production build:

```bash
# npm
npm run preview

# pnpm
pnpm preview

# yarn
yarn preview

# bun
bun run preview
```

Check out the [deployment documentation](https://nuxt.com/docs/getting-started/deployment) for more information.

## Lint & Format

Recommended local quality checks:

```bash
# ESLint (JS/TS/Vue)
npm run lint

# TypeScript type-check
npm run typecheck

# Stylelint (CSS/Tailwind)
npm run stylelint

# Prettier (format) — if no npm script is defined, use npx directly:
npm run format || npx prettier -w .
```

Notes:
- Ensure your editor uses the project Prettier config (.prettierrc) and ESLint config (eslint.config.mjs).
- Tailwind class sorting is handled by the Tailwind v4/Vite integration; Stylelint checks basic rules.

## Health page (Sprint 0)

A minimal health page is available to verify the app and correlation headers:

- URL (via Caddy): http://dev.localhost/health
- Displays the incoming `X-Request-ID` and the ID returned by the backend (`/api/hello`)

Example (set a custom correlation ID and check propagation end-to-end):

```bash
curl -sS -H 'X-Request-ID: demo-123' http://dev.localhost/health
```

Expected:
- The page shows the same `X-Request-ID` received by Nuxt (inbound).
- The call to the backend `/api/hello` echoes the `X-Request-ID` in the response headers/body.


## Tests & Coverage (Vitest)

This project uses Vitest for unit tests. Basic commands:
```bash
# run tests once (CI-friendly)
npm run test -- --run

# run tests in watch mode
npm run test
```

Generate a coverage report:
```bash
# text summary + lcov (saved under coverage/)
npm run test -- --coverage --run
```

Notes:
- JSDOM is available for component tests. If you start testing Vue components, set the test environment to jsdom (either in a vitest.config.ts or in package.json under "vitest": { "environment": "jsdom" }).
- CI can publish the lcov report artifact from the coverage/ directory. Keep thresholds informative at first, then tighten as the suite grows.
