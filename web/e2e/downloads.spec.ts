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

// OAK-S12-005: a download is the stored bytes, checked in the browser against the digest
// the server names, and saved only when they match. The file that lands on disk hashes
// to that digest, and the page says so beside the file.
test("a downloaded candidate's bytes hash to the digest the server named", async ({
  page,
  request,
}) => {
  const slug = `web-e2e-download-${Date.now()}`;
  const caseId = `design-case.${slug}`;

  await apiPost(request, "/v1/design-cases", "create", {
    body: { original_name: `${slug}.yaml`, content: briefFor(slug) },
  });
  await apiPost(request, `/v1/design-cases/${caseId}:interpret`, "interpret", {
    etag: "0.1.0",
  });
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

  // The digest the server names for candidate-03, read directly.
  const listed = await request.get(
    `${API_BASE}/v1/design-cases/${caseId}/artifacts?limit=100`,
  );
  const entries = (await listed.json()) as {
    items: { id: string; version: string; digest: string }[];
  };
  const entry = entries.items.find((item) => item.id === "candidate-03");
  expect(entry).toBeDefined();
  const direct = await request.get(
    `${API_BASE}/v1/design-cases/${caseId}/artifacts/${entry!.id}`,
    { params: { version: entry!.version, digest: entry!.digest } },
  );
  const named = direct.headers()["x-oak-artifact-digest"];
  expect(named).toBe(entry!.digest);

  await page.goto(`/cases/${caseId}`);
  await page.getByRole("button", { name: "Take it" }).click();
  const sheet = page.getByRole("dialog", { name: "Take it" });
  await expect(sheet).toBeVisible();
  await expectAccessible(page, "downloads sheet");

  const downloadPromise = page.waitForEvent("download");
  await sheet.getByRole("button", { name: /candidate-03/ }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("candidate-03.json");
  const path = await download.path();
  const bytes = readFileSync(path);
  const digest = `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
  expect(digest).toBe(named);
  await expect(
    sheet.getByRole("button", { name: /candidate-03/ }),
  ).toContainText("digest matches");

  // Escape closes the sheet and returns focus to the control that opened it.
  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Take it" })).toBeFocused();
});
