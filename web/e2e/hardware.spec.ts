// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "@playwright/test";

import {
  API_BASE,
  apiPost,
  briefFor,
  expectAccessible,
  referenceAnswers,
} from "./support";

// What `oak scan --output json` prints under `proposal` on a Linux machine with one NVIDIA
// GPU. The browser never scans: the scan runs where the hardware is and is proposed here.
const SCAN = {
  platform: { operating_system: "linux", architecture: "x86_64" },
  cpu: {
    model: "AMD EPYC 7763 64-Core Processor",
    physical_cores: 8,
    logical_cores: 16,
  },
  memory: { ram_gib: 32, unified: false },
  storage_gib: 500,
  accelerators: [
    {
      vendor: "nvidia",
      model: "NVIDIA GeForce RTX 4090",
      memory_gib: 24,
      unified_memory: false,
      runtime: "cuda",
      driver_version: "550.54.15",
    },
  ],
  prerequisites: [
    { name: "docker", state: "present" },
    { name: "uv", state: "absent" },
  ],
  unknown: [{ field: "accelerators.amd", reason: "rocm-smi is not installed" }],
  tools: [
    { name: "lscpu", status: "ran" },
    { name: "nvidia-smi", status: "ran" },
    { name: "rocm-smi", status: "absent" },
  ],
};

// OAK-V1-039: a scan's proposal is a moment on the case page, and the hardware enters the
// case's intent only when the user confirms it there.
test("a scanned machine is shown as a proposal and confirmed on the case page", async ({
  page,
  request,
}) => {
  test.skip(
    process.env["OAK_E2E_DOCKER"] !== "1",
    "requires the compose stack (set OAK_E2E_DOCKER=1)",
  );
  test.setTimeout(120_000);
  const slug = `web-e2e-hardware-${Date.now()}`;
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

  await test.step("before a scan, the page says where to run one", async () => {
    await page.goto(`/cases/${encodeURIComponent(caseId)}`);
    await expect(page.getByText("Scan it where it runs")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Copy the scan command" }),
    ).toBeVisible();
  });

  await test.step("a proposed scan is shown, and nothing is confirmed yet", async () => {
    await apiPost(
      request,
      `/v1/design-cases/${caseId}:propose-hardware`,
      "propose",
      { etag: "0.1.2", body: { scan: SCAN } },
    );
    await page.reload();
    await expect(page.getByText("proposed", { exact: true })).toBeVisible();
    await expect(
      page.getByText("GPU: NVIDIA GeForce RTX 4090 (CUDA), 24 GiB"),
    ).toBeVisible();
    await expect(page.getByText("rocm-smi is not installed")).toBeVisible();
    await expectAccessible(page, "the hardware proposal");
  });

  await test.step("confirming puts the hardware in the case", async () => {
    await page.getByRole("button", { name: "Confirm hardware" }).click();
    await expect(page.getByText("confirmed", { exact: true })).toBeVisible();
    const response = await request.get(`${API_BASE}/v1/design-cases/${caseId}`);
    const document = (await response.json()) as {
      intent: { spec: { hardware: Record<string, unknown> } };
    };
    expect(document.intent.spec.hardware["accelerators"]).toEqual([
      "nvidia-cuda",
    ]);
    expect(document.intent.spec.hardware["vram_gib"]).toBe(24);
  });
});
