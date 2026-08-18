# SPDX-License-Identifier: Apache-2.0
"""Independent runner-side verification of a dispatched plan.

Every check runs before any target access, in a fixed order, and fails closed.
Nothing is trusted because it arrived from the control plane: digests,
signatures, trust anchors, target binding, lease, approvals, adapters,
parameter schemas, and permission envelopes are all recomputed locally.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from oak.contracts import ContractValidationError, SchemaRegistry
from oak.contracts.signatures import signed_payload_bytes, verify_signature
from oak.domain import OAKError, canonical_json_bytes, content_digest
from oak.domain.runner_adapters import (
    ADAPTER_IDENTITY_BY_ID,
    ALLOWED_KINDS_BY_ADAPTER,
    PARAMETER_SCHEMA_BY_ADAPTER,
)

PROTOCOL_VERSION = "0.1.0"
FORBIDDEN_PARAMETER_KEYS = frozenset({"command", "shell", "executable", "argv"})
MUTATING_KINDS = frozenset({"apply", "rollback", "destroy"})
ACTION_BY_KIND = {"apply": "apply", "rollback": "rollback", "destroy": "destroy"}


class RunnerDenialError(OAKError):
    """A fail-closed verification denial recorded before any target access."""


@dataclass(frozen=True, slots=True)
class TrustAnchors:
    """Pinned control-plane public keys the runner accepts, by role.

    Anchors hold the public key itself, never merely its identifier. Verification
    uses the pinned key; a document's own embedded key and `key_id` are untrusted
    claims and are only ever compared against the pinned material.
    """

    keys_by_role: dict[str, dict[str, str]]

    @classmethod
    def from_directory(cls, trust_directory: Path) -> TrustAnchors:
        anchors: dict[str, dict[str, str]] = {"plan-signer": {}, "approver": {}}
        for role in anchors:
            identity_path = trust_directory / f"{role}.identity.json"
            if not identity_path.is_file():
                continue
            try:
                document = json.loads(identity_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            key_id = document.get("key_id")
            public_key = document.get("public_key_base64")
            if isinstance(key_id, str) and isinstance(public_key, str):
                if key_id != derive_key_id(role, public_key):
                    continue
                anchors[role][key_id] = public_key
        return cls(keys_by_role=anchors)

    def public_key(self, role: str, key_id: str) -> str | None:
        return self.keys_by_role.get(role, {}).get(key_id)

    def key_ids(self, role: str) -> frozenset[str]:
        return frozenset(self.keys_by_role.get(role, {}))


def derive_key_id(role: str, public_key_base64: str) -> str:
    """Reproduce the signer's key identifier from its public material."""

    return content_digest(
        canonical_json_bytes(
            {
                "algorithm": "ed25519",
                "public_key_base64": public_key_base64,
                "role": role,
            }
        )
    )


def _verify_against_anchor(
    document: dict[str, Any],
    anchors: TrustAnchors,
    expected_role: str,
    label: str,
) -> None:
    """Verify a signed document with a pinned key, not the one it carries."""

    signature = document.get("signature")
    if not isinstance(signature, dict):
        raise RunnerDenialError("OAK-RUNNER-SIGNATURE", f"{label} carries no signature block")
    role = signature.get("role")
    key_id = signature.get("key_id")
    claimed_key = signature.get("public_key_base64")
    signature_value = signature.get("signature_base64")
    if (
        not isinstance(role, str)
        or not isinstance(key_id, str)
        or not isinstance(claimed_key, str)
        or not isinstance(signature_value, str)
    ):
        raise RunnerDenialError("OAK-RUNNER-SIGNATURE", f"{label} signature block is malformed")
    _check(
        role == expected_role,
        "OAK-RUNNER-TRUST",
        f"{label} is not signed in the {expected_role} role",
    )
    pinned_key = anchors.public_key(expected_role, key_id)
    _check(
        pinned_key is not None,
        "OAK-RUNNER-TRUST",
        f"{label} names a key that is not a pinned {expected_role} anchor",
    )
    assert pinned_key is not None
    # The embedded key is a claim; it must equal the pinned key, and the key
    # identifier must be reproducible from that material.
    _check(claimed_key == pinned_key, "OAK-RUNNER-TRUST", f"{label} embeds a different public key")
    _check(
        derive_key_id(expected_role, pinned_key) == key_id,
        "OAK-RUNNER-TRUST",
        f"{label} key identifier does not derive from its key",
    )
    _check(
        verify_signature(
            algorithm=str(signature.get("algorithm")),
            public_key_base64=pinned_key,
            message=signed_payload_bytes(document),
            signature_base64=signature_value,
        ),
        "OAK-RUNNER-SIGNATURE",
        f"{label} signature does not verify against the pinned key",
    )


@dataclass(frozen=True, slots=True)
class VerifiedDispatch:
    envelope: dict[str, Any]
    plan: dict[str, Any]
    bundle: dict[str, Any]
    operations_by_kind: dict[str, dict[str, Any]]
    requested_kinds: tuple[str, ...]
    operations: tuple[dict[str, Any], ...]
    """Exactly the operations verification approved, in plan order."""


def verify_dispatch(
    *,
    envelope: dict[str, Any],
    attachments: dict[str, dict[str, Any]],
    registry: SchemaRegistry,
    anchors: TrustAnchors,
    target_document: dict[str, Any],
    revoked_approval_ids: frozenset[str],
    seen_lease_nonces: frozenset[str],
    now: str,
) -> VerifiedDispatch:
    # 1. Protocol and schema support.
    _check(
        envelope.get("protocol_version") == PROTOCOL_VERSION,
        "OAK-RUNNER-PROTOCOL",
        "dispatch protocol version is unsupported",
    )
    _validate(registry, "runner-envelope.schema.json", envelope, "dispatch envelope")
    plan = _attachment(attachments, "plan")
    bundle = _attachment(attachments, "bundle")
    plan_signature = _attachment(attachments, "plan-signature")
    _validate(registry, "runner-plan.schema.json", plan, "runner plan")
    _validate(registry, "deployment-bundle.schema.json", bundle, "deployment bundle")
    _validate(registry, "plan-signature.schema.json", plan_signature, "plan signature")

    # 2. Content digests of every attachment against the envelope references.
    _check_digest(envelope["plan_ref"], plan, "plan")
    _check_digest(envelope["bundle_ref"], bundle, "bundle")
    _check_digest(envelope["plan_signature_ref"], plan_signature, "plan signature")
    policy = _attachment(attachments, "verification-policy")
    _check_digest(envelope["verification_policy_ref"], policy, "verification policy")
    approvals: list[dict[str, Any]] = []
    for reference in envelope["approval_refs"]:
        parts = str(reference.get("id", "")).split(".")
        _check(
            len(parts) > 1 and parts[0] == "approval" and bool(parts[1]),
            "OAK-RUNNER-ATTACHMENT",
            "approval reference identifier is malformed",
        )
        name = "approval-" + parts[1].replace("_", "-")
        approval = _attachment(attachments, name)
        _validate(registry, "approval.schema.json", approval, "approval")
        _check_digest(reference, approval, "approval")
        approvals.append(approval)

    # 3. Signatures verified with pinned anchor keys, never the embedded claim.
    _verify_against_anchor(envelope, anchors, "plan-signer", "dispatch envelope")
    _verify_against_anchor(plan_signature, anchors, "plan-signer", "plan signature")
    _check(
        plan_signature["plan_ref"]["digest"] == envelope["plan_ref"]["digest"],
        "OAK-RUNNER-SIGNATURE",
        "plan signature binds a different plan digest",
    )
    _check(
        plan_signature["bundle_ref"]["digest"] == envelope["bundle_ref"]["digest"],
        "OAK-RUNNER-SIGNATURE",
        "plan signature binds a different bundle digest",
    )
    for approval in approvals:
        _verify_against_anchor(approval, anchors, "approver", "approval")

    # 4. Tenant, environment, target identity, and locally recomputed fingerprint.
    local_fingerprint = content_digest(canonical_json_bytes(target_document))
    for label, document in (("envelope", envelope), ("plan signature", plan_signature)):
        _check(
            document["target_id"] == target_document["id"],
            "OAK-RUNNER-TARGET",
            f"{label} names a different target",
        )
        _check(
            document["target_fingerprint"] == local_fingerprint,
            "OAK-RUNNER-TARGET",
            f"{label} fingerprint does not match this target",
        )
        _check(
            document["tenant_id"] == target_document["tenant_id"],
            "OAK-RUNNER-TENANT",
            f"{label} tenant does not match this target",
        )
        _check(
            document["environment"] == target_document["environment"],
            "OAK-RUNNER-ENVIRONMENT",
            f"{label} environment does not match this target",
        )
    _check(
        plan["target"]["id"] == target_document["id"],
        "OAK-RUNNER-TARGET",
        "plan names a different target",
    )
    _check(
        plan["target"]["fingerprint"] == local_fingerprint,
        "OAK-RUNNER-TARGET",
        "plan fingerprint does not match this target",
    )
    _check(
        str(plan.get("status")) in {"draft", "signed", "approved"},
        "OAK-RUNNER-PLAN-STATE",
        "plan status is not dispatchable",
    )
    _check(
        _parse_time(now) < _parse_time(str(plan["expires_at"])),
        "OAK-RUNNER-PLAN-EXPIRED",
        "plan has expired",
    )

    # 5. Lease validity, nonce replay, and expiry.
    lease = envelope["lease"]
    now_time = _parse_time(now)
    _check(
        _parse_time(lease["issued_at"]) <= now_time, "OAK-RUNNER-LEASE", "lease is not yet valid"
    )
    _check(now_time < _parse_time(lease["expires_at"]), "OAK-RUNNER-LEASE", "lease has expired")
    _check(
        lease["nonce"] not in seen_lease_nonces,
        "OAK-RUNNER-REPLAY",
        "lease nonce was already consumed",
    )
    plan_lease_policy = plan["lease_policy"]
    lease_seconds = (
        _parse_time(lease["expires_at"]) - _parse_time(lease["issued_at"])
    ).total_seconds()
    _check(
        lease_seconds <= plan_lease_policy["maximum_seconds"],
        "OAK-RUNNER-LEASE",
        "lease exceeds the plan lease policy",
    )

    # 6. Separation of duties between signer and approver identities.
    for approval in approvals:
        _check(
            approval["signature"]["key_id"] != envelope["signature"]["key_id"],
            "OAK-RUNNER-SEPARATION",
            "approval and plan signatures share one identity",
        )

    # 7-9. Operations: allowlisted adapters, parameter schemas, permissions.
    # Every operation the runner will execute is verified individually. Operation
    # kinds must be unique so that verification and execution cannot diverge: a
    # duplicate kind would otherwise let an unverified operation run alongside a
    # verified one.
    requested = tuple(envelope["requested_kinds"])
    operations_by_kind: dict[str, dict[str, Any]] = {}
    for operation in plan["operations"]:
        kind_key = str(operation["kind"])
        _check(
            kind_key not in operations_by_kind,
            "OAK-RUNNER-OPERATION",
            "plan contains more than one operation of the same kind",
        )
        operations_by_kind[kind_key] = operation
    approvals_by_action = {approval["action"]: approval for approval in approvals}
    verified_operations: list[dict[str, Any]] = []
    for kind in requested:
        operation = operations_by_kind.get(kind)
        _check(
            operation is not None,
            "OAK-RUNNER-OPERATION",
            f"plan does not contain a {kind} operation",
        )
        assert operation is not None
        verified_operations.append(operation)
        adapter = operation["adapter"]
        identity = ADAPTER_IDENTITY_BY_ID.get(str(adapter["id"]))
        _check(
            identity is not None,
            "OAK-RUNNER-ADAPTER",
            "operation adapter is not in the runner allowlist",
        )
        assert identity is not None
        for field in ("version", "digest", "parameter_schema_digest"):
            _check(
                adapter[field] == identity[field],
                "OAK-RUNNER-ADAPTER",
                f"operation adapter {field} does not match the allowlisted adapter",
            )
        _check(
            kind in ALLOWED_KINDS_BY_ADAPTER[str(adapter["id"])],
            "OAK-RUNNER-ADAPTER",
            "adapter does not allow this operation kind",
        )
        _reject_forbidden_keys(operation["parameters"])
        schema = PARAMETER_SCHEMA_BY_ADAPTER[str(adapter["id"])]
        _check(
            _parameters_valid(schema, operation["parameters"]),
            "OAK-RUNNER-PARAMETERS",
            "operation parameters do not satisfy the schema",
        )
        _check(
            operation["secret_references"] == [],
            "OAK-RUNNER-SECRETS",
            "fixture operations may not carry secret references",
        )
        _check(
            list(operation["secret_references"])
            == list(target_document["secrets"]["allowed_references"]),
            "OAK-RUNNER-SECRETS",
            "operation secret references exceed the target allowance",
        )
        _check(
            operation["permissions"]["network_destinations"] == [],
            "OAK-RUNNER-NETWORK",
            "fixture operations may not name network destinations",
        )
        # 10. Mutating kinds require a current, matching, unrevoked approval.
        if kind in MUTATING_KINDS:
            _check(
                target_document["permissions"].get("mutation_allowed") is True
                and kind in target_document["permissions"]["allowed_operations"],
                "OAK-RUNNER-TARGET-CAPABILITY",
                "target profile does not allow this mutating operation",
            )
            required_approval = approvals_by_action.get(ACTION_BY_KIND[kind])
            _check(
                required_approval is not None,
                "OAK-RUNNER-APPROVAL",
                f"no {kind} approval accompanies the dispatch",
            )
            assert required_approval is not None
            _check_approval(
                required_approval, envelope, local_fingerprint, revoked_approval_ids, now_time
            )
        else:
            required_approval = approvals_by_action.get("dry_run")
            _check(
                required_approval is not None,
                "OAK-RUNNER-APPROVAL",
                "no dry-run approval accompanies the dispatch",
            )
            assert required_approval is not None
            _check_approval(
                required_approval, envelope, local_fingerprint, revoked_approval_ids, now_time
            )

    policy_body = policy.get("body", policy)
    if policy_body.get("requires_signature_before_dispatch") is False:
        raise RunnerDenialError("OAK-RUNNER-POLICY", "verification policy is not acceptable")

    ordered = tuple(
        operation for operation in plan["operations"] if operation in verified_operations
    )
    return VerifiedDispatch(
        envelope=envelope,
        plan=plan,
        bundle=bundle,
        operations_by_kind=operations_by_kind,
        requested_kinds=requested,
        operations=ordered,
    )


def _check_approval(
    approval: dict[str, Any],
    envelope: dict[str, Any],
    local_fingerprint: str,
    revoked_approval_ids: frozenset[str],
    now_time: datetime,
) -> None:
    _check(approval["revoked"] is False, "OAK-RUNNER-APPROVAL", "approval is revoked")
    # The approval must be scoped to the same tenant, environment, and case as
    # the dispatch it accompanies; otherwise an approval issued elsewhere counts.
    for field in ("tenant_id", "environment", "case_id"):
        _check(
            approval[field] == envelope[field],
            "OAK-RUNNER-APPROVAL",
            f"approval {field} does not match the dispatch",
        )
    _check(
        approval["id"] not in revoked_approval_ids,
        "OAK-RUNNER-APPROVAL",
        "approval has a published revocation",
    )
    _check(
        approval["plan_digest"] == envelope["plan_ref"]["digest"],
        "OAK-RUNNER-APPROVAL",
        "approval binds a different plan digest",
    )
    _check(
        approval["bundle_digest"] == envelope["bundle_ref"]["digest"],
        "OAK-RUNNER-APPROVAL",
        "approval binds a different bundle digest",
    )
    _check(
        approval["target_id"] == envelope["target_id"],
        "OAK-RUNNER-APPROVAL",
        "approval names a different target",
    )
    _check(
        approval["target_fingerprint"] == local_fingerprint,
        "OAK-RUNNER-APPROVAL",
        "approval fingerprint does not match this target",
    )
    _check(
        now_time < _parse_time(approval["expires_at"]),
        "OAK-RUNNER-APPROVAL",
        "approval has expired",
    )


def _reject_forbidden_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            _check(
                str(key).casefold() not in FORBIDDEN_PARAMETER_KEYS,
                "OAK-RUNNER-PARAMETERS",
                "parameters contain a forbidden execution field",
            )
            _reject_forbidden_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_forbidden_keys(nested)


def _parameters_valid(schema: dict[str, Any], parameters: dict[str, Any]) -> bool:
    import jsonschema

    try:
        jsonschema.validate(parameters, schema)
    except jsonschema.ValidationError:
        return False
    return True


def _attachment(attachments: dict[str, dict[str, Any]], name: str) -> dict[str, Any]:
    document = attachments.get(name)
    if not isinstance(document, dict):
        raise RunnerDenialError("OAK-RUNNER-ATTACHMENT", f"dispatch is missing the {name} document")
    return document


def _check_digest(reference: dict[str, Any], document: dict[str, Any], label: str) -> None:
    actual = content_digest(canonical_json_bytes(document))
    _check(
        actual == reference["digest"],
        "OAK-RUNNER-DIGEST",
        f"{label} content does not match its referenced digest",
    )


def _validate(registry: SchemaRegistry, schema: str, document: dict[str, Any], label: str) -> None:
    try:
        registry.validate(schema, document)
    except (ContractValidationError, OAKError) as error:
        raise RunnerDenialError("OAK-RUNNER-SCHEMA", f"{label} is not schema-valid") from error


def _check(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise RunnerDenialError(code, message)


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
