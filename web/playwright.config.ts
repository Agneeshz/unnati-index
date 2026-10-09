import { defineConfig, devices } from "@playwright/test";

// Browser checks against a production build (`npm run build` first). CI uses Playwright's
// Chromium; locally, PW_CHANNEL=msedge (or chrome) uses an installed browser instead of a download.
const port = Number(process.env.PORT ?? 3100);

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: process.env.BASE_URL ?? `http://localhost:${port}`,
    channel: process.env.PW_CHANNEL || undefined,
    trace: "retain-on-failure",
  },
  projects: [{ name: "desktop", use: { ...devices["Desktop Chrome"], channel: process.env.PW_CHANNEL || undefined } }],
  webServer: process.env.BASE_URL
    ? undefined
    : { command: `npx next start -p ${port}`, port, reuseExistingServer: !process.env.CI, timeout: 120_000 },
});
