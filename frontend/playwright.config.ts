import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  // Test the compiled UI behind the same security headers used in deployment.
  use: { baseURL: "http://127.0.0.1:8000", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        "../.venv/bin/uvicorn supportpilot.app:create_app --factory --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/health/ready",
      reuseExistingServer: false,
      env: {
        SUPPORTPILOT_DATABASE_URL: `sqlite:///.state/browser-${process.pid}.db`,
        SUPPORTPILOT_MODE: "fixture",
        SUPPORTPILOT_MAX_INVESTIGATIONS_PER_HOUR: "1000",
        SUPPORTPILOT_API_TOKENS_JSON: JSON.stringify([
          {
            token: "browser-test-token-at-least-24-characters",
            workspace_id: "demo",
            reviewer_id: "browser-reviewer",
          },
        ]),
      },
    },
  ],
});
