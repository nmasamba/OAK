// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "@playwright/test";

import {
  API_BASE,
  apiPost,
  briefFor,
  compose,
  expectAccessible,
  referenceAnswers,
} from "./support";

function api(command: string): string {
  return compose(`exec -T api ${command}`);
}

// OAK-S14-005: research at the point of design (ADR-0018), on the throwaway stack whose
// API and worker answer from the fixture source (OAK_RESEARCH_FIXTURES), so nothing
// leaves the machine. The reviewer sees what research would send before consenting,
// runs it once with the capability token, reviews the one unvetted item with a recorded
// rationale, generates, and finds the new design shown with its evidence and the plain
// reason it cannot be selected this sprint.
test("a reviewer consents to research, reviews the unvetted harness and compares the new design", async ({
  page,
  request,
}) => {
  test.skip(
    process.env["OAK_E2E_DOCKER"] !== "1",
    "requires the compose stack (set OAK_E2E_DOCKER=1)",
  );
  test.setTimeout(240_000);
  const slug = `web-e2e-research-${Date.now()}`;
  const caseId = `design-case.${slug}`;

  await test.step("drive a case to ready_for_candidates", async () => {
    await apiPost(request, "/v1/design-cases", "create", {
      body: { original_name: `${slug}.yaml`, content: briefFor(slug) },
    });
    await apiPost(
      request,
      `/v1/design-cases/${caseId}:interpret`,
      "interpret",
      { etag: "0.1.0" },
    );
    await apiPost(request, `/v1/design-cases/${caseId}:confirm`, "confirm", {
      etag: "0.1.1",
      body: {
        answers: {
          answers_version: "0.1.0",
          design_case_id: caseId,
          answers: referenceAnswers(),
        },
      },
    });
  });

  await test.step("the plan is a read: the hosts and terms, with their digest", async () => {
    const response = await request.get(
      `${API_BASE}/v1/design-cases/${caseId}/research-plan`,
    );
    expect(response.ok(), `research-plan responded ${response.status()}`).toBe(
      true,
    );
    const plan = (await response.json()) as {
      source_mode: string;
      hosts: string[];
      terms_digest: string;
      allowed: boolean;
    };
    expect(plan.source_mode).toBe("fixture");
    expect(plan.hosts).toEqual([]);
    expect(plan.terms_digest).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect(plan.allowed).toBe(true);
  });

  await test.step("the case page asks before anything is sent", async () => {
    const token = api("oak models token").trim();
    expect(token.length).toBeGreaterThan(15);
    await page.goto(`/#token=${encodeURIComponent(token)}`);
    await page.goto(`/cases/${caseId}`);
    await expect(page.getByText("Look for newer options?")).toBeVisible();
    const consent = page.getByRole("region", {
      name: "What research would send",
    });
    await expect(consent).toContainText("pipeline_tags");
    await expect(consent).toContainText(/sha256:[0-9a-f]{64}/);
    await expect(
      consent.getByText(/No host: the fixture source/),
    ).toBeVisible();
    // Generating is still offered beside research; research is never required.
    await expect(
      page.getByRole("button", { name: "Generate candidates" }),
    ).toBeVisible();
    await expectAccessible(page, "research consent");

    await page.getByRole("button", { name: "Run research" }).click();
    const results = page.getByRole("list", { name: "Research results" });
    await expect(results.getByText("2 found", { exact: true })).toBeVisible({
      timeout: 90_000,
    });
    await expect(results.getByText("1 passed", { exact: true })).toBeVisible();
    await expect(
      results.getByText("1 needs your review", { exact: true }),
    ).toBeVisible();
    // Research runs once: the keycap is gone once the case holds a snapshot.
    await expect(
      page.getByRole("button", { name: "Run research" }),
    ).toHaveCount(0);
    const items = page.getByRole("list", { name: "Researched items" });
    await expect(
      items.getByText("HuggingFaceTB/Fixturelm-4B", { exact: true }),
    ).toBeVisible();
    await expect(
      items.getByText("Passed the gates", { exact: true }),
    ).toBeVisible();
    await expect(
      items.getByText("Needs your review", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("research_completed")).toBeVisible();
    await expectAccessible(page, "research results");
  });

  await test.step("review the unvetted harness: a decision with a rationale", async () => {
    const items = page.getByRole("list", { name: "Researched items" });
    const harness = items.getByRole("listitem", {
      name: "fixture-forge/fixturelm-serve",
    });
    await harness.getByText("Claims", { exact: true }).click();
    // Every claim shows its evidence word.
    await expect(harness.getByText("Published release").first()).toBeVisible();
    await expect(
      harness.getByText("Claimed by release notes").first(),
    ).toBeVisible();
    await expectAccessible(page, "research claims");
    await harness
      .getByLabel("Rationale for fixture-forge/fixturelm-serve")
      .fill(
        "Read the release notes and the licence by hand; accepted for comparison only.",
      );
    await harness
      .getByRole("button", { name: "Accept for comparison" })
      .click();
    await expect(harness.getByText("Accepted by you")).toBeVisible();
    const results = page.getByRole("list", { name: "Research results" });
    await expect(results.getByText("2 passed", { exact: true })).toBeVisible();
    await expect(
      results.getByText("0 need your review", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("research_item_reviewed")).toBeVisible();
    await expect(
      harness.getByRole("button", { name: "Accept for comparison" }),
    ).toHaveCount(0);
    await expectAccessible(page, "research reviewed");
  });

  await test.step("generate, then see the new design and why it cannot be selected", async () => {
    await page.getByRole("button", { name: "Generate candidates" }).click();
    await expect(page).toHaveURL(/\/operations\//);
    await expect(page.getByText("succeeded", { exact: true })).toBeVisible({
      timeout: 90_000,
    });
    await page.getByRole("link", { name: /Back to case/ }).click();
    await page.getByRole("link", { name: "Open the full comparison" }).click();
    await expect(
      page.getByRole("heading", { name: /6 candidate architectures/ }),
    ).toBeVisible();
    // The curated label is unchanged, and the researched one carries the suffix and chip.
    await expect(
      page.getByText("Balanced", { exact: true }).first(),
    ).toBeVisible();
    await expect(
      page.getByText("Balanced, new", { exact: true }).first(),
    ).toBeVisible();
    await expect(page.getByText("New", { exact: true }).first()).toBeVisible();
    await expect(
      page.getByText(/never selectable this sprint/).first(),
    ).toBeVisible();
    await expect(
      page.getByRole("list", { name: "Evidence behind candidate-05" }),
    ).toContainText("Published by source");
    await expect(
      page.getByRole("button", { name: /Select candidate-05/ }),
    ).toHaveCount(0);
    await expectAccessible(page, "candidates with a researched design");

    await page.getByRole("button", { name: "Table" }).click();
    const table = page.getByRole("region", {
      name: "Candidate comparison table",
    });
    await expect(
      table.getByRole("columnheader", { name: "Source" }),
    ).toBeVisible();
    await expect(
      table.getByRole("columnheader", { name: "Release date" }),
    ).toBeVisible();
    await expect(
      table.getByText("HuggingFaceTB/Fixturelm-4B").first(),
    ).toBeVisible();
    await expect(table.getByText("Curated catalogue").first()).toBeVisible();
    await expectAccessible(page, "candidates table with a researched design");
  });

  await test.step("the sheet offers the research snapshot", async () => {
    await page.getByRole("button", { name: "Take it" }).click();
    const sheet = page.getByRole("dialog");
    await expect(sheet.getByRole("button", { name: "Research" })).toBeVisible();
    await expectAccessible(page, "downloads sheet with research");
    await page.keyboard.press("Escape");
    await expect(sheet).toHaveCount(0);
  });
});
