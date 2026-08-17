# SPDX-License-Identifier: Apache-2.0
"""Deterministic reference evaluation artifacts."""

from typing import Any

from oak.contracts import SchemaRegistry
from oak.domain import Artifact, ArtifactReference, json_artifact

EVALUATION_RESULT_MEDIA_TYPE = "application/vnd.oak.evaluation-result+json"
FIXTURE_RESULTS = {
    "candidate-00": (1.0, 0.0, 180.0),
    "candidate-01": (0.99, 0.0, 210.0),
    "candidate-03": (0.99, 0.005, 1200.0),
}


def evaluate_candidate(
    candidate: dict[str, Any],
    candidate_ref: ArtifactReference,
    contract: dict[str, Any],
    contract_ref: ArtifactReference,
    registry: SchemaRegistry,
    *,
    executed_at: str,
    executor: str,
) -> Artifact:
    metrics: list[dict[str, Any]] = []
    critical_failures: list[str] = []
    if candidate["status"] != "feasible":
        status = "blocked"
        critical_failures.append("Candidate is infeasible under one or more hard constraints.")
    else:
        values = FIXTURE_RESULTS.get(str(candidate["id"]))
        if values is None:
            status = "blocked"
            critical_failures.append(
                "No deterministic evaluation fixture exists for this candidate."
            )
        else:
            for metric_contract, value in zip(contract["metrics"], values, strict=True):
                result = _metric_result(
                    str(metric_contract["direction"]), value, metric_contract["threshold"]
                )
                metrics.append(
                    {
                        "metric_id": metric_contract["id"],
                        "value": value,
                        "unit": metric_contract["unit"],
                        "threshold": metric_contract["threshold"],
                        "direction": metric_contract["direction"],
                        "result": result,
                        "sample_size": 100,
                        "confidence_interval": (
                            "Deterministic synthetic fixture; no population claim."
                        ),
                    }
                )
            status = "pass" if all(item["result"] == "pass" for item in metrics) else "fail"
    document = {
        "schema_version": "0.4.0",
        "id": f"evaluation-result.{candidate['id']}",
        "version": "0.1.0",
        "candidate_ref": candidate_ref.to_document(),
        "evaluation_contract_ref": contract_ref.to_document(),
        "executed_at": executed_at,
        "executor": executor,
        "fixture_version": "public-manual-qa-evaluation-1.0.0",
        "status": status,
        "metrics": metrics,
        "critical_failures": critical_failures,
        "limitations": [
            "Results are deterministic synthetic fixtures and are not observed production evidence."
        ],
        "evidence_refs": [candidate_ref.to_document(), contract_ref.to_document()],
        "extensions": {},
    }
    registry.validate("evaluation-result.schema.json", document)
    return json_artifact(
        artifact_id=str(document["id"]),
        version=str(document["version"]),
        kind="evaluation_result",
        media_type=EVALUATION_RESULT_MEDIA_TYPE,
        document=document,
    )


def _metric_result(direction: str, value: float, threshold: Any) -> str:
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        return "unknown"
    if direction == "at_least":
        return "pass" if value >= float(threshold) else "fail"
    if direction == "at_most":
        return "pass" if value <= float(threshold) else "fail"
    if direction == "equals":
        return "pass" if value == float(threshold) else "fail"
    return "unknown"
