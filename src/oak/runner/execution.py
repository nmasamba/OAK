# SPDX-License-Identifier: Apache-2.0
"""Runner execution: verified operations with journaling, evidence, and recovery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from oak.contracts import ContractValidationError
from oak.domain import OAKError, canonical_json_bytes, content_digest
from oak.runner.adapters import (
    CommandExecutor,
    ContainerFixtureAdapter,
    collect_inventory,
    default_executor,
)
from oak.runner.journal import RunnerJournal
from oak.runner.verification import MUTATING_KINDS, VerifiedDispatch

REDACTION_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|credential|authorization)"
    r"\s*[=:]\s*\S+"
)
REDACTED = "[redacted]"


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    outcome: str
    applied_kinds: tuple[str, ...]
    evidence: tuple[dict[str, Any], ...]
    journal_digest: str
    detail: str


def execute_dispatch(
    verified: VerifiedDispatch,
    *,
    journal: RunnerJournal,
    target_document: dict[str, Any],
    registry: Any,
    now: str,
    executor: CommandExecutor = default_executor,
    cancellation_requested: bool = False,
) -> ExecutionOutcome:
    """Run the requested kinds in plan order; journal around every side effect."""

    if journal.requires_manual_recovery():
        return ExecutionOutcome(
            outcome="manual_recovery_required",
            applied_kinds=(),
            evidence=(),
            journal_digest=journal.digest(),
            detail="journal requires explicit manual recovery before further work",
        )
    interrupted = journal.incomplete_operation()
    if interrupted is not None:
        journal.append(
            "manual_recovery_required",
            now,
            {"reason": "an interrupted side effect was found on resume", **interrupted},
        )
        return ExecutionOutcome(
            outcome="manual_recovery_required",
            applied_kinds=(),
            evidence=(),
            journal_digest=journal.digest(),
            detail="a previous operation did not complete; inspect the journal",
        )

    journal.append(
        "lease_accepted",
        now,
        {
            "lease_id": verified.envelope["lease"]["lease_id"],
            "envelope_id": verified.envelope["id"],
            "requested_kinds": list(verified.requested_kinds),
        },
    )
    container = ContainerFixtureAdapter(executor)
    evidence: list[dict[str, Any]] = []
    applied: list[str] = []
    policy = verified.plan["evidence_policy"]
    # Execute exactly what verification approved; never re-derive from the plan.
    for operation in verified.operations:
        kind = str(operation["kind"])
        if cancellation_requested:
            journal.append("cancellation_observed", now, {"before_operation": kind})
            return ExecutionOutcome(
                outcome="cancelled",
                applied_kinds=tuple(applied),
                evidence=_bounded(evidence, policy),
                journal_digest=journal.digest(),
                detail="cancellation observed before " + kind,
            )
        entry_type = "rollback_before" if kind == "rollback" else "operation_before"
        journal.append(entry_type, now, {"operation_id": operation["id"], "kind": kind})
        try:
            result = _run_operation(
                kind,
                operation,
                verified,
                target_document,
                registry,
                container,
            )
        except (OAKError, ContractValidationError) as error:
            journal.append(
                "operation_failed",
                now,
                {"operation_id": operation["id"], "kind": kind, "error": str(error)},
            )
            failure_action = str(operation["failure_action"])
            if failure_action == "rollback" and kind in MUTATING_KINDS:
                journal.append("rollback_before", now, {"operation_id": operation["id"]})
                try:
                    container.rollback(dict(operation["parameters"]), 120)
                    journal.append("rollback_after", now, {"operation_id": operation["id"]})
                    outcome = "failed"
                    detail = f"{kind} failed and was rolled back"
                except OAKError:
                    journal.append(
                        "manual_recovery_required",
                        now,
                        {"operation_id": operation["id"], "reason": "rollback failed"},
                    )
                    outcome = "manual_recovery_required"
                    detail = f"{kind} failed and rollback also failed"
            elif failure_action == "manual_recovery":
                journal.append(
                    "manual_recovery_required",
                    now,
                    {"operation_id": operation["id"], "reason": str(error)},
                )
                outcome = "manual_recovery_required"
                detail = f"{kind} failed; manual recovery is required"
            else:
                outcome = "failed"
                detail = f"{kind} failed and blocked the dispatch"
            return ExecutionOutcome(
                outcome=outcome,
                applied_kinds=tuple(applied),
                evidence=_bounded(evidence, policy),
                journal_digest=journal.digest(),
                detail=detail,
            )
        after_type = "rollback_after" if kind == "rollback" else "operation_after"
        journal.append(
            after_type,
            now,
            {"operation_id": operation["id"], "kind": kind, "result_digest": _digest(result)},
        )
        evidence.append({"category": _category(kind), "operation": kind, "content": result})
        applied.append(kind)
    journal.append("completion_recorded", now, {"applied_kinds": applied})
    return ExecutionOutcome(
        outcome="succeeded",
        applied_kinds=tuple(applied),
        evidence=_bounded(evidence, policy),
        journal_digest=journal.digest(),
        detail="all requested operations completed",
    )


def _run_operation(
    kind: str,
    operation: dict[str, Any],
    verified: VerifiedDispatch,
    target_document: dict[str, Any],
    registry: Any,
    container: ContainerFixtureAdapter,
) -> dict[str, Any]:
    parameters = dict(operation["parameters"])
    timeout = int(operation["timeout_seconds"])
    if kind == "inventory":
        inventory = collect_inventory()
        capacity = target_document["capacity"]
        return {
            "capabilities": inventory,
            "declared_capacity_plausible": inventory["storage_gib"] >= 0
            and float(capacity["ram_gib"]) >= 0,
        }
    if kind == "validate":
        registry.validate("deployment-bundle.schema.json", verified.bundle)
        registry.validate("runner-plan.schema.json", verified.plan)
        return {"validated": ["deployment-bundle", "runner-plan"]}
    if kind == "render":
        rendered = canonical_json_bytes(verified.bundle)
        return {"rendered_bytes": len(rendered), "digest": content_digest(rendered)}
    if kind == "plan":
        state = (
            container.verify_present(parameters, timeout)
            if _is_container(operation)
            else {"present": False}
        )
        desired = "present" if "apply" in verified.requested_kinds else "reviewed"
        return {
            "normalized_diff": {
                "resource": parameters.get("container_name", "review-only"),
                "current": "present" if state.get("present") else "absent",
                "desired": desired,
            }
        }
    if kind == "verify":
        expected = operation["expected_state_digest"]
        actual = content_digest(canonical_json_bytes(target_document))
        if expected is not None and actual != expected:
            raise OAKError("OAK-RUNNER-DRIFT", "target state digest drifted during execution")
        return {"verified_state_digest": actual}
    if kind == "apply":
        return container.apply(parameters, timeout)
    if kind == "rollback":
        return container.rollback(parameters, timeout)
    if kind == "destroy":
        return container.destroy(parameters, timeout)
    raise OAKError("OAK-RUNNER-OPERATION", "operation kind is not supported")


def _is_container(operation: dict[str, Any]) -> bool:
    return "container_name" in operation["parameters"]


def _category(kind: str) -> str:
    return {
        "inventory": "inventory",
        "validate": "preflight",
        "render": "status",
        "plan": "plan_diff",
        "verify": "status",
        "apply": "status",
        "rollback": "status",
        "destroy": "status",
    }[kind]


def _bounded(evidence: list[dict[str, Any]], policy: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    allowed = set(policy["allowed_categories"])
    budget = int(policy["maximum_bytes"])
    bounded: list[dict[str, Any]] = []
    for entry in evidence:
        if entry["category"] not in allowed:
            continue
        redacted = _redact(entry)
        size = len(canonical_json_bytes(redacted))
        if size > budget:
            break
        budget -= size
        bounded.append(redacted)
    return tuple(bounded)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED
            if str(key).casefold() in {"credentials", "secrets", "environment"}
            else _redact(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_redact(nested) for nested in value]
    if isinstance(value, str):
        return REDACTION_PATTERN.sub(REDACTED, value)
    return value


def _digest(document: dict[str, Any]) -> str:
    return content_digest(canonical_json_bytes(document))
