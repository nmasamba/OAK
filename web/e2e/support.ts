// SPDX-License-Identifier: Apache-2.0
import { execSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import AxeBuilder from "@axe-core/playwright";
import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

export const API_BASE =
  process.env["OAK_API_BASE_URL"] ?? "http://127.0.0.1:8080";

const REPO_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
);

// Both services listen on 8080 inside their containers; compose.yaml publishes them.
const CONTAINER_PORT = "8080";

export type ComposeTarget = {
  readonly env: Readonly<Record<string, string | undefined>>;
  readonly webOrigin: string;
  readonly apiOrigin: string;
  // What `docker compose port <service> 8080` prints (":0" when the port is not published);
  // throws when Compose fails, for example when the service is not running.
  readonly publishedPort: (service: "web" | "api") => string;
};

type Address = { readonly host: string; readonly port: string };

const IPV4_LOOPBACK = /^127(\.\d{1,3}){3}$/;

// A published binding reaches an origin only on the origin's own address or on the wildcard
// of its address family: 127.0.0.1:N and 127.0.0.2:N, or 127.0.0.1:N and [::1]:N, can
// belong to two different stacks at once.
function covers(published: string, origin: string): boolean {
  return (
    published === origin ||
    (published === "0.0.0.0" && IPV4_LOOPBACK.test(origin)) ||
    (published === "::" && origin === "::1")
  );
}

function bracketed(host: string): string {
  return host.includes(":") ? `[${host}]` : host;
}

// An absolute http(s) origin's host (without IPv6 brackets) and port, or null.
function originAddress(origin: string): Address | null {
  let url: URL;
  try {
    url = new URL(origin);
  } catch {
    return null;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return null;
  }
  const port =
    url.port !== "" ? url.port : url.protocol === "https:" ? "443" : "80";
  return { host: url.hostname.replace(/^\[|\]$/g, ""), port };
}

// `docker compose port` prints one binding such as 127.0.0.1:28080 or [::]:28080. Output
// without a usable port, such as the ":0" Compose prints for an unpublished one, throws.
function publishedAddress(output: string): Address {
  const line = output.trim().split("\n")[0] ?? "";
  const separator = line.lastIndexOf(":");
  const port = separator < 0 ? "" : line.slice(separator + 1);
  if (!/^[1-9]\d*$/.test(port)) {
    throw new Error(
      `docker compose port printed ${JSON.stringify(line)}, not a published binding`,
    );
  }
  return { host: line.slice(0, separator).replace(/^\[|\]$/g, ""), port };
}

/**
 * Why `docker compose`, run from the repository root, would not reach the stack whose
 * origins the suite drives, or null when it would. Compose takes its project from
 * COMPOSE_PROJECT_NAME, exported or set in a `.env` at the repository root, or else from
 * compose.yaml's `name:`, and never from the origins. Only an exported COMPOSE_PROJECT_NAME
 * counts here. An origin override without one is refused before Docker is asked anything,
 * and so is an origin whose host is not 127.x.x.x or [::1]: Compose controls the Docker
 * engine the shell is configured for, which is assumed to be this machine's, and
 * compose.yaml publishes on 127.0.0.1. Otherwise the project Compose reaches must publish
 * each origin's port on the origin's own address or on that family's wildcard address.
 */
export function composeTargetProblem(target: ComposeTarget): string | null {
  const project = target.env["COMPOSE_PROJECT_NAME"] ?? "";
  const overridden = ["OAK_WEB_BASE_URL", "OAK_API_BASE_URL"].filter(
    (name) => target.env[name] !== undefined,
  );
  const origins = `${target.webOrigin} and ${target.apiOrigin}`;
  if (overridden.length > 0 && project === "") {
    return (
      `${overridden.join(" and ")} ${overridden.length === 1 ? "is" : "are"} set, ` +
      "but COMPOSE_PROJECT_NAME is not exported, so docker compose would act on the " +
      "project it picks by default (compose.yaml's `name:`, unless a `.env` at the " +
      `repository root sets another) rather than on the stack at ${origins}. Export ` +
      "COMPOSE_PROJECT_NAME as the name of the Compose project that serves them."
    );
  }
  const services = [
    { service: "api", origin: target.apiOrigin, variable: "OAK_API_BASE_URL" },
    { service: "web", origin: target.webOrigin, variable: "OAK_WEB_BASE_URL" },
  ] as const;
  const wanted: Address[] = [];
  for (const { service, origin, variable } of services) {
    const address = originAddress(origin);
    if (address === null) {
      return `${variable} is ${JSON.stringify(origin)}, which is not an absolute http(s) URL.`;
    }
    if (address.host === "localhost") {
      return (
        `the suite drives ${service} at ${origin}. Use 127.0.0.1 or [::1] instead of ` +
        "localhost, which can resolve to either, so the check knows which address the " +
        "suite reaches."
      );
    }
    if (!IPV4_LOOPBACK.test(address.host) && address.host !== "::1") {
      return (
        `the suite drives ${service} at ${origin}, which is not 127.x.x.x or [::1], the ` +
        "loopback addresses the check accepts. docker compose is assumed to control a " +
        "Docker engine on this machine, and compose.yaml publishes the stack on 127.0.0.1."
      );
    }
    wanted.push(address);
  }
  const reached =
    project === ""
      ? "the Compose project docker compose picks by default"
      : `the Compose project "${project}"`;
  for (const [index, { service, origin }] of services.entries()) {
    let published: Address;
    try {
      published = publishedAddress(target.publishedPort(service));
    } catch (error) {
      const detail = (error instanceof Error ? error.message : String(error))
        .trim()
        .split("\n")
        .pop();
      return (
        `${reached} publishes no ${service} port (${detail}). Start that stack, or ` +
        "point OAK_WEB_BASE_URL, OAK_API_BASE_URL and COMPOSE_PROJECT_NAME at one that " +
        "is running."
      );
    }
    const want = wanted[index];
    if (
      want === undefined ||
      !covers(published.host, want.host) ||
      published.port !== want.port
    ) {
      return (
        `the suite drives ${service} at ${origin}, but ${reached} publishes its ` +
        `${service} on ${bracketed(published.host)}:${published.port}. Point ` +
        "OAK_WEB_BASE_URL, OAK_API_BASE_URL and COMPOSE_PROJECT_NAME at the same stack."
      );
    }
  }
  return null;
}

/**
 * Why compose() must not run `docker compose <command>` whatever the target, or null. A
 * global flag before the subcommand, such as -p, --file or --env-file, would choose the
 * project after the target check has looked at another one.
 */
export function composeCommandProblem(command: string): string | null {
  return /^\s*-/.test(command)
    ? "it starts with a Compose global flag, which would choose the project, file or env " +
        "file after the target check. Pass only the subcommand, and select the stack with " +
        "COMPOSE_PROJECT_NAME."
    : null;
}

let composeTargetConfirmed = false;

function dockerCompose(command: string): string {
  return execSync(`docker compose ${command}`, {
    cwd: REPO_ROOT,
    stdio: "pipe",
  }).toString();
}

/**
 * Runs `docker compose <command>` from the repository root. `command` is a fixed subcommand
 * and its arguments; it goes through a shell, so it must not chain another command. The
 * Compose-backed specs stop the worker and delete model settings, including a stored
 * Hugging Face token. So every call refuses a leading global flag, and the first call in
 * each worker checks composeTargetProblem, which at most asks the read-only
 * `docker compose port` about each service. Either throws before `command` runs.
 */
export function compose(command: string): string {
  const problem =
    composeCommandProblem(command) ??
    (composeTargetConfirmed
      ? null
      : composeTargetProblem({
          env: process.env,
          webOrigin: test.info().project.use.baseURL ?? "",
          apiOrigin: API_BASE,
          publishedPort: (service) =>
            dockerCompose(`port ${service} ${CONTAINER_PORT}`),
        }));
  if (problem !== null) {
    throw new Error(
      `Refusing to run \`docker compose ${command}\`: ${problem}`,
    );
  }
  composeTargetConfirmed = true;
  return dockerCompose(command);
}

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
