# SPDX-License-Identifier: Apache-2.0
"""Run the browser suite on a Compose project of its own, then check what it skipped.

The browser suite (`make web-e2e`) acts on whichever stack `docker compose` reaches: it stops
and restarts that stack's worker and deletes its model settings. This script gives it a
stack nobody else uses. It builds the images from the working tree, starts them under a
project name of their own on loopback ports of their own, with the recorded research
fixture on `api` and `worker`, and checks that `/version` names the commit it built, so the
suite cannot test a stale stack that happens to answer on the port. It then runs the suite
and fails unless every test passed and the tests that skipped are exactly the known ones:
a skip that appears, or a known one that stops skipping, is a change someone must review.
Afterwards it removes the project, its volumes and its images.

CI and the release gate run it (RR-021). It uploads nothing: Playwright's report, traces
and screenshots stay in the ignored `web/test-results/` of the machine that ran it, because
a failed page can show a brief or a model-key field.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "research" / "e2e"

# The tests the suite skips by design. Both capture the manual's figures and run only when
# OAK_MANUAL_SCREENS=1 (docs/manual/README.md); nothing else may skip in a gate run.
EXPECTED_SKIPS = frozenset(
    {
        "manual-screens.spec.ts > capture the manual screenshots from the reference journey",
        "manual-screens.spec.ts > capture the research figure on the fixture source",
    }
)

# The owner's default stack (compose.yaml's `name:` and its ports) is never a target.
_PROJECT = re.compile(r"oak-e2e-[a-z0-9][a-z0-9-]{0,40}")
_RESERVED_PORTS = frozenset({5173, 8080, 15432})
_COMMIT = re.compile(r"[0-9a-f]{40}")


class SuiteError(RuntimeError):
    """The run did not prove what a gate needs; the message says why."""


@dataclass(frozen=True)
class Outcome:
    passed: int
    skipped: tuple[str, ...]
    failed: tuple[str, ...]


def check_target(project: str, api_port: int, web_port: int) -> None:
    """Refuse a project name or port that could reach someone else's stack."""

    if _PROJECT.fullmatch(project) is None:
        raise SuiteError(f"project name must match {_PROJECT.pattern!r}: {project!r}")
    for port in (api_port, web_port):
        if not 1024 <= port <= 65535 or port in _RESERVED_PORTS:
            raise SuiteError(f"port {port} is reserved or out of range")
    if api_port == web_port:
        raise SuiteError("the api and web ports must differ")


def override_document(commit: str, api_port: int, web_port: int) -> str:
    """The Compose override for the run: its ports, its commit and the research fixture.

    It is written at run time because `!override` is a tag a YAML safe loader refuses, and
    the original spec repo's validator safe-loads every YAML file in the tree.
    """

    if _COMMIT.fullmatch(commit) is None:
        raise SuiteError(f"commit must be a full SHA: {commit!r}")
    fixture = json.dumps(f"{FIXTURES}:/fixtures/research:ro")
    build = f'    build:\n      args:\n        OAK_COMMIT: "{commit}"\n'
    research = (
        "    environment:\n"
        "      OAK_RESEARCH_FIXTURES: /fixtures/research\n"
        f"    volumes:\n      - {fixture}\n"
    )
    return (
        "services:\n"
        f"  migrate:\n{build}"
        f"  api:\n{build}{research}"
        f'    ports: !override\n      - "127.0.0.1:{api_port}:8080"\n'
        f"  worker:\n{build}{research}"
        f'  web:\n    ports: !override\n      - "127.0.0.1:{web_port}:8080"\n'
    )


def _specs(suite: Mapping[str, Any], titles: tuple[str, ...]) -> Iterator[tuple[str, str]]:
    path = (*titles, str(suite.get("title", "")))
    for spec in suite.get("specs", []):
        name = " > ".join((*[part for part in path if part], str(spec["title"])))
        for test in spec.get("tests", []):
            yield name, str(test.get("status"))
    for child in suite.get("suites", []):
        yield from _specs(child, path)


def read_report(report: Mapping[str, Any]) -> Outcome:
    """Count a Playwright JSON report's tests by outcome."""

    passed = 0
    skipped: list[str] = []
    failed: list[str] = []
    for suite in report.get("suites", []):
        for name, status in _specs(suite, ()):
            if status == "expected":
                passed += 1
            elif status == "skipped":
                skipped.append(name)
            else:
                # "unexpected" failed; "flaky" passed only on a retry, which the suite
                # does not allow, so either is a failure.
                failed.append(f"{name} ({status})")
    for error in report.get("errors", []):
        failed.append(f"suite error: {str(error.get('message', '')).splitlines()[0][:200]}")
    return Outcome(passed=passed, skipped=tuple(sorted(skipped)), failed=tuple(failed))


def check_outcome(outcome: Outcome, expected: frozenset[str] = EXPECTED_SKIPS) -> list[str]:
    """Return why the run does not count as a pass, or nothing."""

    problems = [f"failed: {name}" for name in outcome.failed]
    if outcome.passed == 0:
        problems.append("no test passed")
    skipped = set(outcome.skipped)
    problems.extend(f"skipped but not expected to: {name}" for name in sorted(skipped - expected))
    problems.extend(f"expected to skip but ran: {name}" for name in sorted(expected - skipped))
    if len(outcome.skipped) != len(skipped):
        problems.append("a skipped test name is reported twice")
    return problems


def _run(argv: list[str], *, env: Mapping[str, str] | None = None) -> int:
    print("+ " + " ".join(argv), flush=True)
    return subprocess.run(argv, cwd=ROOT, env=env, check=False).returncode


def _head_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def _reported_commit(api_port: int) -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:{api_port}/version", timeout=10) as answer:
        document = json.load(answer)
    return str(document.get("commit"))


def run(project: str, api_port: int, web_port: int, commit: str, keep: bool) -> int:
    check_target(project, api_port, web_port)
    with tempfile.TemporaryDirectory(prefix="oak-browser-suite-") as scratch:
        override = Path(scratch) / "compose.override.yaml"
        override.write_text(override_document(commit, api_port, web_port), encoding="utf-8")
        report = Path(scratch) / "report.json"
        compose = ["docker", "compose", "-p", project, "-f", "compose.yaml", "-f", str(override)]
        try:
            if _run([*compose, "up", "--detach", "--build", "--wait", "--wait-timeout", "600"]):
                raise SuiteError("the stack did not become healthy")
            reported = _reported_commit(api_port)
            if reported != commit:
                raise SuiteError(f"/version names {reported!r}, not the commit built ({commit})")
            environment = {
                **os.environ,
                "OAK_E2E_DOCKER": "1",
                "COMPOSE_PROJECT_NAME": project,
                "OAK_WEB_BASE_URL": f"http://127.0.0.1:{web_port}",
                "OAK_API_BASE_URL": f"http://127.0.0.1:{api_port}",
                "PLAYWRIGHT_JSON_OUTPUT_NAME": str(report),
            }
            status = _run(["pnpm", "--dir", "web", "e2e", "--reporter=list,json"], env=environment)
            if not report.is_file():
                raise SuiteError(f"the suite wrote no report (exit {status})")
            outcome = read_report(json.loads(report.read_text(encoding="utf-8")))
            problems = check_outcome(outcome)
            if status != 0 and not problems:
                problems.append(f"the suite exited {status}")
            print(
                f"browser suite: {outcome.passed} passed, {len(outcome.skipped)} skipped "
                f"(expected {len(EXPECTED_SKIPS)}), {len(outcome.failed)} failed",
                flush=True,
            )
            if problems:
                raise SuiteError("; ".join(problems))
        finally:
            if not keep:
                _run([*compose, "down", "--volumes", "--rmi", "local", "--remove-orphans"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--project", default="oak-e2e-local")
    parser.add_argument("--api-port", type=int, default=28080)
    parser.add_argument("--web-port", type=int, default=25173)
    parser.add_argument("--commit", help="the commit /version must name (default: HEAD)")
    parser.add_argument("--keep", action="store_true", help="leave the project running")
    arguments = parser.parse_args(argv)
    try:
        return run(
            arguments.project,
            arguments.api_port,
            arguments.web_port,
            arguments.commit or _head_commit(),
            arguments.keep,
        )
    except SuiteError as error:
        print(f"browser suite refused: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
