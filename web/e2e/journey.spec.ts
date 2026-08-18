// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "@playwright/test";

import { LOCAL_FIXTURE_TARGET, briefFor, expectAccessible } from "./support";

test("a reviewer completes the reference journey from brief to compiled bundle", async ({
  page,
}) => {
  const slug = `web-e2e-${Date.now()}`;
  const caseId = `design-case.${slug}`;

  await test.step("create the case from the brief", async () => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Design cases" }),
    ).toBeVisible();
    await expectAccessible(page, "case list");
    await page.getByLabel("Brief file name").fill(`${slug}.yaml`);
    await page.getByLabel("Brief content").fill(briefFor(slug));
    await page.getByRole("button", { name: "Create case" }).click();
    await expect(page).toHaveURL(new RegExp(`/cases/${caseId}$`));
    await expect(page.getByText("draft", { exact: true })).toBeVisible();
    await expectAccessible(page, "case detail");
  });

  await test.step("interpret the brief", async () => {
    await page.getByRole("button", { name: "Interpret brief" }).click();
    await expect(
      page.getByText("needs_confirmation", { exact: true }),
    ).toBeVisible();
  });

  await test.step("review facts, inferences, defaults, and unknowns", async () => {
    await page
      .getByRole("link", { name: "reviewing the interpreted claims" })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "Interpreted claims and their origin",
      }),
    ).toBeVisible();
    await expect(page.getByText("Fact from brief").first()).toBeVisible();
    await expect(page.getByText("Inference").first()).toBeVisible();
    await expect(page.getByText("Domain default").first()).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Unknowns and open questions" }),
    ).toBeVisible();
    await expectAccessible(page, "brief review");
    await page.goBack();
  });

  await test.step("answer all five ranked questions", async () => {
    await page
      .getByRole("link", { name: /Answer the 5 ranked questions/ })
      .click();
    await expect(
      page.getByRole("heading", { name: /5 ranked questions block/ }),
    ).toBeVisible();
    await expectAccessible(page, "confirmation");
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
        .fill(
          "Verified against the public reference fixture for this journey.",
        );
    }
    await page.getByRole("button", { name: "Record decisions" }).click();
    await expect(
      page.getByText("ready_for_candidates", { exact: true }),
    ).toBeVisible();
  });

  await test.step("generate candidates through a durable operation", async () => {
    await page.getByRole("button", { name: "Generate candidates" }).click();
    await expect(page).toHaveURL(/\/operations\//);
    await expect(page.getByText("succeeded", { exact: true })).toBeVisible({
      timeout: 90_000,
    });
    await expectAccessible(page, "operation status");
    await page.getByRole("link", { name: /Back to case/ }).click();
  });

  await test.step("compare candidates including the infeasible variant", async () => {
    await page.getByRole("link", { name: "Open the full comparison" }).click();
    await expect(
      page.getByRole("heading", { name: /4 candidate architectures/ }),
    ).toBeVisible();
    await expect(page.getByText("simpler_baseline").first()).toBeVisible();
    await expect(page.getByText("infeasible", { exact: true })).toBeVisible();
    await expect(page.getByText(/constraint\.hardware/).first()).toBeVisible();
    await expectAccessible(page, "candidate comparison");
  });

  await test.step("evaluate candidate-03", async () => {
    await page
      .getByRole("button", { name: "Evaluate against the contract" })
      .nth(2)
      .click();
    await expect(page).toHaveURL(/\/operations\//);
    await expect(page.getByText("succeeded", { exact: true })).toBeVisible({
      timeout: 90_000,
    });
    await page.getByRole("link", { name: /Back to case/ }).click();
    await page.getByRole("link", { name: "Open the full comparison" }).click();
  });

  await test.step("select candidate-03 with a rationale", async () => {
    await page
      .getByLabel("Selection rationale for candidate-03")
      .fill("Balanced trade-off between quality, cost, and operability.");
    await page.getByRole("button", { name: "Select candidate-03" }).click();
    await expect(page).toHaveURL(new RegExp(`/cases/${caseId}/decision$`));
    await expect(
      page.getByText("Selected candidate: candidate-03"),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Evaluation evidence" }),
    ).toBeVisible();
  });

  await test.step("create the assurance plan", async () => {
    await page
      .getByRole("button", {
        name: "Create the assurance plan for candidate-03",
      })
      .click();
    await expect(page.getByRole("heading", { name: "Controls" })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Gate blockers" }),
    ).toBeVisible();
    await expectAccessible(page, "decision and assurance");
  });

  await test.step("compile and review the bundle", async () => {
    await page.getByRole("link", { name: "Back to the case" }).click();
    await page.getByRole("link", { name: "Compile the review bundle" }).click();
    await page
      .getByLabel("Target profile (JSON)")
      .fill(JSON.stringify(LOCAL_FIXTURE_TARGET));
    await page.getByRole("button", { name: "Compile the bundle" }).click();
    await expect(page).toHaveURL(/\/operations\//);
    await expect(page.getByText("succeeded", { exact: true })).toBeVisible({
      timeout: 90_000,
    });
    await page.getByRole("link", { name: /Back to case/ }).click();
    await page
      .getByRole("link", { name: "Review the compiled bundle" })
      .click();
    await expect(
      page.getByRole("heading", { name: "Plan, approval, and apply" }),
    ).toBeVisible();
    await expect(
      page.getByText(
        "unavailable in Community — no runner execution authority",
      ),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Component lock" }),
    ).toBeVisible();
    await expectAccessible(page, "bundle review");
  });

  await test.step("download the canonical export and read the timeline", async () => {
    await page.getByRole("link", { name: "Back to the case" }).click();
    const downloadPromise = page.waitForEvent("download");
    await page
      .getByRole("button", { name: "Download the canonical export" })
      .click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(`${caseId}-export.json`);
    await expect(page.getByText("bundle_compiled").first()).toBeVisible();
    await expect(page.getByText("case_created")).toBeVisible();
    await expect(page.getByText("claims_confirmed")).toBeVisible();
  });

  await test.step("the core flow is keyboard operable", async () => {
    await page.goto("/");
    const focusedId = await page.evaluate(
      () => document.activeElement?.id ?? "",
    );
    expect(focusedId).toBe("page-heading");
    await page.keyboard.press("Tab");
    const focusedTag = await page.evaluate(
      () => document.activeElement?.tagName ?? "",
    );
    expect(["A", "BUTTON", "INPUT", "TEXTAREA"]).toContain(focusedTag);
  });
});
