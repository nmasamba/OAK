// SPDX-License-Identifier: Apache-2.0
// Captures the user-manual screenshots from a real journey against the Compose stack.
// Gated: set OAK_MANUAL_SCREENS=1 (and have `docker compose up -d --build` healthy), then
//   OAK_MANUAL_SCREENS=1 pnpm --dir web exec playwright test e2e/manual-screens.spec.ts
// Output lands in docs/manual/assets/; the manual embeds those files by relative path.
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

import { LOCAL_FIXTURE_TARGET, briefFor, compose } from "./support";

const ASSETS = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "docs",
  "manual",
  "assets",
);

async function shoot(page: Page, name: string) {
  await page.screenshot({
    path: path.join(ASSETS, `${name}.png`),
    fullPage: false,
  });
}

test("capture the manual screenshots from the reference journey", async ({
  page,
}) => {
  test.skip(
    process.env["OAK_MANUAL_SCREENS"] !== "1",
    "manual screenshot capture only (set OAK_MANUAL_SCREENS=1)",
  );
  test.setTimeout(360_000);
  await page.setViewportSize({ width: 1200, height: 800 });
  // Fetched first, although only chapter 4's figure uses it: compose() refuses a Compose
  // project that does not serve the suite's origins, and it should do so before any file
  // in docs/manual/assets is overwritten.
  const token = compose("exec -T api oak models token").trim();

  const slug = `getting-started-${Date.now()}`;
  const caseId = `design-case.${slug}`;

  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Design cases" }),
  ).toBeVisible();
  await shoot(page, "01-case-list");

  await page.getByLabel("Brief file name").fill(`${slug}.yaml`);
  await page.getByLabel("Brief content").fill(briefFor(slug));
  await shoot(page, "02-create-case");
  await page.getByRole("button", { name: "Create case" }).click();
  await expect(page).toHaveURL(new RegExp(`/cases/${caseId}$`));
  await expect(page.getByText("draft", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Interpret brief" }).click();
  await expect(
    page.getByText("needs_confirmation", { exact: true }),
  ).toBeVisible();
  await shoot(page, "03-case-detail");

  await page
    .getByRole("link", { name: "reviewing the interpreted claims" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Interpreted claims and their origin" }),
  ).toBeVisible();
  await shoot(page, "04-brief-review");
  await page.goBack();

  await page
    .getByRole("link", { name: /Answer the 5 ranked questions/ })
    .click();
  await expect(
    page.getByRole("heading", { name: /5 ranked questions block/ }),
  ).toBeVisible();
  await shoot(page, "05-questions");
  const questions = page.locator("fieldset");
  await expect(questions).toHaveCount(5);
  for (let index = 0; index < 5; index += 1) {
    const question = questions.nth(index);
    const isVolume = (await question.innerText()).includes("document volume");
    await question
      .getByRole("radio", {
        name: isVolume
          ? "Correct it to a different value"
          : "Confirm the current value",
      })
      .check();
    if (isVolume) {
      await question
        .getByLabel("Value (JSON or plain text)")
        .fill("Synthetic fixture of 1000 public documents refreshed daily.");
    }
    await question
      .getByLabel("Rationale")
      .fill("Verified against the public reference fixture for this journey.");
  }
  await page.getByRole("button", { name: "Record decisions" }).click();
  await expect(
    page.getByText("ready_for_candidates", { exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Generate candidates" }).click();
  await expect(page).toHaveURL(/\/operations\//);
  await shoot(page, "06-operation");
  await expect(page.getByText("succeeded", { exact: true })).toBeVisible({
    timeout: 90_000,
  });
  await page.getByRole("link", { name: /Back to case/ }).click();

  await page.getByRole("link", { name: "Open the full comparison" }).click();
  await expect(
    page.getByRole("heading", { name: /4 candidate architectures/ }),
  ).toBeVisible();
  await shoot(page, "07-candidates");

  await page
    .getByRole("button", { name: "Evaluate against the contract" })
    .nth(2)
    .click();
  await expect(page.getByText("succeeded", { exact: true })).toBeVisible({
    timeout: 90_000,
  });
  await page.getByRole("link", { name: /Back to case/ }).click();
  await page.getByRole("link", { name: "Open the full comparison" }).click();
  await page
    .getByLabel("Selection rationale for candidate-03")
    .fill("Balanced trade-off between quality, cost, and operability.");
  await page.getByRole("button", { name: "Select candidate-03" }).click();
  await expect(page).toHaveURL(new RegExp(`/cases/${caseId}/decision$`));
  await page
    .getByRole("button", { name: "Create the assurance plan for candidate-03" })
    .click();
  await expect(page.getByRole("heading", { name: "Controls" })).toBeVisible();
  await shoot(page, "08-decision-assurance");

  await page.getByRole("link", { name: "Back to the case" }).click();
  await page.getByRole("link", { name: "Compile the review bundle" }).click();
  await page
    .getByLabel("Target profile (JSON)")
    .fill(JSON.stringify(LOCAL_FIXTURE_TARGET));
  await page.getByRole("button", { name: "Compile the bundle" }).click();
  await expect(page.getByText("succeeded", { exact: true })).toBeVisible({
    timeout: 90_000,
  });
  await page.getByRole("link", { name: /Back to case/ }).click();
  await page.getByRole("link", { name: "Review the compiled bundle" }).click();
  await expect(
    page.getByRole("heading", { name: "Plan, approval, and apply" }),
  ).toBeVisible();
  await shoot(page, "09-bundle");

  await page.getByRole("link", { name: "Back to the case" }).click();
  await expect(page.getByText("bundle_compiled").first()).toBeVisible();
  // Shoot the timeline itself, not the top of the case page: the audit entries are the
  // subject of this figure and they sit below the fold at this viewport.
  // This figure's subject is the audit entries, so wait for them and put them on screen.
  // Two traps: the entries are fetched after the case document resolves, so shooting on
  // `bundle_compiled` alone races the trail into "No audit events are recorded yet"; and
  // scrollIntoViewIfNeeded is a no-op because the heading already sits at the bottom
  // edge, which leaves the entries themselves below the fold.
  const timeline = page.getByRole("heading", { name: "Audit timeline" });
  await expect(page.locator("ol.timeline li").first()).toBeVisible();
  await timeline.evaluate((element) =>
    element.scrollIntoView({ block: "start", behavior: "instant" }),
  );
  await shoot(page, "10-timeline");

  // Chapter 4's model settings figure. Captured with the real capability token so the page
  // shows the family list and the key form rather than the token prompt; no key is stored,
  // so nothing about this capture changes the stack's configuration.
  await page.goto(`/#token=${encodeURIComponent(token)}`);
  await page.goto("/settings/models");
  await expect(
    page.getByRole("heading", { name: "Models", level: 1 }),
  ).toBeVisible();
  await expect(page.getByLabel("Hugging Face token")).toBeVisible();
  await shoot(page, "11-models");
});
