import { defineConfig } from "vitest/config";
export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.tsx"],
    coverage: {
      provider: "v8",
      include: ["app/**/*.tsx"],
      exclude: ["app/layout.tsx"],
      reporter: ["text", "json-summary", "lcov"],
    },
  },
});
