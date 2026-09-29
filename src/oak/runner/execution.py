# SPDX-License-Identifier: Apache-2.0
"""Runner execution: verified operations with journaling, evidence, and recovery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from oak.contracts import ContractValidationError
from oak.domain import OAKError, canonical_json_bytes, content_digest
from oak.domain.runner_adapters import CONTAINER_ADAPTER_ID
from oak.runner.adapters import (
    AdapterFailureError,
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
# `scheme://user:password@host` carries a credential in the value itself.
URL_CREDENTIAL_PATTERN = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")
# Redaction by key as well as by value (RR-023): a field *named* like a secret is
# withheld whatever its value looks like, before any adapter output can reach evidence.
REDACTED_KEY_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|apikey|authorization|credential|"
    r"private[_-]?key|connection[_-]?string|dsn|cookie)"
)
REDACTED_KEYS = frozenset({"credentials", "secrets", "environment", "env"})
REDACTED = "[redacted]"


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    outcome: str
    applied_kinds: tuple[str, ...]
    evidence: tuple[dict[str, Any], ...]
    journal_digest: str
    detail: str
    failed_kind: str | None = None


def execute_dispatch(
    verified: VerifiedDispatch,
    *,
    journal: RunnerJournal,
    target_document: dict[str, Any],
    registry: Any,
    now: str,
    executor: CommandExecutor = default_executor,
    cancellation_requested: bool = False,
    adapter: ContainerFixtureAdapter | None = None,
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
    container = adapter or ContainerFixtureAdapter(executor)
    evidence: list[dict[str, Any]] = []
    applied: list[str] = []
    policy = verified.plan["evidence_policy"]
    lease_deadline = _parse_time(str(verified.envelope["lease"]["expires_at"]))
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
        before: dict[str, Any] = {"operation_id": operation["id"], "kind": kind}
        if _is_container(operation):
            # Name every resource the side effect may touch before it happens, so a crash
            # mid-operation leaves the exact list an operator has to inspect.
            before["resources"] = _container_names(operation)
        journal.append(entry_type, now, before)
        try:
            items = _run_operation(
                kind,
                operation,
                verified,
                target_document,
                registry,
                container,
                lease_deadline,
            )
        except (OAKError, ContractValidationError) as error:
            journal.append(
                "operation_failed",
                now,
                {"operation_id": operation["id"], "kind": kind, "error": str(error)},
            )
            if isinstance(error, AdapterFailureError):
                evidence.extend(error.evidence)
            failure_action = str(operation["failure_action"])
            if failure_action == "rollback" and kind in MUTATING_KINDS:
                # Compensate for exactly what this operation created; a container that
                # was already installed before it is not this failure's to remove.
                created = error.created if isinstance(error, AdapterFailureError) else ()
                journal.append(
                    "rollback_before",
                    now,
                    {"operation_id": operation["id"], "resources": list(created)},
                )
                try:
                    evidence.append(
                        container.compensate(dict(operation["parameters"]), created, 120)
                    )
                    journal.append("rollback_after", now, {"operation_id": operation["id"]})
                    outcome = "failed"
                    detail = f"{kind} failed and was rolled back"
                except OAKError as rollback_error:
                    if isinstance(rollback_error, AdapterFailureError):
                        evidence.extend(rollback_error.evidence)
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
                failed_kind=kind,
            )
        after_type = "rollback_after" if kind == "rollback" else "operation_after"
        journal.append(
            after_type,
            now,
            {
                "operation_id": operation["id"],
                "kind": kind,
                "result_digest": _digest({"evidence": list(items)}),
            },
        )
        evidence.extend(items)
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
    lease_deadline: datetime,
) -> tuple[dict[str, Any], ...]:
    """Run one verified operation and return its typed evidence items."""

    parameters = dict(operation["parameters"])
    timeout = int(operation["timeout_seconds"])
    if kind == "apply":
        return container.apply(parameters, timeout, deadline=lease_deadline)
    if kind == "rollback":
        return (container.rollback(parameters, timeout),)
    if kind == "destroy":
        return (container.destroy(parameters, timeout),)
    result = _read_only_result(kind, operation, verified, target_document, registry, container)
    return ({"category": _category(kind), "operation": kind, "content": result},)


def _read_only_result(
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
                "resource": ", ".join(_container_names(operation)) or "review-only",
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
    raise OAKError("OAK-RUNNER-OPERATION", "operation kind is not supported")


def _is_container(operation: dict[str, Any]) -> bool:
    return bool(operation["adapter"]["id"] == CONTAINER_ADAPTER_ID)


def _container_names(operation: dict[str, Any]) -> list[str]:
    entries = operation["parameters"].get("containers")
    if not isinstance(entries, list):
        return []
    return [str(entry.get("container_name")) for entry in entries if isinstance(entry, dict)]


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _category(kind: str) -> str:
    return {
        "inventory": "inventory",
        "validate": "preflight",
        "render": "status",
        "plan": "plan_diff",
        "verify": "status",
    }[kind]


def _bounded(evidence: list[dict[str, Any]], policy: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    allowed = set(policy["allowed_categories"])
    budget = int(policy["maximum_bytes"])
    extra_keys = frozenset(str(key).casefold() for key in policy.get("redact_fields", []))
    bounded: list[dict[str, Any]] = []
    for entry in evidence:
        if entry["category"] not in allowed:
            continue
        redacted = _redact(entry, extra_keys)
        size = len(canonical_json_bytes(redacted))
        if size > budget:
            break
        budget -= size
        bounded.append(redacted)
    return tuple(bounded)


def _redact(value: Any, extra_keys: frozenset[str] = frozenset()) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED if _redacted_key(str(key), extra_keys) else _redact(nested, extra_keys)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_redact(nested, extra_keys) for nested in value]
    if isinstance(value, str):
        return URL_CREDENTIAL_PATTERN.sub(rf"\1{REDACTED}@", REDACTION_PATTERN.sub(REDACTED, value))
    return value


def _redacted_key(key: str, extra_keys: frozenset[str]) -> bool:
    folded = key.casefold()
    return (
        folded in REDACTED_KEYS
        or folded in extra_keys
        or REDACTED_KEY_PATTERN.search(folded) is not None
    )


def _digest(document: dict[str, Any]) -> str:
    return content_digest(canonical_json_bytes(document))
