// SPDX-License-Identifier: Apache-2.0
import { execSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const REPO_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
);

function composeOutput(command: string): string {
  return execSync(`docker compose ${command}`, {
    cwd: REPO_ROOT,
    stdio: "pipe",
  }).toString();
}

// RR-037 regression: a USER directive in a Dockerfile is a claim; the running
// container is the fact. These assertions interrogate the live stack the rest of
// the e2e suite runs against, so a compose override or entrypoint that silently
// restored root would fail here even with the Dockerfiles unchanged.
test("the web and api containers run as their unprivileged users", () => {
  test.skip(
    process.env["OAK_E2E_DOCKER"] !== "1",
    "requires the compose stack (set OAK_E2E_DOCKER=1)",
  );

  expect(composeOutput("exec -T web id -u").trim()).toBe("101");
  expect(composeOutput("exec -T api id -u").trim()).toBe("10001");
  expect(composeOutput("exec -T worker id -u").trim()).toBe("10001");
});
