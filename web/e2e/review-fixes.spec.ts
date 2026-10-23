// SPDX-License-Identifier: Apache-2.0
import { expect, test, type APIRequestContext } from "@playwright/test";

import {
  API_BASE,
  LOCAL_FIXTURE_TARGET,
  apiPost,
  briefFor,
  referenceAnswers,
  waitForOperation,
} from "./support";

// The web workspace findings of the 1.0 readiness review (OAK-V1-005, F3-*), each pinned
// where a reader meets it. Every test builds its own case over REST.

async function readyCase(request: APIRequestContext, prefix: string) {
  const slug = `web-e2e-${prefix}-${Date.now()}`;
  const caseId = `design-case.${slug}`;
  await apiPost(request, "/v1/design-cases", "create", {
    body: { original_name: `${slug}.yaml`, content: briefFor(slug) },
  });
  await apiPost(request, `/v1/design-cases/${caseId}:interpret`, "interpret", {
    etag: "0.1.0",
  });
  return { slug, caseId };
}

async function confirmAll(request: APIRequestContext, caseId: string) {
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
}

async function candidatesReady(request: APIRequestContext, caseId: string) {
  await confirmAll(request, caseId);
  const generated = await apiPost(
    request,
    `/v1/design-cases/${caseId}:generate-candidates`,
    "generate",
    { etag: "0.1.2" },
  );
  await waitForOperation(request, String(generated["operation_id"]));
}

async function evaluate(
  request: APIRequestContext,
  caseId: string,
  candidateId: string,
  version: string,
) {
  const operation = await apiPost(
    request,
    `/v1/candidates/${candidateId}:evaluate`,
    `evaluate-${candidateId}`,
    { etag: version, body: { case_id: caseId } },
  );
  await waitForOperation(request, String(operation["operation_id"]));
}

test("Decision shows the selected design's own evaluation and names it (F3-1)", async ({
  page,
  request,
}) => {
  const { caseId } = await readyCase(request, "evalorder");
  await candidatesReady(request, caseId);
  await evaluate(request, caseId, "candidate-00", "0.1.3");
  await evaluate(request, caseId, "candidate-03", "0.1.4");
  await apiPost(
    request,
    `/v1/design-cases/${caseId}:select-candidate`,
    "select",
    {
      etag: "0.1.5",
      body: {
        candidate_id: "candidate-00",
        rationale: "The baseline suffices.",
      },
    },
  );

  await page.goto(`/cases/${caseId}/decision`);
  const evidence = page.getByRole("region", { name: "Evaluation evidence" });
  await expect(
    evidence.getByText("candidate-00", { exact: true }),
  ).toBeVisible();
  await expect(evidence.getByRole("table")).toContainText("180");
  await expect(page.getByText("Raw decision document")).toHaveCount(0);
});

test("a refused submission keeps every drafted answer (F3-2) and Done keeps focus (F3-8)", async ({
  page,
  request,
}) => {
  const { caseId } = await readyCase(request, "drafts");
  await page.goto(`/cases/${caseId}/confirm`);

  const hardware = page.locator("#question-question\\.model-hardware");
  await hardware.getByRole("radio", { name: /Confirm/ }).check();
  await page
    .locator("#rationale-question\\.model-hardware")
    .fill("Declared capacity.");
  await hardware.getByRole("button", { name: "Done" }).click();
  await expect(page.locator("#edit-question\\.model-hardware")).toBeFocused();

  const production = page.locator("#question-question\\.production-use");
  await production.getByRole("radio", { name: /Confirm/ }).check();
  await page
    .locator("#rationale-question\\.production-use")
    .fill("Fixture only.");

  // Someone else answers a third question meanwhile.
  const third = referenceAnswers().find(
    (answer) => answer["question_id"] === "question.action-autonomy",
  );
  await apiPost(
    request,
    `/v1/design-cases/${caseId}:confirm`,
    "confirm-elsewhere",
    {
      etag: "0.1.1",
      body: {
        answers: {
          answers_version: "0.1.0",
          design_case_id: caseId,
          answers: [third],
        },
      },
    },
  );

  await page.getByRole("button", { name: "Record decisions" }).click();
  await expect(
    page.getByText("This case changed while you were viewing it."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Reload case" }).click();
  await expect(
    page.locator("#rationale-question\\.production-use"),
  ).toHaveValue("Fixture only.");
  await expect(
    production.getByRole("radio", { name: /Confirm/ }),
  ).toBeChecked();
});

test("an unset claim offers only Correct, and nothing sends '(not set)' (F3-10)", async ({
  page,
  request,
}) => {
  const { caseId } = await readyCase(request, "unset");
  const bodies: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes(":confirm")) {
      bodies.push(request.postData() ?? "");
    }
  });
  await page.goto(`/cases/${caseId}/confirm`);
  const volume = page.locator("#question-question\\.data-volume");
  await volume.scrollIntoViewIfNeeded();
  await expect(volume.getByRole("radio", { name: /Confirm/ })).toBeDisabled();
  await expect(
    volume.getByRole("radio", { name: /Accept the risk/ }),
  ).toBeDisabled();
  await expect(volume.getByText("This value is not set yet")).toBeVisible();
  expect(bodies.join("")).not.toContain("(not set)");
});

test("a failed operation shows its own code and message (F3-3)", async ({
  page,
  request,
}) => {
  const { caseId } = await readyCase(request, "tenant");
  await candidatesReady(request, caseId);
  await evaluate(request, caseId, "candidate-03", "0.1.3");
  await apiPost(
    request,
    `/v1/design-cases/${caseId}:select-candidate`,
    "select",
    {
      etag: "0.1.4",
      body: { candidate_id: "candidate-03", rationale: "Balanced." },
    },
  );
  await apiPost(
    request,
    `/v1/design-cases/${caseId}:create-assurance-plan`,
    "assure",
    {
      etag: "0.1.5",
      body: { candidate_id: "candidate-03" },
    },
  );
  const compiled = await apiPost(
    request,
    `/v1/design-cases/${caseId}:compile`,
    "compile",
    {
      etag: "0.1.6",
      body: {
        candidate_id: "candidate-03",
        target: { ...LOCAL_FIXTURE_TARGET, tenant_id: "acme" },
      },
    },
  );

  await page.goto(`/operations/${String(compiled["operation_id"])}`);
  const alert = page.getByRole("alert");
  await expect(alert.getByText("OAK-TARGET-TENANT")).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByText("unknown code")).toHaveCount(0);
  await expect(page.getByText("Next attempt")).toHaveCount(0);
});

test("a case that already exists is named, not a stale view (F3-6)", async ({
  page,
  request,
}) => {
  const slug = `web-e2e-samename-${Date.now()}`;
  await apiPost(request, "/v1/design-cases", "create", {
    body: { original_name: `${slug}.yaml`, content: briefFor(slug) },
  });
  const again = await request.post(`${API_BASE}/v1/design-cases`, {
    headers: { "Idempotency-Key": `e2e-samename-${Date.now()}-again` },
    data: {
      original_name: `${slug}.yaml`,
      content: briefFor(slug).replace("title:", "title: Edited"),
    },
  });
  expect(again.status()).toBe(409);
  expect(((await again.json()) as { code: string }).code).toBe(
    "OAK-CASE-EXISTS",
  );

  await page.goto("/");
  await expect(page.locator("#page-heading")).toBeFocused();
});

test("the research card's Settings link reaches the Models screen (F3-5)", async ({
  page,
  request,
}) => {
  const { caseId } = await readyCase(request, "settings");
  await confirmAll(request, caseId);
  await page.goto(`/cases/${caseId}`);
  await expect(page.locator("#page-heading")).toBeFocused();
  const link = page.getByRole("link", { name: "paste it in Settings" });
  if ((await link.count()) > 0) {
    await link.click();
    await expect(
      page.getByRole("heading", { level: 1, name: "Models" }),
    ).toBeVisible();
  }
});

test("a refused selection is said in its own card, and its rationale is focused (F3-12)", async ({
  page,
  request,
}) => {
  const { caseId } = await readyCase(request, "inview");
  await candidatesReady(request, caseId);
  await evaluate(request, caseId, "candidate-00", "0.1.3");
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`/cases/${caseId}/candidates`);
  await page.getByRole("button", { name: "Select candidate-00" }).click();
  const message = page.getByText("candidate-00 needs a selection rationale.");
  await expect(message).toBeInViewport();
  await expect(page.locator("#rationale-candidate-00")).toBeFocused();
  await expect(page.getByText("Raw candidate document")).toHaveCount(0);
});
