// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "@playwright/test";

import { compose } from "./support";

// RR-037 regression: a USER directive in a Dockerfile is a claim; the running
// container is the fact. These assertions interrogate the live stack the rest of
// the e2e suite runs against, so a compose override or entrypoint that silently
// restored root would fail here even with the Dockerfiles unchanged.
test("the web and api containers run as their unprivileged users", () => {
  test.skip(
    process.env["OAK_E2E_DOCKER"] !== "1",
    "requires the compose stack (set OAK_E2E_DOCKER=1)",
  );

  expect(compose("exec -T web id -u").trim()).toBe("101");
  expect(compose("exec -T api id -u").trim()).toBe("10001");
  expect(compose("exec -T worker id -u").trim()).toBe("10001");
});

// RR-040: provider keys live on a volume the api service alone mounts. A named volume
// inherits ownership and mode from the image path it covers, so "the Dockerfile says
// install -d -m 0700" is a claim about the build, not about the running container.
test("the model-state volume is owner-only on api and holds nothing on the worker", () => {
  test.skip(
    process.env["OAK_E2E_DOCKER"] !== "1",
    "requires the compose stack (set OAK_E2E_DOCKER=1)",
  );

  expect(
    compose("exec -T api stat -c '%u %g %a' /var/lib/oak/model-state").trim(),
  ).toBe("10001 10001 700");

  // The worker is built from the same image, so the directory exists there too — what
  // must not exist there is any content. The volume is mounted on api alone, so the
  // worker's copy stays the empty one the image created, and no key or token is
  // reachable from it. That, not the path's absence, is the property worth asserting.
  expect(
    compose(
      "exec -T worker sh -c 'ls -A /var/lib/oak/model-state | wc -l'",
    ).trim(),
  ).toBe("0");
  expect(
    compose(
      "exec -T worker sh -c 'find /var/lib/oak -name \"*.key\" -o -name api-token | wc -l'",
    ).trim(),
  ).toBe("0");
});
