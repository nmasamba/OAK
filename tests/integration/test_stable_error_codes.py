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
