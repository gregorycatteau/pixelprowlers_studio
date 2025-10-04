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
