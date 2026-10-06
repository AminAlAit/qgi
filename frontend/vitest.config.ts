import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    // #439: Playwright E2E specs live under tests/e2e/ and use @playwright/test's
    // own `describe`/`test` runner — incompatible with Vitest. E2E is invoked
    // via `npm run test:e2e`, never through Vitest.
    exclude: ["tests/e2e/**", "node_modules/**", "dist/**", ".next/**"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
      // Stub Next.js's `server-only` package — vitest can't resolve it
      // because the package's TS module declaration is consumed only by
      // the Next compiler. Tests run in a Node environment anyway, so
      // the runtime-guard purpose is satisfied without it.
      "server-only": path.resolve(__dirname, "vitest.server-only-stub.ts"),
    },
  },
});
