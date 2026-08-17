import { defineConfig } from 'vitest/config'

// Deliberately not `vite.config.ts`. The suite covers `src/domain/`, which
// imports no React, no DOM and no Dexie — so it needs none of the plugins, and
// running it in a plain node environment is the cheapest way to keep that
// constraint honest: anything that reaches for `window` fails here.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['tests/**/*.test.ts'],
  },
})
