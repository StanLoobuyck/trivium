import { defineConfig, devices } from "@playwright/test";

const iPhone = { ...devices["iPhone 13 Mini"], viewport: { width: 375, height: 812 } };
const laptop = { viewport: { width: 1440, height: 900 } };

// WebKit draait niet op Arch (Ubuntu-bibliotheken ontbreken): lokaal Chromium, in CI ook WebKit.
export default defineConfig({
  testDir: "tests/e2e",
  outputDir: "test-results",
  webServer: [
    { command: "npm run preview", port: 4173, reuseExistingServer: true },
    {
      command: "mkdir -p node_modules/.cache && rm -f node_modules/.cache/hub-e2e.sqlite* && uv run --project apps/hub uvicorn --factory hub.app:from_env --port 4174",
      port: 4174,
      reuseExistingServer: false,
      env: { HUB_CODE: "testcode-testcode-testcode-testcode", HUB_DB: "node_modules/.cache/hub-e2e.sqlite", HUB_WEB: "apps/inhaal/dist" },
    },
  ],
  use: { baseURL: "http://localhost:4173" },
  projects: [
    { name: "iphone-chromium", use: { ...iPhone, browserName: "chromium" } },
    { name: "laptop-chromium", use: { ...laptop, browserName: "chromium" } },
    { name: "laptop-firefox", use: { ...laptop, browserName: "firefox" } },
    ...(process.env.CI ? [
      { name: "iphone-webkit", use: { ...iPhone, browserName: "webkit" } },
      { name: "laptop-webkit", use: { ...laptop, browserName: "webkit" } },
    ] : []),
  ],
});
