import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end against a running sp-server (not fixture mode): `SP_E2E_API=http://localhost:8088 pnpm e2e:server`.
 * The web app is built with that API baked in and served on its own port and build directory.
 */
const PORT = Number(process.env.E2E_SERVER_PORT ?? 3108);
const API = process.env.SP_E2E_API ?? "http://localhost:8088";

export default defineConfig({
  testDir: "e2e-server",
  outputDir: "test-results/e2e-server",
  timeout: 180_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: `http://localhost:${PORT}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: {
    command: `pnpm exec next build && pnpm exec next start -p ${PORT}`,
    url: `http://localhost:${PORT}`,
    timeout: 300_000,
    reuseExistingServer: false,
    env: { NEXT_PUBLIC_SP_FIXTURES: "0", NEXT_PUBLIC_SP_API_URL: API, SP_DIST_DIR: ".next-server" },
  },
});
