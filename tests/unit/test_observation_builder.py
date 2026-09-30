# SPDX-License-Identifier: Apache-2.0
"""OAK-S11-004: the observation record scores what the runner reported, and nothing else.

`EV-DEP-01/02/03` and the smoke test come only from accepted completions; every
prediction appears with its interval and, where nothing was observed, `unknown` with a
reason code; a single sample never satisfies a gate; the record proposes nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from oak.compiler.observation import RunnerResult, build_observation_record
from oak.contracts import SchemaRegistry, load_yaml_document
from oak.domain import ArtifactReference
from oak.domain.runner_adapters import ISOLATION_NEVER_STARTED, ISOLATION_STARTED_HARDENED
from tests.container_support import names, parameters

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = SchemaRegistry.from_directory(ROOT / "schemas")


def _ref(identifier: str) -> ArtifactReference:
    return ArtifactReference(
        id=identifier,
        version="0.1.0",
        digest="sha256:" + "a" * 64,
        uri=None,
        media_type="application/vnd.oak.runner-message+json",
    )


def _plan(isolation: str = ISOLATION_STARTED_HARDENED) -> dict[str, Any]:
    return {
        "target": {"id": "target.local-started-fixture", "fingerprint": "sha256:" + "b" * 64},
        "operations": [{"kind": "apply", "parameters": parameters(isolation)}],
    }


def _install(outcome: str = "succeeded", *, already: bool = False, passed: bool = True) -> dict:
    installed = [
        {
            "node_id": entry["node_id"],
            "container_name": entry["container_name"],
            "outcome": "already_present" if already else "created",
        }
        for entry in parameters()["containers"]
    ]
    evidence: list[dict[str, Any]] = [
        {"category": "status", "operation": "apply", "content": {"installation": installed}},
        {
            "category": "test_result",
            "operation": "apply",
            "content": {
                "passed": passed,
                "started": True,
                "smoke_test": [
                    {
                        "node_id": row["node_id"],
                        "container_name": row["container_name"],
                        "startup_seconds": 0.12,
                    }
                    for row in installed
                ],
            },
        },
        {
            "category": "aggregate_metric",
            "operation": "apply",
            "content": {
                "memory": [
                    {
                        "node_id": row["node_id"],
                        "container_name": row["container_name"],
                        "memory_bytes": 512_000,
                    }
                    for row in installed
                ]
            },
        },
    ]
    if outcome != "succeeded":
        evidence.append(_removal("compensation", absent=True)["evidence"][0])
    return {
        "outcome": outcome,
        "requested_kinds": ["apply"],
        "applied_kinds": ["apply"] if outcome == "succeeded" else [],
        "failed_kind": None if outcome == "succeeded" else "apply",
        "evidence": evidence,
    }


def _removal(operation: str = "rollback", *, absent: bool = True) -> dict:
    rows = [
        {"node_id": entry["node_id"], "container_name": name, "absent_after": absent}
        for entry, name in zip(parameters()["containers"], names(parameters()), strict=True)
    ]
    return {
        "outcome": "succeeded" if absent else "manual_recovery_required",
        "requested_kinds": ["rollback"],
        "applied_kinds": ["rollback"] if absent else [],
        "failed_kind": None if absent else "rollback",
        "evidence": [
            {
                "category": "rollback_result",
                "operation": operation,
                "content": {"removed_all": absent, "containers": rows},
            }
        ],
    }


def _record(*payloads: dict, plan: dict | None = None) -> dict[str, Any]:
    candidate = load_yaml_document(
        (ROOT / "examples/example-architecture-candidate.yaml").read_text(encoding="utf-8")
    )
    candidate["extensions"] = {
        "oak.community/estimator_metadata": {
            "version": "community-fixture-estimators-1.0.0",
            "evidence_population": "Public manual QA fixture on a declared x86_64 target.",
            "checked_at": "2026-08-16T12:00:00Z",
        }
    }
    contract = load_yaml_document(
        (ROOT / "examples/example-evaluation-contract.yaml").read_text(encoding="utf-8")
    )
    evaluation = load_yaml_document(
        (ROOT / "examples/example-evaluation-result.yaml").read_text(encoding="utf-8")
    )
    document = build_observation_record(
        record_id="observation.public-manual-qa.1",
        case_id="design-case.public-manual-qa",
        recorded_at="2026-09-29T12:00:00Z",
        recorded_by="local-user",
        candidate=candidate,
        candidate_ref=_ref("candidate-03"),
        evaluation=evaluation,
        evaluation_ref=_ref("evaluation-result.candidate-03"),
        contract=contract,
        plan=plan or _plan(),
        plan_ref=_ref("runner-plan.x"),
        bundle_ref=_ref("bundle.x"),
        target_profile={"platform": {"operating_system": "linux", "architecture": "x86_64"}},
        results=tuple(
            RunnerResult(
                reference=_ref(f"runner-message.completion.{index}"), message={"payload": p}
            )
            for index, p in enumerate(payloads, start=1)
        ),
    )
    REGISTRY.validate("observation-record.schema.json", document)
    return document


def _measure(record: dict, identifier: str) -> dict:
    return next(item for item in record["deployment_measures"] if item["id"] == identifier)


def test_one_install_is_one_passing_sample_that_satisfies_no_gate() -> None:
    record = _record(_install())

    install = _measure(record, "EV-DEP-01")
    assert (install["result"], install["successes"], install["sample_size"]) == ("pass", 1, 1)
    assert all(item["satisfies_gate"] is False for item in record["deployment_measures"])
    assert _measure(record, "smoke-test")["result"] == "pass"
    assert record["installation_state"] == "present"
    assert record["proposals"] == []


@pytest.mark.parametrize("identifier", ["EV-DEP-02", "EV-DEP-03"])
def test_an_unmeasured_deployment_measure_is_unknown_with_a_reason(identifier: str) -> None:
    measure = _measure(_record(_install()), identifier)

    assert measure["result"] == "unknown" and measure["value"] is None
    assert measure["sample_size"] == 0 and measure["reason"]


def test_a_failed_install_then_a_success_is_scored_below_the_threshold() -> None:
    record = _record(_install("failed", passed=False), _install())

    install = _measure(record, "EV-DEP-01")
    assert (install["successes"], install["sample_size"], install["result"]) == (1, 2, "fail")
    smoke = _measure(record, "smoke-test")
    assert (smoke["successes"], smoke["sample_size"]) == (1, 2)
    # The failed install's compensation removed what it created: a recovery sample.
    assert _measure(record, "EV-DEP-03")["result"] == "pass"


def test_a_repeated_apply_over_a_present_installation_is_the_idempotence_sample() -> None:
    record = _record(_install(), _install(already=True))

    assert _measure(record, "EV-DEP-01")["sample_size"] == 1
    reapply = _measure(record, "EV-DEP-02")
    assert (reapply["result"], reapply["sample_size"]) == ("pass", 1)


def test_a_re_apply_that_had_to_create_is_not_idempotent() -> None:
    record = _record(_install(), _install(already=False))

    assert _measure(record, "EV-DEP-02")["result"] == "fail"


def test_a_verified_rollback_passes_and_the_installation_reads_removed() -> None:
    record = _record(_install(), _removal())

    assert _measure(record, "EV-DEP-03")["result"] == "pass"
    assert record["installation_state"] == "removed"


def test_a_removal_that_left_a_container_behind_fails_recovery() -> None:
    record = _record(_install(), _removal(absent=False))

    assert _measure(record, "EV-DEP-03")["result"] == "fail"
    assert record["installation_state"] == "present"


def test_a_denied_dispatch_is_not_an_install_attempt() -> None:
    denied = {"outcome": "denied", "applied_kinds": [], "denial_code": "OAK-RUNNER-APPROVAL"}
    record = _record(denied, _install())

    assert _measure(record, "EV-DEP-01")["sample_size"] == 1
    # A denial never reached the target; it is neither scored nor mistaken for an
    # older completion missing its requested kinds.
    assert not any("requested_kinds" in line for line in record["limitations"])


def test_an_older_completion_without_requested_kinds_is_scored_and_disclosed() -> None:
    older = _install()
    del older["requested_kinds"]
    record = _record(older)

    assert _measure(record, "EV-DEP-01")["sample_size"] == 1
    assert any("requested_kinds" in line for line in record["limitations"])


def test_every_prediction_appears_and_every_unknown_says_why() -> None:
    record = _record(_install())

    names_seen = [row["name"] for row in record["calibration"]]
    assert names_seen[:2] == ["component_count", "answer_synthesis_quality"]
    assert "metric.latency-p95" in names_seen
    for row in record["calibration"]:
        assert row["observed"]["status"] == "unknown"
        assert row["observed"]["value"] is None
        assert row["observed"]["reason_code"] and row["observed"]["reason"]
        assert row["absolute_error"] is None and row["interval_covered"] is None
        assert row["recalibration_decision"] == "none — single non-production sample"
    latency = next(row for row in record["calibration"] if row["name"] == "metric.latency-p95")
    assert latency["observed"]["reason_code"] == "no_request_workload"
    assert "startup time is not request latency" in latency["observed"]["reason"]


def test_startup_and_memory_are_reported_as_measurements_without_a_prediction() -> None:
    record = _record(_install())

    metrics = {(item["node_id"], item["metric"]) for item in record["unpredicted_measurements"]}
    assert ("node.retrieval", "startup_seconds") in metrics
    assert ("node.generation", "memory_bytes") in metrics


def test_the_observed_calibration_requirement_names_what_is_missing() -> None:
    record = _record(_install())

    # The example candidate predicts none of the four calibrated measures: having nothing
    # to compare satisfies nothing, so each is named as not predicted.
    assert record["assurance"]["status"] == "not_satisfied"
    assert record["assurance"]["missing"] == [
        "monthly_cost: not_predicted",
        "latency_p95: not_predicted",
        "quality: not_predicted",
        "energy: not_predicted",
    ]


def test_a_never_started_install_discloses_what_its_smoke_test_checked() -> None:
    record = _record(_install(), plan=_plan(ISOLATION_NEVER_STARTED))

    assert any("creation and the resolved digest only" in line for line in record["limitations"])


def test_the_schema_refuses_a_proposal_a_passing_unknown_and_a_gate_claim() -> None:
    from oak.contracts import ContractValidationError

    record = _record(_install())
    for mutate in (
        lambda document: document["proposals"].append({"change": "promote"}),
        lambda document: document["deployment_measures"][1].update(value=1.0),
        lambda document: document["deployment_measures"][0].update(satisfies_gate=True),
        lambda document: document["calibration"][0]["observed"].update(reason_code=None),
    ):
        broken = __import__("copy").deepcopy(record)
        mutate(broken)
        with pytest.raises(ContractValidationError):
            REGISTRY.validate("observation-record.schema.json", broken)


# -- audit regressions (Sprint 11 closing audit) ---------------------------------------


def _failed_removal(operation: str = "rollback", *, first_fails: bool = True) -> dict:
    """A removal that stopped part-way: one container gone, the other not."""

    document = parameters()
    rows = [
        {
            "node_id": entry["node_id"],
            "container_name": entry["container_name"],
            "present_before": True,
            "absent_after": not (index == 0 and first_fails),
        }
        for index, entry in enumerate(document["containers"])
    ]
    return {
        "outcome": "manual_recovery_required",
        "requested_kinds": ["rollback"] if operation == "rollback" else ["apply"],
        "applied_kinds": [],
        "failed_kind": "rollback" if operation == "rollback" else "apply",
        "evidence": [
            {
                "category": "rollback_result",
                "operation": operation,
                "content": {"removed_all": False, "containers": rows},
            }
        ],
    }


def test_a_rollback_that_ended_in_manual_recovery_fails_recovery() -> None:
    """S15: whatever the rows say, a removal that failed is a failed recovery sample."""

    record = _record(_install(), _failed_removal())

    recovery = _measure(record, "EV-DEP-03")
    assert (recovery["result"], recovery["sample_size"]) == ("fail", 1)
    assert record["installation_state"] == "partial"


def test_a_rollback_that_failed_before_removing_anything_is_still_a_failed_sample() -> None:
    """S15: an empty record of a failed rollback is not 'no rollback has run'."""

    failed = _failed_removal()
    failed["evidence"][0]["content"]["containers"] = []
    record = _record(_install(), failed)

    assert _measure(record, "EV-DEP-03")["result"] == "fail"


def test_a_compensation_that_ended_in_manual_recovery_fails_recovery() -> None:
    record = _record(_failed_removal("compensation"))

    assert _measure(record, "EV-DEP-03")["result"] == "fail"


def test_a_rollback_of_nothing_is_not_a_recovery_sample() -> None:
    """S18: removing an installation that was never there proves nothing."""

    empty = _removal()
    for row in empty["evidence"][0]["content"]["containers"]:
        row["present_before"] = False
    record = _record(empty)

    assert _measure(record, "EV-DEP-03")["result"] == "unknown"


def test_an_incomplete_smoke_test_is_not_a_pass() -> None:
    """S16: a test that covered only some nodes has not passed."""

    partial = _install("failed")
    test = next(item for item in partial["evidence"] if item["category"] == "test_result")
    test["content"]["smoke_test"] = test["content"]["smoke_test"][:1]
    test["content"]["passed"] = True
    record = _record(partial)

    smoke = _measure(record, "smoke-test")
    assert (smoke["successes"], smoke["sample_size"]) == (0, 1)


def test_an_older_failed_completion_makes_the_measures_unattributable_not_passing() -> None:
    """S19: a failure with no requested kinds cannot be scored against anything."""

    older_failure = {"outcome": "failed", "applied_kinds": [], "evidence": []}
    record = _record(older_failure, _install())

    for identifier in ("EV-DEP-01", "EV-DEP-02", "EV-DEP-03"):
        measure = _measure(record, identifier)
        assert measure["result"] == "unknown"
        assert "cannot be attributed" in measure["reason"]


def test_a_single_container_plan_from_before_the_topology_installer_does_not_crash() -> None:
    """S19: the plan shape released in 0.7.1 and 0.8.0 is read, not a KeyError."""

    older_plan = {
        "target": {"id": "target.local-mutation-fixture", "fingerprint": "sha256:" + "b" * 64},
        "operations": [
            {
                "kind": "apply",
                "parameters": {
                    "container_name": "oak-fixture-local-mutation-fixture",
                    "image_reference": "postgres:17.6-alpine",
                    "image_digest": "sha256:" + "e" * 64,
                    "isolation": "network-none-never-started",
                },
            }
        ],
    }
    record = _record(_install(), plan=older_plan)

    assert record["installation_state"] in {"present", "partial", "unknown"}


def test_startup_time_comes_from_the_fresh_install_not_a_re_apply() -> None:
    """S20: a re-apply over a running installation measured no startup."""

    reapply = _install(already=True)
    for row in next(item for item in reapply["evidence"] if item["category"] == "test_result")[
        "content"
    ]["smoke_test"]:
        row["startup_seconds"] = 0.0
    record = _record(_install(), reapply)

    startups = {
        item["value"]
        for item in record["unpredicted_measurements"]
        if item["metric"] == "startup_seconds"
    }
    assert startups == {0.12}
    assert all(
        item["evidence_ref"]["id"] == "runner-message.completion.1"
        for item in record["unpredicted_measurements"]
    )


def test_completions_are_scored_in_dispatch_order_whatever_the_ingest_order() -> None:
    """S12: an earlier dispatch's completion ingested late still counts as earlier."""

    first = {**_install(), "evidence": _install()["evidence"]}
    second = _install(already=True)
    results = (
        RunnerResult(
            reference=_ref("runner-message.completion.late"),
            message={"payload": second, "lease_id": "lease.public-manual-qa.20", "id": "b"},
        ),
        RunnerResult(
            reference=_ref("runner-message.completion.early"),
            message={"payload": first, "lease_id": "lease.public-manual-qa.12", "id": "a"},
        ),
    )
    from oak.compiler.observation import _score

    scored = _score(
        results, {"isolation": "network-none-started-hardened", "names": names(parameters())}
    )
    measures = {item["id"]: item for item in scored.measures}
    assert measures["EV-DEP-01"]["sample_size"] == 1
    assert measures["EV-DEP-02"]["result"] == "pass"
