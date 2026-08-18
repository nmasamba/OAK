// SPDX-License-Identifier: Apache-2.0
import { execSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

import {
  apiPost,
  briefFor,
  referenceAnswers,
  waitForOperation,
} from "./support";

const REPO_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
);

function compose(command: string) {
  execSync(`docker compose ${command}`, { cwd: REPO_ROOT, stdio: "pipe" });
}

test("a stale action is denied and the reviewer recovers to current state", async ({
  page,
  request,
}) => {
  const slug = `web-e2e-denied-${Date.now()}`;
  const caseId = `design-case.${slug}`;

  await apiPost(request, "/v1/design-cases", "create", {
    body: { original_name: `${slug}.yaml`, content: briefFor(slug) },
  });
  await apiPost(request, `/v1/design-cases/${caseId}:interpret`, "interpret", {
    etag: "0.1.0",
  });
  const answers = referenceAnswers();
  await apiPost(request, `/v1/design-cases/${caseId}:confirm`, "confirm", {
    etag: "0.1.1",
    body: {
      answers: {
        answers_version: "0.1.0",
        design_case_id: caseId,
        answers,
      },
    },
  });

  await page.goto(`/cases/${caseId}`);
  await expect(
    page.getByRole("button", { name: "Generate candidates" }),
  ).toBeVisible();

  const generated = await apiPost(
    request,
    `/v1/design-cases/${caseId}:generate-candidates`,
    "generate",
    { etag: "0.1.2" },
  );
  await waitForOperation(request, String(generated["operation_id"]));

  await page.getByRole("button", { name: "Generate candidates" }).click();
  const alert = page.getByRole("alert");
  await expect(
    alert.getByText("This case changed while you were viewing it."),
  ).toBeVisible();
  await expect(alert.getByText("OAK-EXPECTED-VERSION")).toBeVisible();

  await page.getByRole("button", { name: "Reload case" }).click();
  await expect(
    page.getByText("candidates_ready", { exact: true }),
  ).toBeVisible();
});

test("an interrupted operation is cancelled cooperatively and durably", async ({
  page,
  request,
}) => {
  test.skip(
    process.env["OAK_E2E_DOCKER"] !== "1",
    "requires docker compose control over the worker (set OAK_E2E_DOCKER=1)",
  );
  const slug = `web-e2e-interrupt-${Date.now()}`;
  const caseId = `design-case.${slug}`;

  await apiPost(request, "/v1/design-cases", "create", {
    body: { original_name: `${slug}.yaml`, content: briefFor(slug) },
  });
  await apiPost(request, `/v1/design-cases/${caseId}:interpret`, "interpret", {
    etag: "0.1.0",
  });
  const answers = referenceAnswers();
  await apiPost(request, `/v1/design-cases/${caseId}:confirm`, "confirm", {
    etag: "0.1.1",
    body: {
      answers: {
        answers_version: "0.1.0",
        design_case_id: caseId,
        answers,
      },
    },
  });

  compose("stop worker");
  try {
    await page.goto(`/cases/${caseId}`);
    await page.getByRole("button", { name: "Generate candidates" }).click();
    await expect(page).toHaveURL(/\/operations\//);
    await expect(
      page.getByText("Waiting for the worker to finish…"),
    ).toBeVisible();

    await page.getByRole("button", { name: "Cancel operation" }).click();
    await expect(page.getByText(/cancell(ing|ed)/).first()).toBeVisible();
  } finally {
    compose("start worker");
  }

  const operationId = page.url().split("/operations/")[1] ?? "";
  const deadline = Date.now() + 60_000;
  for (;;) {
    const response = await request.get(
      `${process.env["OAK_API_BASE_URL"] ?? "http://127.0.0.1:8080"}/v1/operations/${operationId}`,
    );
    const body = (await response.json()) as { state: string };
    if (body.state === "cancelled") {
      break;
    }
    if (Date.now() > deadline) {
      throw new Error(`operation stayed ${body.state}; expected cancelled`);
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  await page.reload();
  await expect(page.getByText("cancelled", { exact: true })).toBeVisible();
});
