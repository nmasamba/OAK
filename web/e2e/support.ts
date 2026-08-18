// SPDX-License-Identifier: Apache-2.0
import AxeBuilder from "@axe-core/playwright";
import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const API_BASE =
  process.env["OAK_API_BASE_URL"] ?? "http://127.0.0.1:8080";

export const REFERENCE_BRIEF = `# SPDX-License-Identifier: Apache-2.0
brief_version: 0.1.0
id: brief.__SLUG__
status: non-production-fixture
title: Browser end-to-end reference case
purpose:
  problem: Help a small internal engineering team locate and cite answers from a bounded collection of public technical manuals.
  desired_outcomes:
    - Answers cite the exact source passages used.
    - Unsupported questions abstain or refer the user to manual review.
  baseline: Deterministic lexical search with cited passages and no generative model.
stakeholders:
  end_users: [internal engineering users]
  operators: [community-local operator]
  affected_non_users: []
decision:
  actions: [return cited passages, draft a cited answer, abstain]
  autonomy: recommend_only
  reversibility: reversible
data:
  sources: [public technical manuals]
  classifications: [public]
  production_data_permitted: false
quality:
  priorities:
    - citation correctness
    - supported-answer accuracy
    - calibrated abstention
deployment:
  modes: [local]
  network: isolated-no-egress-after-setup
hardware:
  cpu_architectures: [x86_64]
  ram_gib: 32
  storage_gib: 100
openness:
  software: OSI-approved by default
  models: local optional model or no-model baseline
unknowns:
  - Exact document count and update cadence for a real deployment.
  - Approved model licence and hardware if the generated-answer variant is selected.
extensions: {}
`;

export const LOCAL_FIXTURE_TARGET = {
  target_profile_version: "0.1.0",
  id: "target.local-fixture",
  status: "non-production-fixture",
  environment: "validation",
  tenant_id: "local",
  platform: {
    operating_system: "linux",
    architecture: "x86_64",
    accelerators: [],
    drivers: [],
    container_runtime: "rootless-compatible OCI runtime",
  },
  capacity: { ram_gib: 32, storage_gib: 100 },
  network: { mode: "isolated-no-egress", inbound_control_plane: false },
  permissions: {
    mutation_allowed: false,
    allowed_operations: ["inventory", "validate", "render", "plan", "verify"],
  },
  secrets: { allowed_references: [] },
  notes: ["Synthetic target for compiler and dry-run tests only."],
} as const;

export function briefFor(slug: string): string {
  return REFERENCE_BRIEF.replace("__SLUG__", slug);
}

export function referenceAnswers(): readonly Record<string, unknown>[] {
  return [
    {
      question_id: "question.model-hardware",
      decision: "confirm",
      value: { cpu_architectures: ["x86_64"], ram_gib: 32, storage_gib: 100 },
      rationale: "The synthetic local target has the declared capacity.",
    },
    {
      question_id: "question.production-use",
      decision: "confirm",
      value: false,
      rationale: "This fixture validates the compiler and interfaces only.",
    },
    {
      question_id: "question.action-autonomy",
      decision: "confirm",
      value: "recommend_only",
      rationale: "The fixture returns information and takes no actions.",
    },
    {
      question_id: "question.data-classification",
      decision: "confirm",
      value: "public",
      rationale: "The reference corpus is public technical manuals.",
    },
    {
      question_id: "question.data-volume",
      decision: "correct",
      value: "Synthetic fixture of 1000 public documents refreshed daily.",
      rationale: "This bounded volume suffices for deterministic evaluation.",
    },
  ];
}

export async function expectAccessible(page: Page, screen: string) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(
    results.violations,
    `accessibility violations on ${screen}: ${JSON.stringify(
      results.violations.map((violation) => ({
        id: violation.id,
        impact: violation.impact,
        nodes: violation.nodes.map((node) => node.target),
      })),
      null,
      1,
    )}`,
  ).toEqual([]);
}

let sequence = 0;

export function idempotencyKey(step: string): string {
  sequence += 1;
  return `e2e-${step}-${Date.now()}-${sequence}`;
}

export async function apiPost(
  request: APIRequestContext,
  path: string,
  step: string,
  options: {
    readonly etag?: string;
    readonly body?: unknown;
  } = {},
) {
  const headers: Record<string, string> = {
    "Idempotency-Key": idempotencyKey(step),
  };
  if (options.etag !== undefined) {
    headers["If-Match"] = `"${options.etag}"`;
  }
  const response = await request.post(`${API_BASE}${path}`, {
    headers,
    data: options.body ?? {},
  });
  expect(response.ok(), `${path} responded ${response.status()}`).toBe(true);
  return response.json() as Promise<Record<string, unknown>>;
}

export async function waitForOperation(
  request: APIRequestContext,
  operationId: string,
) {
  const deadline = Date.now() + 90_000;
  for (;;) {
    const response = await request.get(
      `${API_BASE}/v1/operations/${operationId}`,
    );
    const body = (await response.json()) as { state: string };
    if (body.state === "succeeded") {
      return;
    }
    if (["failed", "cancelled"].includes(body.state)) {
      throw new Error(`operation ${operationId} ended ${body.state}`);
    }
    if (Date.now() > deadline) {
      throw new Error(`operation ${operationId} timed out`);
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}
