# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-006: one stable code must mean one thing.

`docs/compatibility.md` makes `OAK-*` codes part of the public surface, and both REST
and MCP replace the message of a not-found error with an opaque string — so on those
transports the code is the operator's *only* signal. Two codes were carrying two
meanings each when the error-code reference was compiled for this release.

`OAK-WORKSPACE-NOT-FOUND` meant both "the workspace is absent" and "the workspace is
present and one artifact lookup missed". `OAK-EXPECTED-VERSION` meant both "your version
is stale" and "your `If-Match` header is unusable" — and the second is worse than
cosmetic, because that code maps to HTTP 409 and CLI exit 4, which tell automation to
re-read and retry. A client that sent a weak entity tag will never succeed by retrying.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from oak.domain import OAKError

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.integration


def test_a_malformed_precondition_is_not_a_retriable_conflict() -> None:
    from oak.interfaces.api.app import _error_status, _expected_version

    for header in ('W/"3"', "", '""', "   "):
        with pytest.raises(OAKError) as refusal:
            _expected_version(header)
        assert refusal.value.code == "OAK-PRECONDITION-INVALID", header
        assert _error_status(refusal.value) != 409, header


def test_a_well_formed_precondition_still_parses() -> None:
    from oak.interfaces.api.app import _expected_version

    assert _expected_version('"0.1.3"') == "0.1.3"
    assert _expected_version("0.1.3") == "0.1.3"


def test_a_stale_version_remains_a_retriable_conflict() -> None:
    """The retry signal must keep working for the case it was designed for."""

    from oak.interfaces.api.app import _error_status

    assert _error_status(OAKError("OAK-EXPECTED-VERSION", "stale")) == 409


def test_an_artifact_miss_is_not_reported_as_a_missing_workspace() -> None:
    """Both codes still 404, but they no longer say the same thing."""

    from oak.interfaces.api.app import _error_status
    from oak.interfaces.mcp.tools import NOT_FOUND_CODES

    assert _error_status(OAKError("OAK-ARTIFACT-NOT-FOUND", "artifact was not found")) == 404
    assert "OAK-ARTIFACT-NOT-FOUND" in NOT_FOUND_CODES
    assert "OAK-WORKSPACE-NOT-FOUND" in NOT_FOUND_CODES


def test_no_source_site_still_calls_an_artifact_miss_a_missing_workspace() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "OAK-WORKSPACE-NOT-FOUND" in line and "artifact" in line:
                offenders.append(f"{path.relative_to(ROOT)}:{number}")

    assert not offenders, offenders


def test_the_documented_bound_matches_the_enforced_bound() -> None:
    """Three of four copies said "must contain 16 characters" for a minimum check.

    An operator reading an exact-length rule sizes keys to exactly 16 and may reject
    their own longer keys upstream.
    """

    exact_claim = re.compile(r"must contain (?:16|8) characters")
    offenders: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if exact_claim.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}")

    assert not offenders, offenders


def test_a_longer_idempotency_key_is_accepted_as_the_message_now_says() -> None:
    from oak.application import CommandContext
    from oak.application.candidate_planning import CandidatePlanningService

    context = CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key="a" * 64,
        expected_version=None,
        correlation_id="b" * 32,
        interface_origin="cli",
        occurred_at="2026-08-21T12:00:00Z",
    )

    CandidatePlanningService._check_context(context)


# OAK-V1-017: a case id the server does not hold is `OAK-CASE-NOT-FOUND` at every entry
# point. Each server case is stored as its own workspace, so a well-formed unknown id used
# to reach the store and come back as `OAK-WORKSPACE-NOT-FOUND`, the local CLI's code for
# "no workspace here", while a malformed id already answered `OAK-CASE-NOT-FOUND`.
UNKNOWN_CASE = "design-case.nobody-holds-this"
CASE_SCOPED_METHODS = (
    "architecture",
    "confirm",
    "create_assurance_plan",
    "export_design_case",
    "get_design_case",
    "interpret",
    "list_artifacts",
    "list_audit_events",
    "list_candidates",
    "read_artifact",
    "record_report",
    "research_plan",
    "resolve_interpreter",
    "review_research_item",
    "select_candidate",
    "submit_compile_bundle",
    "submit_evaluate_candidate",
    "submit_generate_candidates",
    "submit_research",
)


def _unknown_case_calls(plane):  # type: ignore[no-untyped-def]
    import yaml

    from oak.application import CommandContext

    def context(step: str) -> CommandContext:
        return CommandContext(
            actor="local-user",
            tenant_id="local",
            idempotency_key=f"unknown-case-{step}",
            expected_version="0.1.0",
            correlation_id=f"unknown-case-{step}",
            interface_origin="rest",
            occurred_at="2026-10-26T12:00:00Z",
        )

    target = yaml.safe_load(
        (ROOT / "examples/targets/local-fixture.yaml").read_text(encoding="utf-8")
    )
    digest = "sha256:" + "0" * 64
    case = UNKNOWN_CASE
    return {
        "architecture": lambda: plane.architecture(
            case, tenant_id="local", candidate_id=None, now="2026-10-26T12:00:00Z"
        ),
        "confirm": lambda: plane.confirm(case, {}, context("confirm")),
        "create_assurance_plan": lambda: plane.create_assurance_plan(
            case, "candidate-03", context("assure")
        ),
        "export_design_case": lambda: plane.export_design_case(case, tenant_id="local"),
        "get_design_case": lambda: plane.get_design_case(case, tenant_id="local"),
        "interpret": lambda: plane.interpret(case, context("interpret")),
        "list_artifacts": lambda: plane.list_artifacts(case, tenant_id="local"),
        "list_audit_events": lambda: plane.list_audit_events(case, tenant_id="local"),
        "list_candidates": lambda: plane.list_candidates(case, tenant_id="local"),
        "read_artifact": lambda: plane.read_artifact(
            case, tenant_id="local", artifact_id="design-case", version="0.1.0", digest=digest
        ),
        "record_report": lambda: plane.record_report(case, context("record-report")),
        "research_plan": lambda: plane.research_plan(case, tenant_id="local"),
        "resolve_interpreter": lambda: plane.resolve_interpreter(
            case, tenant_id="local", interpreter="deterministic"
        ),
        "review_research_item": lambda: plane.review_research_item(
            case, context("review"), item_id="item-1", decision="accept", rationale="why"
        ),
        "select_candidate": lambda: plane.select_candidate(
            case, "candidate-03", "why", context("select")
        ),
        "submit_compile_bundle": lambda: plane.submit_compile_bundle(
            case, "candidate-03", target, context("compile")
        ),
        "submit_evaluate_candidate": lambda: plane.submit_evaluate_candidate(
            case, "candidate-03", context("evaluate")
        ),
        "submit_generate_candidates": lambda: plane.submit_generate_candidates(
            case, context("generate")
        ),
        "submit_research": lambda: plane.submit_research(
            case, {"hosts": [], "terms_digest": digest}, context("research")
        ),
    }


def test_every_case_scoped_entry_point_is_checked(tmp_path: Path) -> None:
    """A new public method that takes a case id must join the table, and so the check."""

    import inspect

    from oak.application.control_plane import CommunityControlPlane
    from tests.mcp_support import build_file_control_plane

    scoped = {
        name
        for name, member in inspect.getmembers(CommunityControlPlane, inspect.isfunction)
        if not name.startswith("_") and "case_id" in inspect.signature(member).parameters
    }
    plane, _ = build_file_control_plane(tmp_path)

    assert scoped == set(CASE_SCOPED_METHODS)
    assert set(_unknown_case_calls(plane)) == scoped


@pytest.mark.parametrize("method", CASE_SCOPED_METHODS)
def test_an_unknown_case_is_case_not_found_at_every_entry_point(
    tmp_path: Path, method: str
) -> None:
    from tests.mcp_support import build_file_control_plane, drain_operations

    plane, store = build_file_control_plane(tmp_path)

    with pytest.raises(OAKError) as refusal:
        _unknown_case_calls(plane)[method]()

    assert refusal.value.code == "OAK-CASE-NOT-FOUND"
    assert not any((tmp_path / "workspaces").iterdir())
    assert drain_operations(plane, store) == 0


def test_a_missing_workspace_is_still_its_own_code_locally(tmp_path: Path) -> None:
    """The local answer keeps its one meaning: there is no workspace at this location."""

    from oak.adapters.persistence.file_workspace import FileWorkspaceRepository
    from oak.contracts import SchemaRegistry

    repository = FileWorkspaceRepository(
        tmp_path / "nowhere", SchemaRegistry.from_directory(ROOT / "schemas")
    )

    with pytest.raises(OAKError) as refusal:
        repository.current_case()

    assert refusal.value.code == "OAK-WORKSPACE-NOT-FOUND"
