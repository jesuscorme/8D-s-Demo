import { defineConfig } from "@playwright/test";

// Recorrido E2E en Edge contra una instancia ya arrancada (scripts/e2e.ps1 la levanta sobre una BD temporal).
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3020",
    channel: "msedge",
    viewport: { width: 1400, height: 900 },
    trace: "retain-on-failure",
  },
});
