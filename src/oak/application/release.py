# SPDX-License-Identifier: Apache-2.0
"""Signing, approval, dispatch, and runner-result ingestion for compiled plans.

Every method publishes an immutable case successor with an audit event; compiled
canonical artifacts are never edited. Signing and approval use separate key
roles, approvals bind digest/target/action/expiry, and dispatch requires both
under the compiled verification policy. Delivery of a dispatch is never treated
as success — only a verified runner completion advances the case.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from oak.application.context import CommandContext
from oak.application.persistence import build_workspace_mutation
from oak.contracts import SchemaRegistry
from oak.contracts.signatures import signed_payload_bytes, verify_signed_document
from oak.domain import (
    Artifact,
    ArtifactReference,
    OAKError,
    canonical_json_bytes,
    content_digest,
    json_artifact,
)
from oak.domain.audit import audit_event_document
from oak.domain.design_case import DesignCase, DesignCaseStatus
from oak.ports import DispatchTransport, WorkspaceRepository
from oak.ports.signing import SigningPort

CASE_MEDIA_TYPE = "application/vnd.oak.design-case+json"
AUDIT_MEDIA_TYPE = "application/vnd.oak.audit-event+json"
PLAN_SIGNATURE_MEDIA_TYPE = "application/vnd.oak.plan-signature+json"
APPROVAL_MEDIA_TYPE = "application/vnd.oak.approval+json"
ENVELOPE_MEDIA_TYPE = "application/vnd.oak.runner-envelope+json"
RUNNER_MESSAGE_MEDIA_TYPE = "application/vnd.oak.runner-message+json"

APPROVAL_ACTIONS = ("dry_run", "apply", "rollback", "destroy")
READ_ONLY_KINDS = frozenset({"inventory", "validate", "render", "plan", "verify"})
MUTATING_ACTION_BY_KIND = {"apply": "apply", "rollback": "rollback", "destroy": "destroy"}
DEFAULT_APPROVAL_SECONDS = 86_400
LEASE_SECONDS = 300
LEASE_HEARTBEAT_SECONDS = 30


@dataclass(frozen=True, slots=True)
class ReleaseResult:
    case: dict[str, Any]
    document: dict[str, Any]
    duplicate: bool


@dataclass(frozen=True, slots=True)
class IngestResult:
    case: dict[str, Any]
    accepted: tuple[dict[str, Any], ...]
    rejected: tuple[str, ...]


class ReleaseService:
    def __init__(
        self,
        repository: WorkspaceRepository,
        registry: SchemaRegistry,
        signer_loader: Callable[[str], SigningPort],
        transport: DispatchTransport,
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._signer_loader = signer_loader
        self._transport = transport

    def sign_plan(self, context: CommandContext) -> ReleaseResult:
        input_digest = self._request_digest(context, {"action": "sign_plan"})
        context = self._normalized_context(context, "sign-plan", input_digest)
        self._check_context(context)
        self._check_tenant(context)
        duplicate = self._repository.idempotent_case(context.idempotency_key, input_digest)
        if duplicate is not None:
            return ReleaseResult(
                case=duplicate,
                document=self._extension_document(duplicate, "oak.community/plan_signature_ref"),
                duplicate=True,
            )
        current_document = self._require_case()
        current = DesignCase.from_document(current_document)
        if current.status is not DesignCaseStatus.BUNDLE_COMPILED:
            raise OAKError("OAK-SIGN-STATE", "plan signing requires a compiled bundle")
        plan_ref = self._required_reference(current_document, "runner_plan_ref")
        bundle_ref = self._required_reference(current_document, "deployment_bundle_ref")
        plan = self._repository.read_json_artifact(plan_ref)
        policy_ref = ArtifactReference.from_document(
            plan["supply_chain"]["verification_policy_ref"]
        )
        document: dict[str, Any] = {
            "schema_version": "0.1.0",
            "id": f"plan-signature.{plan_ref.id.removeprefix('runner-plan.')}",
            "version": "0.1.0",
            "case_id": current.id,
            "tenant_id": context.tenant_id,
            "environment": str(plan["target"]["environment"]),
            "plan_ref": plan_ref.to_document(),
            "bundle_ref": bundle_ref.to_document(),
            "verification_policy_ref": policy_ref.to_document(),
            "target_id": str(plan["target"]["id"]),
            "target_fingerprint": str(plan["target"]["fingerprint"]),
            "nonce": _deterministic_nonce("plan-signature", plan_ref.digest, bundle_ref.digest),
            "signed_at": context.occurred_at,
            "extensions": {},
        }
        artifact = self._signed_artifact(
            document,
            role="plan-signer",
            schema="plan-signature.schema.json",
            kind="plan_signature",
            media_type=PLAN_SIGNATURE_MEDIA_TYPE,
        )
        extensions = copy.deepcopy(current.extensions or {})
        extensions["oak.community/plan_signature_ref"] = artifact.reference.to_document()
        successor = current.revise(
            status=DesignCaseStatus.BUNDLE_COMPILED,
            updated_at=context.occurred_at,
            extensions=extensions,
        )
        published = self._publish(
            current=current_document,
            successor=successor,
            event_type="plan_signed",
            context=context,
            input_digest=input_digest,
            artifacts=(artifact,),
        )
        return ReleaseResult(
            case=published,
            document=self._artifact_document(artifact),
            duplicate=False,
        )

    def approve(
        self,
        action: str,
        context: CommandContext,
        *,
        expires_at: str | None = None,
    ) -> ReleaseResult:
        if action not in APPROVAL_ACTIONS:
            raise OAKError("OAK-APPROVAL-ACTION", "approval action is not recognized")
        input_digest = self._request_digest(context, {"action": "approve", "kind": action})
        context = self._normalized_context(context, f"approve-{action}", input_digest)
        self._check_context(context)
        self._check_tenant(context)
        duplicate = self._repository.idempotent_case(context.idempotency_key, input_digest)
        if duplicate is not None:
            return ReleaseResult(case=duplicate, document={}, duplicate=True)
        current_document = self._require_case()
        current = DesignCase.from_document(current_document)
        if current.status not in {
            DesignCaseStatus.BUNDLE_COMPILED,
            DesignCaseStatus.DEPLOYMENT_APPROVED,
        }:
            raise OAKError("OAK-APPROVAL-STATE", "approval requires a compiled bundle")
        self._extension_document(current_document, "oak.community/plan_signature_ref")
        plan_ref = self._required_reference(current_document, "runner_plan_ref")
        bundle_ref = self._required_reference(current_document, "deployment_bundle_ref")
        plan = self._repository.read_json_artifact(plan_ref)
        expiry = expires_at or _add_seconds(context.occurred_at, DEFAULT_APPROVAL_SECONDS)
        if _parse_time(expiry) <= _parse_time(context.occurred_at):
            raise OAKError("OAK-APPROVAL-EXPIRY", "approval expiry must be in the future")
        document: dict[str, Any] = {
            "schema_version": "0.1.0",
            "id": f"approval.{action.replace('_', '-')}.{plan_ref.id.removeprefix('runner-plan.')}",
            "version": "0.1.0",
            "case_id": current.id,
            "tenant_id": context.tenant_id,
            "environment": str(plan["target"]["environment"]),
            "action": action,
            "plan_digest": plan_ref.digest,
            "bundle_digest": bundle_ref.digest,
            "target_id": str(plan["target"]["id"]),
            "target_fingerprint": str(plan["target"]["fingerprint"]),
            "actor": context.actor,
            "nonce": _deterministic_nonce("approval", action, plan_ref.digest, context.actor),
            "issued_at": context.occurred_at,
            "expires_at": expiry,
            "revoked": False,
            "revoked_at": None,
            "revocation_reason": None,
            "extensions": {},
        }
        artifact = self._signed_artifact(
            document,
            role="approver",
            schema="approval.schema.json",
            kind="approval",
            media_type=APPROVAL_MEDIA_TYPE,
        )
        extensions = copy.deepcopy(current.extensions or {})
        approvals = dict(extensions.get("oak.community/approval_refs", {}))
        approvals[action] = artifact.reference.to_document()
        extensions["oak.community/approval_refs"] = approvals
        status = DesignCaseStatus.DEPLOYMENT_APPROVED if action == "apply" else current.status
        successor = current.revise(
            status=status,
            updated_at=context.occurred_at,
            extensions=extensions,
        )
        published = self._publish(
            current=current_document,
            successor=successor,
            event_type="approval_recorded",
            context=context,
            input_digest=input_digest,
            artifacts=(artifact,),
        )
        return ReleaseResult(
            case=published,
            document=self._artifact_document(artifact),
            duplicate=False,
        )

    def revoke_approval(
        self,
        action: str,
        reason: str,
        context: CommandContext,
    ) -> ReleaseResult:
        if action not in APPROVAL_ACTIONS:
            raise OAKError("OAK-APPROVAL-ACTION", "approval action is not recognized")
        if not reason.strip():
            raise OAKError("OAK-REVOCATION-REASON", "revocation requires a reason")
        input_digest = self._request_digest(context, {"action": "revoke", "kind": action})
        context = self._normalized_context(context, f"revoke-{action}", input_digest)
        self._check_context(context)
        self._check_tenant(context)
        duplicate = self._repository.idempotent_case(context.idempotency_key, input_digest)
        if duplicate is not None:
            return ReleaseResult(case=duplicate, document={}, duplicate=True)
        current_document = self._require_case()
        current = DesignCase.from_document(current_document)
        approvals = dict((current.extensions or {}).get("oak.community/approval_refs", {}))
        reference_document = approvals.get(action)
        if not isinstance(reference_document, dict):
            raise OAKError("OAK-APPROVAL-MISSING", "no approval exists for that action")
        reference = ArtifactReference.from_document(reference_document)
        approval = self._repository.read_json_artifact(reference)
        if approval.get("revoked") is True:
            raise OAKError("OAK-APPROVAL-REVOKED", "approval is already revoked")
        revoked = dict(approval)
        revoked.pop("signature", None)
        revoked["version"] = _next_patch(str(approval["version"]))
        revoked["revoked"] = True
        revoked["revoked_at"] = context.occurred_at
        revoked["revocation_reason"] = reason.strip()
        artifact = self._signed_artifact(
            revoked,
            role="approver",
            schema="approval.schema.json",
            kind="approval",
            media_type=APPROVAL_MEDIA_TYPE,
            version=_next_patch(reference.version),
        )
        approvals[action] = artifact.reference.to_document()
        extensions = copy.deepcopy(current.extensions or {})
        extensions["oak.community/approval_refs"] = approvals
        successor = current.revise(
            status=current.status,
            updated_at=context.occurred_at,
            extensions=extensions,
        )
        published = self._publish(
            current=current_document,
            successor=successor,
            event_type="approval_revoked",
            context=context,
            input_digest=input_digest,
            artifacts=(artifact,),
        )
        self._transport.publish_revocation(
            {
                "id": f"revocation.{artifact.reference.id}",
                "approval_id": artifact.reference.id,
                "approval_digest": artifact.reference.digest,
                "action": action,
                "revoked_at": context.occurred_at,
                "reason": reason.strip(),
            }
        )
        return ReleaseResult(
            case=published,
            document=self._artifact_document(artifact),
            duplicate=False,
        )

    def dispatch(
        self,
        requested_kinds: tuple[str, ...],
        context: CommandContext,
    ) -> ReleaseResult:
        kinds = tuple(dict.fromkeys(requested_kinds))
        if not kinds:
            raise OAKError("OAK-DISPATCH-KINDS", "dispatch requires at least one operation kind")
        input_digest = self._request_digest(context, {"action": "dispatch", "kinds": list(kinds)})
        context = self._normalized_context(context, "dispatch", input_digest)
        self._check_context(context)
        self._check_tenant(context)
        duplicate = self._repository.idempotent_case(context.idempotency_key, input_digest)
        if duplicate is not None:
            return ReleaseResult(case=duplicate, document={}, duplicate=True)
        current_document = self._require_case()
        current = DesignCase.from_document(current_document)
        if current.status not in {
            DesignCaseStatus.BUNDLE_COMPILED,
            DesignCaseStatus.DEPLOYMENT_APPROVED,
            DesignCaseStatus.DEPLOYED,
        }:
            raise OAKError("OAK-DISPATCH-STATE", "dispatch requires a compiled bundle")
        plan_ref = self._required_reference(current_document, "runner_plan_ref")
        bundle_ref = self._required_reference(current_document, "deployment_bundle_ref")
        plan = self._repository.read_json_artifact(plan_ref)
        plan_kinds = {str(operation["kind"]) for operation in plan["operations"]}
        unknown = [kind for kind in kinds if kind not in plan_kinds]
        if unknown:
            raise OAKError(
                "OAK-DISPATCH-KINDS", "dispatch requested kinds absent from the compiled plan"
            )
        signature_reference = ArtifactReference.from_document(
            self._extension_document(current_document, "oak.community/plan_signature_ref")
        )
        signature_document = self._repository.read_json_artifact(signature_reference)
        if not verify_signed_document(signature_document):
            raise OAKError("OAK-DISPATCH-SIGNATURE", "plan signature does not verify")
        if signature_document["plan_ref"]["digest"] != plan_ref.digest:
            raise OAKError("OAK-DISPATCH-SIGNATURE", "plan signature binds a different plan")
        approvals = (current.extensions or {}).get("oak.community/approval_refs", {})
        unknown_kinds = [
            kind
            for kind in kinds
            if kind not in MUTATING_ACTION_BY_KIND and kind not in READ_ONLY_KINDS
        ]
        if unknown_kinds:
            # A kind in neither set must not silently inherit the dry-run approval.
            raise OAKError("OAK-DISPATCH-KINDS", "dispatch requested an unclassified kind")
        required_actions = {MUTATING_ACTION_BY_KIND.get(kind, "dry_run") for kind in kinds}
        approval_documents: dict[str, dict[str, Any]] = {}
        approval_references: list[ArtifactReference] = []
        for required in sorted(required_actions):
            reference_document = approvals.get(required)
            if not isinstance(reference_document, dict):
                raise OAKError(
                    "OAK-DISPATCH-APPROVAL", f"dispatch requires a current {required} approval"
                )
            reference = ArtifactReference.from_document(reference_document)
            approval = self._repository.read_json_artifact(reference)
            self._check_approval(approval, plan_ref, bundle_ref, context.occurred_at, required)
            approval_documents[f"approval-{required.replace('_', '-')}"] = approval
            approval_references.append(reference)
        policy_ref = ArtifactReference.from_document(
            plan["supply_chain"]["verification_policy_ref"]
        )
        policy_document = self._artifact_document_for(policy_ref)
        sequence = len(self._repository.manifest()["audit_events"]) + 1
        envelope: dict[str, Any] = {
            "schema_version": "0.1.0",
            "protocol_version": "0.1.0",
            "id": f"dispatch.{current.id.removeprefix('design-case.')}.{sequence}",
            "version": "0.1.0",
            "kind": "dispatch_envelope",
            "case_id": current.id,
            "tenant_id": context.tenant_id,
            "environment": str(plan["target"]["environment"]),
            "plan_ref": plan_ref.to_document(),
            "bundle_ref": bundle_ref.to_document(),
            "verification_policy_ref": policy_ref.to_document(),
            "plan_signature_ref": signature_reference.to_document(),
            "approval_refs": [item.to_document() for item in approval_references],
            "target_id": str(plan["target"]["id"]),
            "target_fingerprint": str(plan["target"]["fingerprint"]),
            "requested_kinds": list(kinds),
            "lease": {
                "lease_id": f"lease.{current.id.removeprefix('design-case.')}.{sequence}",
                "nonce": _deterministic_nonce("lease", plan_ref.digest, context.idempotency_key),
                "issued_at": context.occurred_at,
                "expires_at": _add_seconds(context.occurred_at, LEASE_SECONDS),
                "heartbeat_seconds": LEASE_HEARTBEAT_SECONDS,
            },
            "issued_at": context.occurred_at,
            "extensions": {},
        }
        artifact = self._signed_artifact(
            envelope,
            role="plan-signer",
            schema="runner-envelope.schema.json",
            kind="dispatch_envelope",
            media_type=ENVELOPE_MEDIA_TYPE,
        )
        envelope_document = self._artifact_document(artifact)
        attachments: dict[str, dict[str, Any]] = {
            "plan": plan,
            "bundle": self._repository.read_json_artifact(bundle_ref),
            "verification-policy": policy_document,
            "plan-signature": signature_document,
            **approval_documents,
        }
        extensions = copy.deepcopy(current.extensions or {})
        extensions["oak.community/last_dispatch_ref"] = artifact.reference.to_document()
        successor = current.revise(
            status=current.status,
            updated_at=context.occurred_at,
            extensions=extensions,
        )
        published = self._publish(
            current=current_document,
            successor=successor,
            event_type="plan_dispatched",
            context=context,
            input_digest=input_digest,
            artifacts=(artifact,),
        )
        self._transport.deliver(envelope_document, attachments)
        return ReleaseResult(case=published, document=envelope_document, duplicate=False)

    def ingest_runner_messages(self, context: CommandContext) -> IngestResult:
        self._check_tenant(context)
        current_document = self._require_case()
        accepted: list[dict[str, Any]] = []
        rejected: list[str] = []
        for message in self._transport.read_messages():
            message_id = str(message.get("id", ""))
            try:
                self._registry.validate("runner-message.schema.json", message)
            except Exception:
                rejected.append(message_id or "(unidentified)")
                continue
            if not verify_signed_document(message):
                rejected.append(message_id)
                continue
            if not _key_id_derives_from_key(message.get("signature")):
                rejected.append(message_id)
                continue
            if message["tenant_id"] != context.tenant_id:
                rejected.append(message_id)
                continue
            if not self._is_dispatched_lease(message.get("lease_id")):
                # A completion must reference a lease this control plane issued;
                # self-signed messages cannot invent work that was never dispatched.
                rejected.append(message_id)
                continue
            if message["kind"] in {"completion", "evidence"}:
                accepted.append(message)
            self._transport.acknowledge(message_id)
        result_case = current_document
        for message in accepted:
            result_case = self._record_completion(message, context)
        return IngestResult(
            case=result_case,
            accepted=tuple(accepted),
            rejected=tuple(rejected),
        )

    def _is_dispatched_lease(self, lease_id: Any) -> bool:
        if not isinstance(lease_id, str) or not lease_id:
            return False
        case = self._repository.current_case()
        if case is None:
            return False
        reference = case.get("extensions", {}).get("oak.community/last_dispatch_ref")
        if not isinstance(reference, dict):
            return False
        try:
            envelope = self._repository.read_json_artifact(
                ArtifactReference.from_document(reference)
            )
        except OAKError:
            return False
        return str(envelope.get("lease", {}).get("lease_id")) == lease_id

    def _record_completion(
        self,
        message: dict[str, Any],
        context: CommandContext,
    ) -> dict[str, Any]:
        input_digest = content_digest(canonical_json_bytes(message))
        ingest_context = replace(
            context,
            idempotency_key=f"ingest:{input_digest.removeprefix('sha256:')}",
            correlation_id=str(message["correlation_id"]),
        )
        duplicate = self._repository.idempotent_case(ingest_context.idempotency_key, input_digest)
        if duplicate is not None:
            return duplicate
        current_document = self._require_case()
        current = DesignCase.from_document(current_document)
        ingest_context = replace(ingest_context, expected_version=current.version)
        payload = message.get("payload", {})
        outcome = str(payload.get("outcome", "unknown"))
        applied = bool(payload.get("applied_kinds")) and "apply" in payload.get("applied_kinds", [])
        rolled_back = bool(payload.get("applied_kinds")) and "rollback" in payload.get(
            "applied_kinds", []
        )
        if outcome == "manual_recovery_required":
            event_type = "runner_recovery_required"
            status = current.status
        elif rolled_back and outcome == "succeeded":
            event_type = "runner_rolled_back"
            status = current.status
        else:
            event_type = "runner_completed"
            status = (
                DesignCaseStatus.DEPLOYED
                if applied
                and outcome == "succeeded"
                and current.status is DesignCaseStatus.DEPLOYMENT_APPROVED
                else current.status
            )
        artifact = json_artifact(
            artifact_id=str(message["id"]),
            version="0.1.0",
            kind="runner_message",
            media_type=RUNNER_MESSAGE_MEDIA_TYPE,
            document=message,
        )
        extensions = copy.deepcopy(current.extensions or {})
        results = list(extensions.get("oak.community/runner_result_refs", []))
        results.append(artifact.reference.to_document())
        extensions["oak.community/runner_result_refs"] = results
        successor = current.revise(
            status=status,
            updated_at=ingest_context.occurred_at,
            extensions=extensions,
        )
        return self._publish(
            current=current_document,
            successor=successor,
            event_type=event_type,
            context=ingest_context,
            input_digest=input_digest,
            artifacts=(artifact,),
        )

    def _check_approval(
        self,
        approval: dict[str, Any],
        plan_ref: ArtifactReference,
        bundle_ref: ArtifactReference,
        now: str,
        action: str,
    ) -> None:
        if not verify_signed_document(approval):
            raise OAKError("OAK-DISPATCH-APPROVAL", "approval signature does not verify")
        if approval.get("revoked") is True:
            raise OAKError("OAK-DISPATCH-APPROVAL", "approval has been revoked")
        if approval["action"] != action:
            raise OAKError("OAK-DISPATCH-APPROVAL", "approval action does not match dispatch")
        if approval["plan_digest"] != plan_ref.digest:
            raise OAKError("OAK-DISPATCH-APPROVAL", "approval binds a different plan digest")
        if approval["bundle_digest"] != bundle_ref.digest:
            raise OAKError("OAK-DISPATCH-APPROVAL", "approval binds a different bundle digest")
        if _parse_time(approval["expires_at"]) <= _parse_time(now):
            raise OAKError("OAK-DISPATCH-APPROVAL", "approval has expired")

    def _signed_artifact(
        self,
        document: dict[str, Any],
        *,
        role: str,
        schema: str,
        kind: str,
        media_type: str,
        version: str = "0.1.0",
    ) -> Artifact:
        signer = self._signer_loader(role)
        identity = signer.identity()
        payload = dict(document)
        signature_value = signer.sign(signed_payload_bytes(payload))
        payload["signature"] = {
            "role": identity.role,
            "key_id": identity.key_id,
            "algorithm": identity.algorithm,
            "public_key_base64": identity.public_key_base64,
            "trust_level": identity.trust_level,
            "signature_base64": signature_value,
        }
        self._registry.validate(schema, payload)
        return json_artifact(
            artifact_id=str(payload["id"]),
            version=version,
            kind=kind,
            media_type=media_type,
            document=payload,
        )

    def _publish(
        self,
        *,
        current: dict[str, Any],
        successor: DesignCase,
        event_type: str,
        context: CommandContext,
        input_digest: str,
        artifacts: tuple[Artifact, ...],
    ) -> dict[str, Any]:
        manifest = self._repository.manifest()
        intent_ref = self._required_reference(current, "intent_ref")
        intent = self._repository.read_json_artifact(intent_ref)
        source_value = intent["extensions"].get("oak.community/source_record")
        source_record_ref = (
            ArtifactReference.from_document(source_value)
            if isinstance(source_value, dict)
            else None
        )
        sequence = len(manifest["audit_events"]) + 1
        previous = manifest["audit_events"][-1]["digest"] if manifest["audit_events"] else None
        event_document = audit_event_document(
            sequence=sequence,
            previous_event_digest=previous,
            case_id=successor.id,
            case_version=successor.version,
            event_type=event_type,
            actor=context.actor,
            tenant_id=context.tenant_id,
            interface_origin=context.interface_origin,
            correlation_id=context.correlation_id,
            idempotency_key=context.idempotency_key,
            input_digest=input_digest,
            occurred_at=context.occurred_at,
            intent_ref=intent_ref,
            source_record_ref=source_record_ref,
            extensions={
                "oak.community/artifact_refs": [
                    artifact.reference.to_document() for artifact in artifacts
                ]
            },
        )
        self._registry.validate("audit-event.schema.json", event_document)
        event = json_artifact(
            artifact_id=str(event_document["id"]),
            version=str(sequence),
            kind="audit_event",
            media_type=AUDIT_MEDIA_TYPE,
            document=event_document,
        )
        successor = successor.with_audit_head(event.digest)
        case_document = successor.to_document()
        self._registry.validate("design-case.schema.json", case_document)
        case = json_artifact(
            artifact_id=successor.id,
            version=successor.version,
            kind="design_case",
            media_type=CASE_MEDIA_TYPE,
            document=case_document,
        )
        committed = self._repository.commit(
            build_workspace_mutation(
                workspace_id=str(manifest["id"]),
                expected_case_version=context.expected_version,
                idempotency_key=context.idempotency_key,
                input_digest=input_digest,
                artifacts=(*artifacts, event, case),
                current_case_ref=case.reference,
                event_artifact=event,
                event_document=event_document,
                updated_at=context.occurred_at,
            )
        )
        return committed.case_document

    def _artifact_document_for(self, reference: ArtifactReference) -> dict[str, Any]:
        return self._repository.read_json_artifact(reference)

    def _artifact_document(self, artifact: Artifact) -> dict[str, Any]:
        import json

        return dict(json.loads(artifact.content.decode("utf-8")))

    def _extension_document(self, case: dict[str, Any], key: str) -> dict[str, Any]:
        value = case.get("extensions", {}).get(key)
        if not isinstance(value, dict):
            raise OAKError("OAK-DEPENDENCY-MISSING", f"case is missing required {key}")
        return value

    def _require_case(self) -> dict[str, Any]:
        case = self._repository.current_case()
        if case is None:
            raise OAKError("OAK-CASE-NOT-FOUND", "workspace has no design case")
        return case

    def _check_tenant(self, context: CommandContext) -> None:
        if self._repository.manifest()["tenant_id"] != context.tenant_id:
            raise OAKError("OAK-TENANT-MISMATCH", "workspace tenant does not match command")

    @staticmethod
    def _required_reference(document: dict[str, Any], field: str) -> ArtifactReference:
        value = document.get(field)
        if not isinstance(value, dict):
            raise OAKError("OAK-DEPENDENCY-MISSING", f"required {field} artifact is missing")
        return ArtifactReference.from_document(value)

    @staticmethod
    def _check_context(context: CommandContext) -> None:
        if len(context.idempotency_key) < 16:
            raise OAKError(
                "OAK-IDEMPOTENCY-KEY", "idempotency key must contain at least 16 characters"
            )
        if len(context.correlation_id) < 8:
            raise OAKError(
                "OAK-CORRELATION-ID", "correlation ID must contain at least 8 characters"
            )

    @staticmethod
    def _normalized_context(
        context: CommandContext, operation: str, input_digest: str
    ) -> CommandContext:
        digest_hex = input_digest.removeprefix("sha256:")
        return replace(
            context,
            idempotency_key=(context.idempotency_key or f"{operation}:{digest_hex}"),
            correlation_id=(context.correlation_id or f"correlation:{digest_hex[:24]}"),
        )

    @staticmethod
    def _request_digest(context: CommandContext, input_document: dict[str, Any]) -> str:
        return content_digest(
            canonical_json_bytes(
                {
                    "actor": context.actor,
                    "tenant_id": context.tenant_id,
                    "input": input_document,
                }
            )
        )


def _key_id_derives_from_key(signature: Any) -> bool:
    """Reject a signature block whose key_id is decoupled from its public key."""

    if not isinstance(signature, dict):
        return False
    public_key = signature.get("public_key_base64")
    role = signature.get("role")
    key_id = signature.get("key_id")
    if not isinstance(public_key, str) or not isinstance(role, str):
        return False
    expected = content_digest(
        canonical_json_bytes(
            {"algorithm": "ed25519", "public_key_base64": public_key, "role": role}
        )
    )
    return key_id == expected


def _deterministic_nonce(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _add_seconds(value: str, seconds: int) -> str:
    return (
        (_parse_time(value) + timedelta(seconds=seconds))
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _next_patch(version: str) -> str:
    major, minor, patch = version.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"
