import { defineConfig } from "vitest/config";

export default defineConfig({
  test: { include: ["apps/**/*.test.js", "packages/**/*.test.js", "scripts/**/*.test.js"], exclude: ["**/node_modules/**", "apps/swiftskip/**", "apps/verbatim/**"] },
});
