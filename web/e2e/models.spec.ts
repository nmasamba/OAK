// SPDX-License-Identifier: Apache-2.0
import { execSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const REPO_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
);

// A synthetic key in the repository's test convention. The whole point of this spec is that
// it never comes back, so it must be distinctive enough to find anywhere it might.
const TEST_KEY = "oak-test-key-openai-web-0123456789ab";

function api(command: string): string {
  return execSync(`docker compose exec -T api ${command}`, {
    cwd: REPO_ROOT,
    stdio: "pipe",
  }).toString();
}

function requireStack() {
  test.skip(
    process.env["OAK_E2E_DOCKER"] !== "1",
    "requires the compose stack (set OAK_E2E_DOCKER=1)",
  );
}

test.describe("model settings", () => {
  test.afterEach(() => {
    if (process.env["OAK_E2E_DOCKER"] === "1") {
      try {
        api("oak models clear");
        api("oak models remove-key huggingface");
      } catch {
        // The test may have failed before storing anything.
      }
    }
  });

  test("a key can be stored and removed, and never comes back", async ({
    page,
  }) => {
    requireStack();
    const token = api("oak models token").trim();
    expect(token.length).toBeGreaterThan(15);

    // Every response body the page receives is inspected, not just the ones it renders.
    const leaked: string[] = [];
    page.on("response", async (response) => {
      try {
        const body = await response.text();
        if (body.includes(TEST_KEY)) {
          leaked.push(response.url());
        }
      } catch {
        // Redirects and empty bodies have nothing to read.
      }
    });

    await page.goto(`/#token=${encodeURIComponent(token)}`);
    await page.goto("/settings/models");
    await expect(
      page.getByRole("heading", { name: "Models", level: 1 }),
    ).toBeVisible();

    // The fragment carried the token, so the paste form is gone and the address bar is clean.
    expect(page.url()).not.toContain("token=");
    await expect(page.getByLabel("Model family")).toBeVisible();

    await page.getByLabel("Model family").selectOption("huggingface");
    await page.getByLabel("API key").fill(TEST_KEY);
    await page.getByRole("button", { name: "Store key" }).click();

    await expect(page.getByText(/A key is stored in the/)).toBeVisible();
    await expect(page.getByText(/fingerprint/)).toBeVisible();
    // The field is cleared on submit so the key does not sit in the DOM.
    await expect(page.getByLabel("API key")).toHaveValue("");
    expect(await page.content()).not.toContain(TEST_KEY);

    await page.getByLabel("Model identifier").fill("openai/gpt-oss-120b");
    await page.getByRole("button", { name: "Use this model" }).click();
    await expect(
      page.getByText("huggingface/openai/gpt-oss-120b").first(),
    ).toBeVisible();

    // The masthead says which interpreter the workspace will use.
    await expect(page.locator(".masthead")).toContainText(
      "huggingface/openai/gpt-oss-120b",
    );

    await page.getByRole("button", { name: "Remove key" }).click();
    await expect(
      page.getByText("No key is stored for this family."),
    ).toBeVisible();

    expect(leaked).toEqual([]);
  });

  test("without a token the page asks for one and changes nothing", async ({
    page,
  }) => {
    requireStack();
    await page.goto("/settings/models");
    await expect(
      page.getByRole("heading", {
        name: "Paste the model-configuration token",
      }),
    ).toBeVisible();
    await expect(page.getByLabel("Model family")).toHaveCount(0);
  });

  test("the settings page has no accessibility violations", async ({
    page,
  }) => {
    requireStack();
    const token = api("oak models token").trim();
    await page.goto(`/#token=${encodeURIComponent(token)}`);
    await page.goto("/settings/models");
    await expect(page.getByLabel("Model family")).toBeVisible();

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    expect(results.violations).toEqual([]);
  });

  test("a plain-language brief is the default, and says so when no model is set", async ({
    page,
  }) => {
    requireStack();
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Describe what you want to build" }),
    ).toBeVisible();
    await expect(page.getByLabel("Brief content")).toBeVisible();
    await expect(
      page.locator("p.hint", {
        hasText: /No model is configured|A model is configured/,
      }),
    ).toBeVisible();
  });
});
