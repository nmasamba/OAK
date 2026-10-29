# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-021 (RR-021): the browser-suite runner refuses what a gate must not accept."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import run_browser_suite as runner
from scripts.run_browser_suite import (
    EXPECTED_SKIPS,
    FIXTURES,
    Outcome,
    SuiteError,
    check_outcome,
    check_target,
    override_document,
    read_report,
)

COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _spec(title: str, status: str) -> dict[str, Any]:
    return {"title": title, "tests": [{"status": status, "projectName": ""}]}


def _report(*extra: dict[str, Any], manual: str = "skipped") -> dict[str, Any]:
    return {
        "suites": [
            {
                "title": "journey.spec.ts",
                "specs": [_spec("the reference journey", "expected")],
                "suites": [{"title": "nested", "specs": [_spec("a described test", "expected")]}],
            },
            {
                "title": "manual-screens.spec.ts",
                "specs": [
                    _spec("capture the manual screenshots from the reference journey", manual),
                    _spec("capture the research figure on the fixture source", manual),
                ],
            },
            *extra,
        ],
        "errors": [],
    }


def test_a_run_with_only_the_known_skips_passes() -> None:
    outcome = read_report(_report())

    assert outcome.passed == 2
    assert set(outcome.skipped) == EXPECTED_SKIPS
    assert check_outcome(outcome) == []


def test_a_described_test_is_named_by_its_file_and_describe_block() -> None:
    report = _report({"title": "models.spec.ts", "specs": [_spec("chips", "skipped")]})
    report["suites"][0]["suites"][0]["specs"][0]["tests"][0]["status"] = "skipped"

    problems = check_outcome(read_report(report))

    assert "skipped but not expected to: journey.spec.ts > nested > a described test" in problems
    assert "skipped but not expected to: models.spec.ts > chips" in problems


def test_a_known_skip_that_ran_is_reported() -> None:
    problems = check_outcome(read_report(_report(manual="expected")))

    assert problems == [f"expected to skip but ran: {name}" for name in sorted(EXPECTED_SKIPS)]


@pytest.mark.parametrize("status", ["unexpected", "flaky", "timedOut", "interrupted"])
def test_a_test_that_did_not_pass_cleanly_fails_the_run(status: str) -> None:
    report = _report({"title": "report.spec.ts", "specs": [_spec("pager", status)]})

    assert check_outcome(read_report(report)) == [f"failed: report.spec.ts > pager ({status})"]


def test_a_suite_error_fails_the_run() -> None:
    report = _report()
    report["errors"] = [{"message": "Error: config\nstack"}]

    assert check_outcome(read_report(report)) == ["failed: suite error: Error: config"]


def test_an_empty_run_fails() -> None:
    outcome = Outcome(passed=0, skipped=tuple(sorted(EXPECTED_SKIPS)), failed=())

    assert check_outcome(outcome) == ["no test passed"]


def test_a_skip_reported_twice_fails() -> None:
    name = sorted(EXPECTED_SKIPS)[0]
    outcome = Outcome(passed=3, skipped=(*sorted(EXPECTED_SKIPS), name), failed=())

    assert check_outcome(outcome) == ["a skipped test name is reported twice"]


@pytest.mark.parametrize(
    ("project", "api", "web"),
    [
        ("oak-community", 28080, 25173),
        ("oak-e2e", 28080, 25173),
        ("oak-e2e-x; rm -rf /", 28080, 25173),
        ("oak-e2e-run", 8080, 25173),
        ("oak-e2e-run", 28080, 5173),
        ("oak-e2e-run", 15432, 25173),
        ("oak-e2e-run", 80, 25173),
        ("oak-e2e-run", 28080, 28080),
    ],
)
def test_a_target_that_could_reach_another_stack_is_refused(
    project: str, api: int, web: int
) -> None:
    with pytest.raises(SuiteError):
        check_target(project, api, web)


def test_a_run_named_target_on_its_own_ports_is_accepted() -> None:
    check_target("oak-e2e-1234567-1", 28080, 25173)


def test_the_override_binds_its_own_ports_commit_and_fixture() -> None:
    class Loader(yaml.SafeLoader):
        pass

    Loader.add_constructor("!override", lambda loader, node: loader.construct_sequence(node))
    document = yaml.load(override_document(COMMIT, 28080, 25173), Loader=Loader)
    services = document["services"]

    assert services["api"]["ports"] == ["127.0.0.1:28080:8080"]
    assert services["web"]["ports"] == ["127.0.0.1:25173:8080"]
    for name in ("migrate", "api", "worker"):
        assert services[name]["build"]["args"] == {"OAK_COMMIT": COMMIT}
    for name in ("api", "worker"):
        assert services[name]["environment"] == {"OAK_RESEARCH_FIXTURES": "/fixtures/research"}
        assert services[name]["volumes"] == [f"{FIXTURES}:/fixtures/research:ro"]
    assert set(services) == {"migrate", "api", "worker", "web"}


@pytest.mark.parametrize("commit", ["unknown", "HEAD", COMMIT[:7], COMMIT + '"\nx: 1'])
def test_the_override_refuses_anything_but_a_full_commit(commit: str) -> None:
    with pytest.raises(SuiteError):
        override_document(commit, 28080, 25173)


class _Stack:
    """Stands in for Docker and the suite: records commands, writes the report it is given."""

    def __init__(self, reported: str, report: dict[str, Any] | None, status: int = 0) -> None:
        self.reported = reported
        self.report = report
        self.status = status
        self.commands: list[list[str]] = []

    def run(self, argv: list[str], *, env: Any = None) -> int:
        self.commands.append(argv)
        if argv[:2] == ["pnpm", "--dir"]:
            assert env["COMPOSE_PROJECT_NAME"] == "oak-e2e-test"
            assert env["OAK_API_BASE_URL"] == "http://127.0.0.1:28080"
            if self.report is not None:
                Path(env["PLAYWRIGHT_JSON_OUTPUT_NAME"]).write_text(json.dumps(self.report))
            return self.status
        return 0


def _install(monkeypatch: pytest.MonkeyPatch, stack: _Stack) -> None:
    monkeypatch.setattr(runner, "_run", stack.run)
    monkeypatch.setattr(runner, "_reported_commit", lambda port: stack.reported)


def _ran_suite(stack: _Stack) -> bool:
    return any(command[:2] == ["pnpm", "--dir"] for command in stack.commands)


def _tore_down(stack: _Stack) -> bool:
    return stack.commands[-1][-5:] == ["down", "--volumes", "--rmi", "local", "--remove-orphans"]


def test_a_stack_that_names_another_commit_is_refused_before_the_suite_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = _Stack(reported="unknown", report=_report())
    _install(monkeypatch, stack)

    with pytest.raises(SuiteError, match="/version names 'unknown'"):
        runner.run("oak-e2e-test", 28080, 25173, COMMIT, keep=False)

    assert not _ran_suite(stack)
    assert _tore_down(stack)


def test_a_clean_report_from_a_failing_suite_still_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    stack = _Stack(reported=COMMIT, report=_report(), status=1)
    _install(monkeypatch, stack)

    with pytest.raises(SuiteError, match="the suite exited 1"):
        runner.run("oak-e2e-test", 28080, 25173, COMMIT, keep=False)
    assert _tore_down(stack)


def test_a_suite_that_wrote_no_report_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    stack = _Stack(reported=COMMIT, report=None)
    _install(monkeypatch, stack)

    with pytest.raises(SuiteError, match="wrote no report"):
        runner.run("oak-e2e-test", 28080, 25173, COMMIT, keep=False)


def test_a_passing_run_tears_its_project_down_unless_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    stack = _Stack(reported=COMMIT, report=_report())
    _install(monkeypatch, stack)

    assert runner.run("oak-e2e-test", 28080, 25173, COMMIT, keep=False) == 0
    assert stack.commands[0][:4] == ["docker", "compose", "-p", "oak-e2e-test"]
    assert _ran_suite(stack)
    assert _tore_down(stack)

    kept = _Stack(reported=COMMIT, report=_report())
    _install(monkeypatch, kept)
    assert runner.run("oak-e2e-test", 28080, 25173, COMMIT, keep=True) == 0
    assert not _tore_down(kept)
