import { defineConfig } from 'vitest/config'

// Plain Node environment (Node 22 has global fetch/Headers built in, which
// is all lib/api.test.ts needs) — no jsdom dependency required. Storage
// (sessionStorage/localStorage) is polyfilled per-test in the test file
// itself, since Node doesn't provide it by default.
export default defineConfig({
  test: {
    environment: 'node',
  },
})
