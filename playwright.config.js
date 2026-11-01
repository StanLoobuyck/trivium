import { defineConfig, devices } from "@playwright/test";

const iPhone = { ...devices["iPhone 13 Mini"], viewport: { width: 375, height: 812 } };
const laptop = { viewport: { width: 1440, height: 900 } };

// WebKit draait niet op Arch (Ubuntu-bibliotheken ontbreken): lokaal Chromium, in CI ook WebKit.
export default defineConfig({
  testDir: "tests/e2e",
  outputDir: "test-results",
  webServer: { command: "npm run preview", port: 4173, reuseExistingServer: true },
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
