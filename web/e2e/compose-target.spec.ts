// SPDX-License-Identifier: Apache-2.0
// The decisions behind compose() in support.ts, exercised without Docker: whether a
// `docker compose` run from the repository root would reach the stack under test, and
// whether a command could choose another project after that check.
import { expect, test } from "@playwright/test";

import { composeCommandProblem, composeTargetProblem } from "./support";

const DEFAULT_ORIGINS = {
  webOrigin: "http://127.0.0.1:5173",
  apiOrigin: "http://127.0.0.1:8080",
};
const OTHER_ORIGINS = {
  webOrigin: "http://127.0.0.1:25173",
  apiOrigin: "http://127.0.0.1:28080",
};
const POINTED_ELSEWHERE = {
  OAK_WEB_BASE_URL: OTHER_ORIGINS.webOrigin,
  OAK_API_BASE_URL: OTHER_ORIGINS.apiOrigin,
};
const NAMED = { ...POINTED_ELSEWHERE, COMPOSE_PROJECT_NAME: "oak-e2e" };

// Stands in for `docker compose port <service> 8080` and records every question asked. A
// bare port is published on 127.0.0.1; any other value is printed as given. A missing
// service fails the way execSync does: "Command failed: …" first, Compose's stderr last.
function project(published: Partial<Record<"web" | "api", string>>) {
  const asked: string[] = [];
  const publishedPort = (service: "web" | "api") => {
    asked.push(service);
    const binding = published[service];
    if (binding === undefined) {
      throw new Error(
        `Command failed: docker compose port ${service} 8080\nservice "${service}" is not running\n`,
      );
    }
    return `${/^\d+$/.test(binding) ? `127.0.0.1:${binding}` : binding}\n`;
  };
  return { asked, publishedPort };
}

test.describe("which stack docker compose reaches", () => {
  test("an overridden origin without a project name is refused before Docker is asked anything", () => {
    for (const env of [
      { OAK_WEB_BASE_URL: OTHER_ORIGINS.webOrigin },
      { OAK_API_BASE_URL: OTHER_ORIGINS.apiOrigin },
      POINTED_ELSEWHERE,
      { ...POINTED_ELSEWHERE, COMPOSE_PROJECT_NAME: "" },
    ]) {
      const compose = project({ web: "5173", api: "8080" });
      const problem = composeTargetProblem({
        env,
        ...OTHER_ORIGINS,
        publishedPort: compose.publishedPort,
      });
      expect(problem, JSON.stringify(env)).toContain(
        "COMPOSE_PROJECT_NAME is not exported",
      );
      expect(compose.asked, JSON.stringify(env)).toEqual([]);
    }
  });

  test("an origin that is not 127.x.x.x or [::1] over http(s) is refused before Docker is asked anything", () => {
    for (const [apiOrigin, expected] of [
      ["", "not an absolute http(s) URL"],
      ["127.0.0.1:28080", "not an absolute http(s) URL"],
      ["localhost:28080", "not an absolute http(s) URL"],
      ["http://localhost:28080", "instead of localhost"],
      ["http://localhost.:28080", "not 127.x.x.x or [::1]"],
      ["http://[::ffff:127.0.0.1]:28080", "not 127.x.x.x or [::1]"],
      ["http://192.168.64.2:28080", "not 127.x.x.x or [::1]"],
      ["http://oak.example.test:28080", "not 127.x.x.x or [::1]"],
    ]) {
      const compose = project({ web: "25173", api: "28080" });
      const problem = composeTargetProblem({
        env: NAMED,
        webOrigin: OTHER_ORIGINS.webOrigin,
        apiOrigin: apiOrigin ?? "",
        publishedPort: compose.publishedPort,
      });
      expect(problem, apiOrigin).toContain(expected ?? "");
      expect(compose.asked, apiOrigin).toEqual([]);
    }
  });

  test("a named project that does not publish the API under test is refused", () => {
    const compose = project({ web: "5173", api: "8080" });
    const problem = composeTargetProblem({
      env: { ...POINTED_ELSEWHERE, COMPOSE_PROJECT_NAME: "oak-community" },
      ...OTHER_ORIGINS,
      publishedPort: compose.publishedPort,
    });
    expect(problem).toContain(
      `drives api at ${OTHER_ORIGINS.apiOrigin}, but the Compose project "oak-community" publishes its api on 127.0.0.1:8080`,
    );
    expect(compose.asked).toEqual(["api"]);
  });

  test("a named project that does not publish the web origin under test is refused", () => {
    const compose = project({ web: "5173", api: "28080" });
    const problem = composeTargetProblem({
      env: NAMED,
      ...OTHER_ORIGINS,
      publishedPort: compose.publishedPort,
    });
    expect(problem).toContain(`drives web at ${OTHER_ORIGINS.webOrigin}`);
    expect(compose.asked).toEqual(["api", "web"]);
  });

  test("the right port on an address other than the origin's own is refused", () => {
    for (const [api, apiOrigin, expected] of [
      ["192.168.64.2:28080", OTHER_ORIGINS.apiOrigin, "192.168.64.2:28080"],
      ["127.0.0.2:28080", OTHER_ORIGINS.apiOrigin, "127.0.0.2:28080"],
      ["[::]:28080", OTHER_ORIGINS.apiOrigin, "[::]:28080"],
      ["[::1]:28080", OTHER_ORIGINS.apiOrigin, "[::1]:28080"],
      ["127.0.0.1:28080", "http://[::1]:28080", "127.0.0.1:28080"],
      ["0.0.0.0:28080", "http://[::1]:28080", "0.0.0.0:28080"],
    ]) {
      const compose = project({ web: "25173", api: api ?? "" });
      const problem = composeTargetProblem({
        env: NAMED,
        webOrigin: OTHER_ORIGINS.webOrigin,
        apiOrigin: apiOrigin ?? "",
        publishedPort: compose.publishedPort,
      });
      expect(problem, `${api} for ${apiOrigin}`).toContain(
        `publishes its api on ${expected}`,
      );
    }
  });

  test("a project name that matches no running stack is refused with Compose's own reason", () => {
    const compose = project({});
    const problem = composeTargetProblem({
      env: { ...POINTED_ELSEWHERE, COMPOSE_PROJECT_NAME: "oak-nothing" },
      ...OTHER_ORIGINS,
      publishedPort: compose.publishedPort,
    });
    expect(problem).toContain(
      'the Compose project "oak-nothing" publishes no api port (service "api" is not running)',
    );
    expect(problem).not.toContain("Command failed");
  });

  test("output without a published binding is refused as publishing no port", () => {
    for (const output of [":0", ""]) {
      const compose = project({ web: "25173", api: output });
      const problem = composeTargetProblem({
        env: NAMED,
        ...OTHER_ORIGINS,
        publishedPort: compose.publishedPort,
      });
      expect(problem, JSON.stringify(output)).toContain(
        `publishes no api port (docker compose port printed ${JSON.stringify(output)}`,
      );
    }
  });

  test("a project name alone does not move the default origins", () => {
    const compose = project({ web: "25173", api: "28080" });
    const problem = composeTargetProblem({
      env: { COMPOSE_PROJECT_NAME: "oak-e2e" },
      ...DEFAULT_ORIGINS,
      publishedPort: compose.publishedPort,
    });
    expect(problem).toContain(`drives api at ${DEFAULT_ORIGINS.apiOrigin}`);
  });

  test("the project that publishes both origins under test is accepted", () => {
    for (const [published, origins] of [
      [{ web: "25173", api: "28080" }, OTHER_ORIGINS],
      [
        { web: "25173", api: "28080" },
        {
          webOrigin: "http://127.0.0.1:25173/",
          apiOrigin: "http://127.1:28080",
        },
      ],
      [
        { web: "80", api: "28080" },
        { webOrigin: "http://127.0.0.1", apiOrigin: OTHER_ORIGINS.apiOrigin },
      ],
      [{ web: "0.0.0.0:25173", api: "0.0.0.0:28080" }, OTHER_ORIGINS],
      [
        { web: "[::1]:25173", api: "[::]:28080" },
        {
          webOrigin: "http://[::1]:25173",
          apiOrigin: "http://[::1]:28080",
        },
      ],
    ] as const) {
      const compose = project(published);
      expect(
        composeTargetProblem({
          env: NAMED,
          ...origins,
          publishedPort: compose.publishedPort,
        }),
        JSON.stringify(published),
      ).toBeNull();
      expect(compose.asked).toEqual(["api", "web"]);
    }
  });

  test("the default stack at the default origins is accepted, after Docker is asked", () => {
    const compose = project({ web: "5173", api: "8080" });
    expect(
      composeTargetProblem({
        env: {},
        ...DEFAULT_ORIGINS,
        publishedPort: compose.publishedPort,
      }),
    ).toBeNull();
    expect(compose.asked).toEqual(["api", "web"]);
  });

  test("the default stack is refused when it is not running", () => {
    const compose = project({});
    const problem = composeTargetProblem({
      env: {},
      ...DEFAULT_ORIGINS,
      publishedPort: compose.publishedPort,
    });
    expect(problem).toContain(
      "the Compose project docker compose picks by default publishes no api port",
    );
    expect(compose.asked).toEqual(["api"]);
  });
});

test.describe("which commands compose() will run", () => {
  test("a global flag before the subcommand is refused", () => {
    for (const command of [
      "-p oak-community stop worker",
      "--project-name oak-community stop worker",
      "--file other.yaml exec -T api id -u",
      "  --env-file .env.other stop worker",
    ]) {
      expect(composeCommandProblem(command), command).toContain(
        "Compose global flag",
      );
    }
  });

  test("the subcommands the specs use are allowed", () => {
    for (const command of [
      "stop worker",
      "start worker",
      "exec -T api oak models token",
      "exec -T worker sh -c 'ls -A /var/lib/oak/model-state | wc -l'",
    ]) {
      expect(composeCommandProblem(command), command).toBeNull();
    }
  });
});
