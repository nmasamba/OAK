// SPDX-License-Identifier: Apache-2.0
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

import {
  API_BASE,
  apiPost,
  briefFor,
  expectAccessible,
  referenceAnswers,
  waitForOperation,
} from "./support";

// OAK-S13-005: the architecture report is recorded by one deliberate step, read one
// slide at a time from the keyboard, taken away as a PDF and as its document, each
// matched to the digest the server names, and flagged when the case moves on.
test("a reviewer records the report, reads every slide and takes it away", async ({
  page,
  request,
}) => {
  test.setTimeout(180_000);
  const slug = `web-e2e-report-${Date.now()}`;
  const caseId = `design-case.${slug}`;

  await test.step("drive a case to a selected design", async () => {
    await apiPost(request, "/v1/design-cases", "create", {
      body: { original_name: `${slug}.yaml`, content: briefFor(slug) },
    });
    await apiPost(
      request,
      `/v1/design-cases/${caseId}:interpret`,
      "interpret",
      {
        etag: "0.1.0",
      },
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
    const generated = await apiPost(
      request,
      `/v1/design-cases/${caseId}:generate-candidates`,
      "generate",
      { etag: "0.1.2" },
    );
    await waitForOperation(request, String(generated["operation_id"]));
    const evaluated = await apiPost(
      request,
      "/v1/candidates/candidate-03:evaluate",
      "evaluate",
      { etag: "0.1.3", body: { case_id: caseId } },
    );
    await waitForOperation(request, String(evaluated["operation_id"]));
    await apiPost(
      request,
      `/v1/design-cases/${caseId}:select-candidate`,
      "select",
      {
        etag: "0.1.4",
        body: {
          candidate_id: "candidate-03",
          rationale:
            "Balanced trade-off between quality, cost, and operability.",
        },
      },
    );
  });

  await test.step("open the Report screen from the case rail and record", async () => {
    await page.goto(`/cases/${caseId}`);
    await page
      .getByRole("complementary", { name: "Case at a glance" })
      .getByRole("link", { name: "Report" })
      .click();
    await expect(page).toHaveURL(new RegExp(`/cases/${caseId}/report$`));
    await expect(page.getByText("No report is recorded yet.")).toBeVisible();
    const notes = page.getByRole("group", {
      name: "Should a model add notes to the slides?",
    });
    await expect(notes.getByRole("radio")).toHaveCount(3);
    await expect(
      notes.getByRole("radio", { name: "Deterministic" }),
    ).toBeChecked();
    await expectAccessible(page, "report screen before recording");
    await page.getByRole("button", { name: "Record report" }).click();
    await expect(
      page.getByText("Slide 1 of 20", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", {
        level: 2,
        name: /build the Balanced design$/,
      }),
    ).toBeVisible();
    await expectAccessible(page, "report, first slide");
  });

  await test.step("page through every slide from the keyboard", async () => {
    const slide = page.getByRole("region", {
      name: /build the Balanced design$/,
    });
    await slide.focus();
    for (let number = 2; number <= 20; number += 1) {
      await page.keyboard.press("ArrowRight");
      await expect(
        page.getByText(`Slide ${number} of 20`, { exact: true }),
      ).toBeVisible();
    }
    await expect(
      page.getByRole("heading", {
        level: 2,
        name: "Every input record, by digest",
      }),
    ).toBeVisible();
    await page.keyboard.press("ArrowRight");
    await expect(
      page.getByText("Slide 20 of 20", { exact: true }),
    ).toBeVisible();
    await page.keyboard.press("Home");
    await expect(
      page.getByText("Slide 1 of 20", { exact: true }),
    ).toBeVisible();
  });

  await test.step("a picture sits beside the table that lists the same", async () => {
    await page
      .getByRole("navigation", { name: "Report contents" })
      .getByRole("button", { name: /^9 / })
      .click();
    await expect(
      page.getByText("Slide 9 of 20", { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("img", { name: /feeds/ })).toBeVisible();
    await expect(page.getByRole("table", { name: "Nodes" })).toBeVisible();
    await expect(page.getByRole("table", { name: "Edges" })).toBeVisible();
    await expectAccessible(page, "report, architecture slide");
  });

  await test.step("take the PDF and the document, each by digest", async () => {
    const response = await request.get(`${API_BASE}/v1/design-cases/${caseId}`);
    const entry = (
      (await response.json()) as {
        case: {
          extensions: Record<string, Record<string, Record<string, string>>>;
        };
      }
    ).case.extensions["oak.community/report"];
    expect(entry).toBeDefined();
    const files = page.getByRole("list", { name: "Report files" });
    for (const [word, field, extension] of [
      ["PDF", "pdf_ref", "pdf"],
      ["JSON", "document_ref", "json"],
    ] as const) {
      const reference = entry![field]!;
      const direct = await request.get(
        `${API_BASE}/v1/design-cases/${caseId}/artifacts/${reference["id"]}`,
        {
          params: {
            version: reference["version"]!,
            digest: reference["digest"]!,
          },
        },
      );
      const named = direct.headers()["x-oak-artifact-digest"];
      expect(named).toBe(reference["digest"]);
      const downloadPromise = page.waitForEvent("download");
      await files.getByRole("button", { name: new RegExp(`^${word}`) }).click();
      const download = await downloadPromise;
      expect(download.suggestedFilename()).toBe(
        `report.${slug}.from-0.1.5.${extension}`,
      );
      const bytes = readFileSync(await download.path());
      expect(`sha256:${createHash("sha256").update(bytes).digest("hex")}`).toBe(
        named,
      );
      await expect(
        files.getByRole("button", { name: new RegExp(`^${word}`) }),
      ).toContainText("digest matches");
    }
  });

  await test.step("the Take it sheet offers the report", async () => {
    await page.getByRole("button", { name: "Take it" }).click();
    const sheet = page.getByRole("dialog", { name: "Take it" });
    await expect(sheet.getByRole("button", { name: /^Report/ })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(sheet).toHaveCount(0);
  });

  await test.step("when the case moves on, the screen says so", async () => {
    await apiPost(
      request,
      `/v1/design-cases/${caseId}:create-assurance-plan`,
      "assure",
      { etag: "0.1.6", body: { candidate_id: "candidate-03" } },
    );
    await page.reload();
    await expect(
      page.getByText(/The case has moved on since this report/),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Record again" }),
    ).toBeVisible();
    await expectAccessible(page, "report screen when the case has moved on");
  });
});
