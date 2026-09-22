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

// A synthetic token in the repository's test convention. The whole point of this spec is
// that it never comes back, so it must be distinctive enough to find anywhere it might.
// Storing it makes the API ask huggingface.co about it once (nothing is generated); the
// Hub answers that it is not a token it knows, and that verdict is what the page shows.
const TEST_KEY = "oak-test-key-huggingface-web-0123456789";

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
        api("oak models clear huggingface");
        api("oak models clear local");
        api("oak models remove-key huggingface");
      } catch {
        // The test may have failed before storing anything.
      }
    }
  });

  test("a token can be stored, verified, pinned against and removed, and never comes back", async ({
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
    await expect(page.getByLabel("Hugging Face token")).toBeVisible();
    await expect(
      page.getByText("No Hugging Face token is stored on this machine."),
    ).toBeVisible();

    await page.getByLabel("Hugging Face token").fill(TEST_KEY);
    await page.getByRole("button", { name: "Store and verify" }).click();

    await expect(page.getByText(/A token is stored in the/)).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByText(/fingerprint/)).toBeVisible();
    // The verdict is shown with the time it was given — whatever the Hub said about a
    // token it has never issued — never a bare tick.
    await expect(page.locator("[data-verdict]")).toBeVisible();
    await expect(page.locator("[data-verdict]")).toContainText(/ago|just now/);
    // The field is cleared on submit so the token does not sit in the DOM.
    await expect(page.getByLabel("Hugging Face token")).toHaveValue("");
    expect(await page.content()).not.toContain(TEST_KEY);

    // Local AI needs nothing but a model name; pinning one makes the mode available.
    await page.getByLabel("Model the local server serves").fill("qwen3:8b");
    await page.getByRole("button", { name: "Use this model" }).click();
    await expect(page.getByText("Pinned qwen3:8b for Local AI.")).toBeVisible();

    // The intake form offers the three ways to read a brief, with Local AI now enabled.
    await page.goto("/");
    const chooser = page.getByLabel("How should this brief be read?");
    await expect(chooser).toBeVisible();
    await expect(chooser.locator("option")).toHaveCount(3);
    await expect(chooser).toHaveValue("deterministic");
    await chooser.selectOption("local");
    await expect(page.locator("[data-mode-detail=local]")).toContainText(
      "qwen3:8b",
    );
    // The masthead names the Online AI pair that would run and the token's verdict age.
    await expect(page.locator(".masthead")).toContainText("Online AI:");
    await expect(page.locator(".masthead")).toContainText("token");

    await page.goto("/settings/models");
    await page.getByRole("button", { name: "Remove token" }).click();
    await expect(
      page.getByText("No Hugging Face token is stored on this machine."),
    ).toBeVisible();

    expect(leaked).toEqual([]);
  });

  test("the mode chosen on the intake form reaches the case page, and a failed model run recovers deterministically", async ({
    page,
  }) => {
    requireStack();
    const token = api("oak models token").trim();
    api("oak models select local qwen3:8b");
    const interpretRequests: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes(":interpret")) {
        interpretRequests.push(request.url());
      }
    });

    await page.goto(`/#token=${encodeURIComponent(token)}`);
    await page.goto("/");
    const chooser = page.getByLabel("How should this brief be read?");
    await chooser.selectOption("local");
    await page.getByLabel("Brief file name").fill("brief.md");
    await page
      .getByLabel("Brief content")
      .fill(
        "A support desk wants drafted answers from public manuals, reviewed by a person.",
      );
    await page.getByRole("button", { name: "Create case" }).click();

    // The case page starts from the choice made on the form.
    await expect(page.getByLabel("How should this brief be read?")).toHaveValue(
      "local",
    );
    await page.getByRole("button", { name: "Interpret brief" }).click();
    // No loopback model server runs under Compose, so Local AI fails honestly and nothing
    // is recorded; the recovery re-runs the interpretation deterministically.
    await expect(
      page.getByText("The model could not interpret this brief."),
    ).toBeVisible({ timeout: 60_000 });
    await page
      .getByRole("button", { name: "Interpret without the model" })
      .click();
    await expect(page.getByText("needs_confirmation")).toBeVisible({
      timeout: 30_000,
    });

    expect(
      interpretRequests.some((url) => url.includes("interpreter=local")),
    ).toBe(true);
    expect(
      interpretRequests.some((url) =>
        url.includes("interpreter=deterministic"),
      ),
    ).toBe(true);
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
    await expect(page.getByLabel("Hugging Face token")).toHaveCount(0);
  });

  test("the settings page has no accessibility violations", async ({
    page,
  }) => {
    requireStack();
    const token = api("oak models token").trim();
    await page.goto(`/#token=${encodeURIComponent(token)}`);
    await page.goto("/settings/models");
    await expect(page.getByLabel("Hugging Face token")).toBeVisible();

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    expect(results.violations).toEqual([]);
  });

  test("a plain-language brief is the default, read deterministically unless chosen otherwise", async ({
    page,
  }) => {
    requireStack();
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Describe what you want to build" }),
    ).toBeVisible();
    await expect(page.getByLabel("Brief content")).toBeVisible();
    const chooser = page.getByLabel("How should this brief be read?");
    await expect(chooser).toHaveValue("deterministic");
    await expect(
      page.locator("[data-mode-detail=deterministic]"),
    ).toContainText("nothing leaves");
  });
});
