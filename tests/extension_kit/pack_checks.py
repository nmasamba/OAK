# SPDX-License-Identifier: Apache-2.0
"""Policy-pack governance checks: fields, dating, embedded tests."""

from typing import Any

from oak.domain.policy_rules import pack_effective_window
from oak.ports.policy import PolicyEnginePort


def check_pack_governance_fields(pack: dict[str, Any]) -> None:
    """Licence, evidence, owner, scope, and review must be present and real."""

    assert str(pack["licence"]["spdx_expression"]).strip(), "pack must declare a licence"
    assert pack["evidence"], "pack must cite at least one evidence source"
    for evidence in pack["evidence"]:
        assert str(evidence["checked_at"]).strip(), "evidence must record checked_at"
    assert str(pack["owner"]).strip(), "pack must name an owner"
    assert pack["scope"]["jurisdictions"], "pack must declare jurisdiction scope"
    assert pack["scope"]["domains"], "pack must declare domain scope"
    assert str(pack["source_version"]).strip(), "pack must record its source version"
    assert pack["review"]["owner_review_status"] in {"pending", "approved", "rejected"}


def check_pack_lifecycle_dating(pack: dict[str, Any]) -> None:
    """Effective dating must gate evaluation on both sides of the window."""

    effective_from = str(pack["effective_from"])
    before = "1970-01-01T00:00:00Z"
    assert before < effective_from, "kit assumes the pack is not effective at the epoch"
    usable, reason = pack_effective_window(pack, at=before)
    assert usable is False and reason == "OAK-POLICY-PACK-NOT-YET-EFFECTIVE", (
        "a pack must refuse evaluation before its effective date"
    )
    if pack["expires_at"] is not None:
        usable, reason = pack_effective_window(pack, at="9999-12-31T00:00:00Z")
        assert usable is False and reason == "OAK-POLICY-PACK-EXPIRED", (
            "an expired pack must refuse evaluation"
        )


def check_pack_embedded_tests(pack: dict[str, Any], engine: PolicyEnginePort) -> None:
    """Every embedded fixture must reproduce its expected outcome and reasons."""

    assert pack["tests"], "pack must embed at least one test fixture"
    for test in pack["tests"]:
        evaluation = engine.evaluate(pack, dict(test["subject"]))
        assert evaluation.outcome == str(test["expected_outcome"]), (
            f"embedded test {test['name']!r} produced {evaluation.outcome}"
        )
        assert list(evaluation.reasons) == sorted(
            str(code) for code in test["expected_reason_codes"]
        ), f"embedded test {test['name']!r} produced reasons {list(evaluation.reasons)}"
