# SPDX-License-Identifier: Apache-2.0
"""Observation records: what an installation was seen to do, beside what was predicted.

A pure function of documents the control plane already holds — the selected candidate,
its evaluation, the contract, the compiled plan, and the signed runner completions that
ingest accepted. Nothing here reads a clock, a network or a runner; nothing here can
propose, promote or authorize anything. An `unknown` never passes and always says why.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from oak.domain import ArtifactReference

OBSERVATION_MEDIA_TYPE = "application/vnd.oak.observation-record+json"
SINGLE_SAMPLE = "none — single non-production sample"
NO_DRIFT_ASSESSMENT = "not assessed — a single non-production sample has no baseline to drift from"
NO_WORKLOAD = "none — only install, readiness and resource readings; no request was sent"
GATE_LIMITATION = (
    "A single sample cannot satisfy an EV-DEP gate: gates need fixture counts and "
    "confidence intervals, and this is one non-production install."
)
# The governance calibration list names cost, latency, quality and energy; the assurance
# plan's `evidence.observed-calibration` asks for exactly these to be observed.
CALIBRATED_OBJECTIVES = ("monthly_cost", "latency_p95", "quality", "energy")

_OBJECTIVE_REASONS: dict[str, tuple[str, str]] = {
    "monthly_cost": (
        "not_observable_on_fixture",
        "A local fixture install incurs no billed cost; a monthly cost needs a priced "
        "deployment observed over a billing period.",
    ),
    "latency_p95": (
        "no_request_workload",
        "No request workload ran against the installation; container startup time is not "
        "request latency.",
    ),
    "quality": (
        "requires_workload_and_human_review",
        "Answer quality needs a representative workload and human review of the answers.",
    ),
    "operability": (
        "not_measured",
        "Operability is a fixture score with no counterpart a single install can measure.",
    ),
    "energy": (
        "no_energy_measurement",
        "The runner reads no power or energy counter.",
    ),
}
_METRIC_REASONS: dict[str, tuple[str, str]] = {
    "latency": (
        "no_request_workload",
        "No request workload ran against the installation; container startup time is not "
        "request latency.",
    ),
    "quality": (
        "requires_workload_and_human_review",
        "This metric is adjudicated over answers to a representative workload by a person.",
    ),
    "safety": (
        "requires_workload_and_human_review",
        "This metric is adjudicated over answers to a representative workload by a person.",
    ),
}
_NOT_MEASURED = ("not_measured", "Nothing the runner reports corresponds to this measure.")


@dataclass(frozen=True, slots=True)
class RunnerResult:
    """One accepted runner completion and the reference under which it is stored."""

    reference: ArtifactReference
    message: dict[str, Any]


def build_observation_record(
    *,
    record_id: str,
    case_id: str,
    recorded_at: str,
    recorded_by: str,
    candidate: dict[str, Any],
    candidate_ref: ArtifactReference,
    evaluation: dict[str, Any] | None,
    evaluation_ref: ArtifactReference | None,
    contract: dict[str, Any],
    plan: dict[str, Any],
    plan_ref: ArtifactReference,
    bundle_ref: ArtifactReference,
    target_profile: dict[str, Any],
    results: tuple[RunnerResult, ...],
) -> dict[str, Any]:
    installation = _planned_installation(plan)
    scored = _score(results, installation)
    declared = target_profile.get("platform", {})
    hardware = (
        f"declared {declared.get('operating_system', 'unknown')}/"
        f"{declared.get('architecture', 'unknown')} on {plan['target']['id']}; "
        "the host itself was not measured"
    )
    calibration = [
        *(_objective_row(objective, candidate, hardware) for objective in candidate["objectives"]),
        *(_metric_row(metric, evaluation, hardware) for metric in contract["metrics"]),
    ]
    # A measure the candidate never predicted is missing too: nothing is satisfied by
    # having had nothing to compare.
    objective_rows = {row["name"]: row for row in calibration if row["subject"] == "objective"}
    missing = [
        f"{name}: not_predicted"
        if name not in objective_rows
        else f"{name}: {objective_rows[name]['observed']['reason_code']}"
        for name in CALIBRATED_OBJECTIVES
        if name not in objective_rows or objective_rows[name]["observed"]["status"] != "observed"
    ]
    limitations = [
        "One install on a non-production local target; nothing here is production evidence.",
        "Only installation, readiness and resource readings were observed; the installed "
        "images are whatever the operator acknowledged in the target profile, and no request "
        "was sent to them.",
        GATE_LIMITATION,
    ]
    if installation["isolation"] != "network-none-started-hardened":
        limitations.append(
            "The target does not acknowledge starting containers, so the smoke test checked "
            "creation and the resolved digest only."
        )
    if scored.untyped:
        limitations.append(
            f"{scored.untyped} completion(s) carry no requested_kinds (an older runner); they "
            "were scored from the kinds they applied."
        )
    return {
        "schema_version": "0.1.0",
        "id": record_id,
        "version": "0.1.0",
        "case_id": case_id,
        "recorded_at": recorded_at,
        "recorded_by": recorded_by,
        "selected_candidate_ref": candidate_ref.to_document(),
        "evaluation_result_ref": evaluation_ref.to_document() if evaluation_ref else None,
        "runner_plan_ref": plan_ref.to_document(),
        "bundle_ref": bundle_ref.to_document(),
        "target": {
            "id": plan["target"]["id"],
            "fingerprint": plan["target"]["fingerprint"],
            "declared_platform": (
                f"{declared.get('operating_system', 'unknown')}/"
                f"{declared.get('architecture', 'unknown')}"
            ),
            "isolation": installation["isolation"],
        },
        "source_message_refs": [result.reference.to_document() for result in results],
        "installation_state": scored.installation_state,
        "deployment_measures": scored.measures,
        "calibration": calibration,
        "unpredicted_measurements": scored.unpredicted,
        "assurance": {
            "requirement_id": "evidence.observed-calibration",
            "status": "not_satisfied" if missing else "satisfied",
            "missing": missing,
        },
        "limitations": limitations,
        "proposals": [],
        "extensions": {},
    }


@dataclass(frozen=True, slots=True)
class _Scored:
    measures: list[dict[str, Any]]
    unpredicted: list[dict[str, Any]]
    installation_state: str
    untyped: int


@dataclass
class _Tally:
    successes: int = 0
    attempts: int = 0
    refs: list[dict[str, Any]] | None = None

    def add(self, success: bool, reference: ArtifactReference) -> None:
        self.attempts += 1
        self.successes += int(success)
        if self.refs is None:
            self.refs = []
        document = reference.to_document()
        if document not in self.refs:
            self.refs.append(document)


def _planned_installation(plan: dict[str, Any]) -> dict[str, Any]:
    for operation in plan["operations"]:
        if operation["kind"] == "apply":
            parameters = operation["parameters"]
            return {
                "isolation": parameters.get("isolation"),
                "names": [str(entry["container_name"]) for entry in parameters["containers"]],
            }
    return {"isolation": None, "names": []}


def _score(results: tuple[RunnerResult, ...], installation: dict[str, Any]) -> _Scored:
    install, reapply, removal, smoke = _Tally(), _Tally(), _Tally(), _Tally()
    present: dict[str, bool] = {}
    seen_any = False
    untyped = 0
    unpredicted: list[dict[str, Any]] = []
    planned = installation["names"]
    for result in results:
        payload = result.message.get("payload", {})
        if not isinstance(payload, dict) or payload.get("outcome") == "denied":
            continue
        requested = payload.get("requested_kinds")
        applied = list(payload.get("applied_kinds") or [])
        if not isinstance(requested, list):
            untyped += 1
            requested = [
                *applied,
                *([payload["failed_kind"]] if payload.get("failed_kind") else []),
            ]
        evidence = [item for item in payload.get("evidence") or [] if isinstance(item, dict)]
        succeeded = payload.get("outcome") == "succeeded"
        if "apply" in requested:
            rows = _rows(evidence, "status", "apply", "installation")
            was_installed = bool(planned) and all(present.get(name) for name in planned)
            if was_installed:
                reapply.add(
                    succeeded
                    and "apply" in applied
                    and all(row.get("outcome") == "already_present" for row in rows),
                    result.reference,
                )
            else:
                install.add(succeeded and "apply" in applied, result.reference)
            for row in rows:
                present[str(row.get("container_name"))] = True
                seen_any = True
            for item in evidence:
                if item.get("category") == "test_result" and item.get("operation") == "apply":
                    content = item.get("content", {})
                    smoke.add(bool(content.get("passed")), result.reference)
                    if succeeded:
                        unpredicted = _unpredicted(evidence, result.reference)
        for item in evidence:
            if item.get("category") != "rollback_result":
                continue
            content = item.get("content", {})
            rows = [row for row in content.get("containers", []) if isinstance(row, dict)]
            # A compensation that had nothing to remove is not a recovery sample.
            if item.get("operation") in {"rollback", "compensation"} and rows:
                removal.add(all(row.get("absent_after") is True for row in rows), result.reference)
            for row in rows:
                present[str(row.get("container_name"))] = row.get("absent_after") is not True
                seen_any = True
        if (
            "rollback" in requested
            and payload.get("failed_kind") == "rollback"
            and not any(item.get("category") == "rollback_result" for item in evidence)
        ):
            removal.add(False, result.reference)
    return _Scored(
        measures=[
            _measure(
                "EV-DEP-01",
                "Fresh install success",
                install,
                0.95,
                "No install was attempted on this case.",
            ),
            _measure(
                "EV-DEP-02",
                "Idempotent re-apply success",
                reapply,
                1.0,
                "No apply was repeated while the installation was present.",
            ),
            _measure(
                "EV-DEP-03",
                "Rollback recovery",
                removal,
                1.0,
                "No rollback or compensation has run on this case.",
            ),
            _measure(
                "smoke-test",
                "Post-install smoke test",
                smoke,
                1.0,
                "No install reported a smoke test.",
            ),
        ],
        unpredicted=unpredicted,
        installation_state=_installation_state(planned, present, seen_any),
        untyped=untyped,
    )


def _rows(
    evidence: list[dict[str, Any]], category: str, operation: str, key: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in evidence:
        if item.get("category") == category and item.get("operation") == operation:
            rows.extend(
                row for row in item.get("content", {}).get(key, []) if isinstance(row, dict)
            )
    return rows


def _unpredicted(
    evidence: list[dict[str, Any]], reference: ArtifactReference
) -> list[dict[str, Any]]:
    measurements: list[dict[str, Any]] = []
    for row in _rows(evidence, "test_result", "apply", "smoke_test"):
        if isinstance(row.get("startup_seconds"), int | float):
            measurements.append(
                _unpredicted_row(
                    row, "startup_seconds", row["startup_seconds"], "seconds", reference
                )
            )
    for row in _rows(evidence, "aggregate_metric", "apply", "memory"):
        measurements.append(
            _unpredicted_row(
                row,
                "memory_bytes",
                row["memory_bytes"] if isinstance(row.get("memory_bytes"), int) else None,
                "bytes",
                reference,
            )
        )
    return measurements


def _unpredicted_row(
    row: dict[str, Any], metric: str, value: Any, unit: str, reference: ArtifactReference
) -> dict[str, Any]:
    return {
        "node_id": str(row.get("node_id")),
        "container_name": str(row.get("container_name")),
        "metric": metric,
        "value": value,
        "unit": unit,
        "evidence_ref": reference.to_document(),
    }


def _measure(
    identifier: str, name: str, tally: _Tally, threshold: float, unknown_reason: str
) -> dict[str, Any]:
    if tally.attempts == 0:
        return {
            "id": identifier,
            "name": name,
            "result": "unknown",
            "value": None,
            "successes": 0,
            "sample_size": 0,
            "threshold": threshold,
            "satisfies_gate": False,
            "evidence_refs": [],
            "reason": unknown_reason,
            "limitations": [GATE_LIMITATION],
        }
    value = round(tally.successes / tally.attempts, 4)
    return {
        "id": identifier,
        "name": name,
        "result": "pass" if value >= threshold else "fail",
        "value": value,
        "successes": tally.successes,
        "sample_size": tally.attempts,
        "threshold": threshold,
        "satisfies_gate": False,
        "evidence_refs": list(tally.refs or []),
        "reason": None,
        "limitations": [GATE_LIMITATION],
    }


def _installation_state(planned: list[str], present: dict[str, bool], seen_any: bool) -> str:
    if not planned or not seen_any:
        return "unknown"
    states = [present.get(name) for name in planned]
    if all(state is True for state in states):
        return "present"
    if all(state is False for state in states):
        return "removed"
    return "partial"


def _objective_row(
    objective: dict[str, Any], candidate: dict[str, Any], hardware: str
) -> dict[str, Any]:
    metadata = candidate.get("extensions", {}).get("oak.community/estimator_metadata", {})
    reason_code, reason = _OBJECTIVE_REASONS.get(str(objective["name"]), _NOT_MEASURED)
    population = str(metadata.get("evidence_population") or "not recorded")
    checked = metadata.get("checked_at")
    return _unknown_row(
        subject="objective",
        name=str(objective["name"]),
        unit=str(objective["unit"]),
        direction=str(objective["direction"]),
        estimator={
            "ref": objective.get("estimator_ref"),
            "version": metadata.get("version"),
        },
        evidence_population=f"{population} (checked {checked})" if checked else population,
        hardware=hardware,
        predicted={
            "value": objective.get("value"),
            "lower": objective.get("lower"),
            "upper": objective.get("upper"),
        },
        reason_code=reason_code,
        reason=reason,
    )


def _metric_row(
    metric: dict[str, Any], evaluation: dict[str, Any] | None, hardware: str
) -> dict[str, Any]:
    result = None
    if evaluation is not None:
        result = next(
            (item for item in evaluation["metrics"] if item["metric_id"] == metric["id"]), None
        )
    reason_code, reason = _METRIC_REASONS.get(str(metric.get("kind")), _NOT_MEASURED)
    return _unknown_row(
        subject="contract_metric",
        name=str(metric["id"]),
        unit=str(metric["unit"]),
        direction=str(metric["direction"]),
        estimator={
            "ref": evaluation.get("fixture_version") if evaluation else None,
            "version": evaluation.get("fixture_version") if evaluation else None,
        },
        evidence_population=(
            str(result.get("confidence_interval") or "not recorded")
            if result
            else "no evaluation result for the selected candidate"
        ),
        hardware=hardware,
        predicted={
            "value": result.get("value") if result else None,
            "lower": None,
            "upper": None,
        },
        reason_code=reason_code,
        reason=reason,
    )


def _unknown_row(
    *,
    subject: str,
    name: str,
    unit: str,
    direction: str,
    estimator: dict[str, Any],
    evidence_population: str,
    hardware: str,
    predicted: dict[str, Any],
    reason_code: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "subject": subject,
        "name": name,
        "unit": unit,
        "direction": direction,
        "estimator": estimator,
        "evidence_population": evidence_population,
        "conditions": {"workload": NO_WORKLOAD, "hardware": hardware},
        "predicted": predicted,
        "observed": {
            "status": "unknown",
            "value": None,
            "reason_code": reason_code,
            "reason": reason,
        },
        "absolute_error": None,
        "relative_error": None,
        "interval_covered": None,
        "drift": NO_DRIFT_ASSESSMENT,
        "recalibration_decision": SINGLE_SAMPLE,
    }
