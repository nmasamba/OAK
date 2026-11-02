// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "@playwright/test";

import {
  apiPost,
  briefFor,
  expectAccessible,
  referenceAnswers,
  waitForOperation,
} from "./support";

const STAND_IN = {
  role: "harness",
  source: "oak-stand-in:http-server",
  sha256:
    "sha256:71ec5f57b36e7f6aa9f963197845708cda430b7f028ea9bbf063fea80cf4351a",
  size_bytes: 1756,
  format: "file",
} as const;

// `examples/targets/local-native-stand-in.yaml` as the JSON a compile takes (ADR-0019).
const NATIVE_TARGET = {
  target_profile_version: "0.2.0",
  id: "target.local-native-stand-in",
  status: "non-production-local",
  environment: "validation",
  tenant_id: "local",
  platform: {
    operating_system: "linux",
    architecture: "x86_64",
    accelerators: [],
    drivers: [],
    container_runtime: "none (native installation)",
  },
  capacity: { ram_gib: 32, storage_gib: 100 },
  network: { mode: "isolated-no-egress", inbound_control_plane: false },
  permissions: {
    mutation_allowed: true,
    allowed_operations: [
      "inventory",
      "validate",
      "render",
      "plan",
      "verify",
      "apply",
      "rollback",
      "destroy",
    ],
  },
  execution: {
    mutation_acknowledgement: "native-non-production-user-consented",
    native_components: [
      "component.fixture-lexical-search",
      "component.fixture-local-model",
      "component.fixture-high-assurance-model",
    ].map((manifestId, index) => ({
      manifest_id: manifestId,
      harness_kind: "oak_stand_in",
      artifacts: [STAND_IN],
      listen_port: 18431 + index,
      health_probe: { path: "/health" },
    })),
  },
  secrets: { allowed_references: [] },
  notes: ["Synthetic non-production target for a native installation."],
};

// OAK-V1-042: a native plan's bundle page shows the third approval, the consent text the
// user reads before giving it, and the steps with the plan's consent digest. The web
// records no consent: that happens only in the terminal.
test("a native plan shows its consent text and the steps that give it", async ({
  page,
  request,
}) => {
  test.setTimeout(180_000);
  const slug = `web-e2e-native-${Date.now()}`;
  const caseId = `design-case.${slug}`;

  await test.step("drive a case to a plan compiled for a native target", async () => {
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
        body: { candidate_id: "candidate-03", rationale: "Balanced." },
      },
    );
    await apiPost(
      request,
      `/v1/design-cases/${caseId}:create-assurance-plan`,
      "assure",
      { etag: "0.1.5", body: { candidate_id: "candidate-03" } },
    );
    const compiled = await apiPost(
      request,
      `/v1/design-cases/${caseId}:compile`,
      "compile",
      {
        etag: "0.1.6",
        body: { candidate_id: "candidate-03", target: NATIVE_TARGET },
      },
    );
    await waitForOperation(request, String(compiled["operation_id"]));
  });

  await test.step("the bundle page names the consent and shows its text", async () => {
    await page.goto(`/cases/${caseId}/bundle`);
    const needs = page.getByRole("list", { name: "Install needs" });
    await expect(needs.getByRole("listitem")).toHaveCount(4);
    await expect(needs.getByText("consent · absent")).toBeVisible();

    await page
      .getByText("What a native install relaxes", { exact: true })
      .click();
    await expect(
      page
        .getByRole("list", { name: "What a native install relaxes" })
        .getByRole("listitem"),
    ).toHaveCount(6);
    await expect(
      page.getByRole("list", { name: "What stays" }).getByRole("listitem"),
    ).toHaveCount(5);
    const digest = (
      await page.locator(".dock-consent-digest code").textContent()
    )?.trim();
    expect(digest).toMatch(/^sha256:[a-f0-9]{64}$/);
    await expect(
      page.getByText(`oak approve native_consent --consent ${digest}`),
    ).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
    await expectAccessible(page, "bundle page for a native plan");
  });
});
