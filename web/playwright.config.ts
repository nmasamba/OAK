// SPDX-License-Identifier: Apache-2.0
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  use: {
    baseURL: process.env["OAK_WEB_BASE_URL"] ?? "http://127.0.0.1:5173",
    trace: "retain-on-failure",
  },
  reporter: [["list"]],
});
