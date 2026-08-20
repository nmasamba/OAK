# SPDX-License-Identifier: Apache-2.0
"""Governed policy evaluation over the compiled reference case."""

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from oak.adapters.persistence import FileWorkspaceRepository
from oak.adapters.policies import BuiltinPolicyEngine, LocalPolicyPackStore
from oak.application.policy import PolicyService
from oak.contracts import SchemaRegistry
from oak.domain import ArtifactReference, OAKError
from tests.runner_support import ROOT, build_compiled_case

pytestmark = pytest.mark.integration

PACK_ID = "pack.community-baseline"
PACK_DIRECTORY = ROOT / "policy-packs"


@pytest.fixture(scope="module")
def compiled_case(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return build_compiled_case(tmp_path_factory.mktemp("policy-case"))


def _service(harness: Any, pack_directory: Path | None = None) -> PolicyService:
    registry = harness.registry
    return PolicyService(
        FileWorkspaceRepository(harness.workspace, registry),
        registry,
        LocalPolicyPackStore((pack_directory or PACK_DIRECTORY,), registry),
        {"builtin": BuiltinPolicyEngine},
    )


def _version(harness: Any) -> str:
    case = FileWorkspaceRepository(harness.workspace, harness.registry).current_case()
    assert case is not None
    return str(case["version"])


def test_reference_case_evaluation_is_reviewable_and_audited(compiled_case: Any) -> None:
    service = _service(compiled_case)
    result = service.evaluate(
        PACK_ID,
        compiled_case.context("policy-evaluate-000001", _version(compiled_case)),
    )
    decision = result.decision
    assert decision["outcome"] == "review_required"
    assert decision["reasons"] == ["POL-EU-NEXUS-UNCONFIRMED", "POL-NO-EGRESS-OK"]
    assert decision["obligations"] == [
        "Confirm the regulatory nexus facts with the accountable legal owner.",
        "Keep the deny-all egress policy in every rendered manifest.",
    ]
    assert decision["case_id"] == result.case["id"]
    assert decision["pack_ref"]["id"] == PACK_ID
    assert "engine" not in decision
    assert result.case["status"] == "bundle_compiled"
    assert (
        result.case["extensions"]["oak.community/policy_decision_refs"][-1]["id"]
        == (decision["id"])
    )
    repository = FileWorkspaceRepository(compiled_case.workspace, compiled_case.registry)
    last_event_ref = repository.manifest()["audit_events"][-1]
    last_event = repository.read_json_artifact(ArtifactReference.from_document(last_event_ref))
    assert last_event["event_type"] == "policy_evaluated"
    assert last_event["extensions"]["oak.community/policy_engine"] == "policy-engine.builtin"

    retry = service.evaluate(
        PACK_ID,
        compiled_case.context("policy-evaluate-000001", _version(compiled_case)),
    )
    assert retry.duplicate is True
    assert retry.decision == decision


def test_same_inputs_yield_byte_identical_decisions_across_workspaces(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    first = build_compiled_case(tmp_path_factory.mktemp("policy-a"))
    second = build_compiled_case(tmp_path_factory.mktemp("policy-b"))
    decision_a = (
        _service(first)
        .evaluate(PACK_ID, first.context("policy-determinism-01", _version(first)))
        .decision
    )
    decision_b = (
        _service(second)
        .evaluate(PACK_ID, second.context("policy-determinism-01", _version(second)))
        .decision
    )
    assert decision_a == decision_b


def _pack_variant(tmp_path: Path, mutate: dict[str, Any]) -> Path:
    document = yaml.safe_load((PACK_DIRECTORY / "community-baseline.yaml").read_text())
    document = {**copy.deepcopy(document), **mutate}
    directory = tmp_path / "packs"
    directory.mkdir()
    (directory / "pack.yaml").write_text(yaml.safe_dump(document, sort_keys=True))
    return directory


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ({"expires_at": "2026-08-18T00:00:00Z"}, "OAK-POLICY-PACK-EXPIRED"),
        ({"effective_from": "2027-01-01T00:00:00Z"}, "OAK-POLICY-PACK-NOT-YET-EFFECTIVE"),
        ({"status": "draft"}, "OAK-POLICY-PACK-STATUS"),
    ],
)
def test_stale_or_inactive_packs_refuse_evaluation(
    compiled_case: Any, tmp_path: Path, mutation: dict[str, Any], code: str
) -> None:
    service = _service(compiled_case, _pack_variant(tmp_path, mutation))
    with pytest.raises(OAKError) as denial:
        service.evaluate(
            PACK_ID,
            compiled_case.context(f"policy-stale-{code[-12:]}", _version(compiled_case)),
        )
    assert denial.value.code == code


def test_unknown_engine_and_pack_fail_closed(compiled_case: Any) -> None:
    service = _service(compiled_case)
    with pytest.raises(OAKError) as unknown_engine:
        service.evaluate(
            PACK_ID,
            compiled_case.context("policy-unknown-eng-01", _version(compiled_case)),
            engine="imaginary",
        )
    assert unknown_engine.value.code == "OAK-POLICY-ENGINE-UNKNOWN"
    with pytest.raises(OAKError) as unknown_pack:
        service.evaluate(
            "pack.does-not-exist",
            compiled_case.context("policy-unknown-pack-1", _version(compiled_case)),
        )
    assert unknown_pack.value.code == "OAK-POLICY-PACK-NOT-FOUND"


def test_embedded_pack_tests_pass_under_the_builtin_engine() -> None:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    store = LocalPolicyPackStore((PACK_DIRECTORY,), registry)
    pack = store.load(PACK_ID)
    engine = BuiltinPolicyEngine()
    for test in pack["tests"]:
        evaluation = engine.evaluate(pack, test["subject"])
        assert evaluation.outcome == test["expected_outcome"], test["name"]
        assert list(evaluation.reasons) == sorted(test["expected_reason_codes"]), test["name"]


def test_expired_pack_refuses_even_for_a_previously_evaluated_request(
    compiled_case: Any, tmp_path: Path
) -> None:
    """Expiry must refuse, not replay a cached decision.

    The derived idempotency key is a function of pack and subject with no time
    component, so the same command re-run after the pack expires would otherwise
    return the original decision and present a stale automated outcome as current.
    """

    service = _service(compiled_case)
    key = "policy-expiry-replay-1"
    first = service.evaluate(PACK_ID, compiled_case.context(key, _version(compiled_case)))
    assert first.duplicate is False

    expired = _service(
        compiled_case, _pack_variant(tmp_path, {"expires_at": "2026-08-18T00:00:00Z"})
    )
    with pytest.raises(OAKError) as denial:
        expired.evaluate(PACK_ID, compiled_case.context(key, _version(compiled_case)))
    assert denial.value.code == "OAK-POLICY-PACK-EXPIRED"
