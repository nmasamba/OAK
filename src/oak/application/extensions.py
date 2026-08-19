# SPDX-License-Identifier: Apache-2.0
"""Extension supply-chain lifecycle: quarantine, verification, explicit activation.

Every installed extension stays quarantined until schema, payload digest,
compatibility, licence, pinned-anchor steward signature, and embedded tests
all pass and an explicit local actor activates it. Extension payloads are
governed data; nothing here imports, executes, or downloads code.
"""

import base64
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from oak.contracts import (
    ContractValidationError,
    SchemaRegistry,
    load_yaml_document,
)
from oak.contracts.signatures import signed_payload_bytes, verify_signature
from oak.domain import OAKError, canonical_json_bytes, content_digest
from oak.domain.extension_sdk import (
    INTERFACE_BY_CLASS,
    RENDERER_IDENTITY_BY_ID,
    capability_document,
)
from oak.domain.policy_rules import pack_effective_window
from oak.domain.runner_adapters import ADAPTER_IDENTITY_BY_ID
from oak.ports.extensions import ExtensionEntry, ExtensionStorePort
from oak.ports.policy import PolicyEnginePort
from oak.ports.signing import SigningPort

STEWARD_ROLE = "extension-steward"


@dataclass(frozen=True, slots=True)
class VerificationReport:
    entry: ExtensionEntry
    checks: tuple[dict[str, Any], ...]
    passed: bool

    def to_document(self) -> dict[str, Any]:
        return {
            "extension_id": self.entry.extension_id,
            "version": self.entry.version,
            "state": self.entry.state,
            "passed": self.passed,
            "checks": list(self.checks),
        }


class ExtensionService:
    """Orchestrate the governed extension lifecycle over the store port."""

    def __init__(
        self,
        registry: SchemaRegistry,
        store: ExtensionStorePort,
        engine_loader: Callable[[], PolicyEnginePort],
        anchor_loader: Callable[[], dict[str, str]],
        oak_version: str,
    ) -> None:
        self._registry = registry
        self._store = store
        self._engine_loader = engine_loader
        self._anchor_loader = anchor_loader
        self._oak_version = oak_version

    def install(self, source: Path) -> ExtensionEntry:
        return self._store.install(source)

    def list_extensions(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "id": entry.extension_id,
                "version": entry.version,
                "state": entry.state,
                "extension_class": str(entry.manifest["extension_class"]),
                "name": str(entry.manifest["name"]),
            }
            for entry in self._store.list_entries()
        )

    def capabilities(self) -> dict[str, Any]:
        return capability_document()

    def verify(
        self, extension_id: str, version: str | None, *, occurred_at: str
    ) -> VerificationReport:
        entry = self._store.entry(extension_id, version)
        report = self._verify_entry(entry, occurred_at=occurred_at)
        self._store.store_report(entry, report.to_document())
        return report

    def activate(
        self,
        extension_id: str,
        version: str | None,
        *,
        actor: str,
        occurred_at: str,
    ) -> dict[str, Any]:
        entry = self._store.entry(extension_id, version)
        report = self._verify_entry(entry, occurred_at=occurred_at)
        self._store.store_report(entry, report.to_document())
        if not report.passed:
            failed = sorted(check["id"] for check in report.checks if check["result"] != "pass")
            raise OAKError(
                "OAK-EXTENSION-QUARANTINED",
                f"extension failed verification and stays quarantined: {', '.join(failed)}",
            )
        activation = {
            "schema_version": "0.1.0",
            "id": f"extension-activation.{entry.extension_id}.{entry.version}",
            "version": "0.1.0",
            "extension_id": entry.extension_id,
            "extension_version": entry.version,
            "manifest_digest": content_digest(canonical_json_bytes(entry.manifest)),
            "activated_at": occurred_at,
            "activated_by": actor,
            "verification": {"checks": list(report.checks)},
            "extensions": {},
        }
        self._registry.validate("extension-activation.schema.json", activation)
        self._store.activate(entry, activation)
        return activation

    def deactivate(self, extension_id: str, version: str | None) -> ExtensionEntry:
        return self._store.deactivate(extension_id, version)

    def sign_source(self, source: Path, signer: SigningPort) -> dict[str, Any]:
        """Recompute payload digests and sign the manifest with the steward key."""

        identity = signer.identity()
        if identity.role != STEWARD_ROLE:
            raise OAKError("OAK-EXTENSION-SIGNER", "extensions are signed by the steward role")
        manifest = self._store.read_source_manifest(source)
        manifest.pop("signature", None)
        files = self._store.source_payload_listing(source)
        manifest["payload"] = {
            "files": files,
            "payload_digest": content_digest(canonical_json_bytes({"files": files})),
        }
        manifest["supply_chain"]["signature_status"] = "present_unverified"
        signature = {
            "role": identity.role,
            "key_id": identity.key_id,
            "algorithm": identity.algorithm,
            "public_key_base64": identity.public_key_base64,
            "trust_level": identity.trust_level,
            "signature_base64": signer.sign(signed_payload_bytes(manifest)),
        }
        manifest["signature"] = signature
        self._registry.validate("extension-manifest.schema.json", manifest)
        self._store.write_source_manifest(source, manifest)
        return manifest

    def _verify_entry(self, entry: ExtensionEntry, *, occurred_at: str) -> VerificationReport:
        checks: list[dict[str, Any]] = []

        def record(check_id: str, passed: bool, detail: str) -> bool:
            checks.append(
                {"id": check_id, "result": "pass" if passed else "fail", "detail": detail}
            )
            return passed

        manifest = entry.manifest
        try:
            self._registry.validate("extension-manifest.schema.json", manifest)
            record("manifest-schema", True, "Manifest validates against the extension schema.")
        except ContractValidationError as error:
            record("manifest-schema", False, f"Manifest is schema-invalid: {error.reason}")
            return VerificationReport(entry=entry, checks=tuple(checks), passed=False)

        self._check_payload_digest(entry, record)
        self._check_compatibility(manifest, record)
        record(
            "licence",
            bool(str(manifest["licence"]["spdx_expression"]).strip()),
            "Extension declares an SPDX licence expression.",
        )
        self._check_signature(manifest, record)
        self._check_payload_content(entry, record, occurred_at=occurred_at)
        passed = all(check["result"] == "pass" for check in checks)
        return VerificationReport(entry=entry, checks=tuple(checks), passed=passed)

    def _check_payload_digest(
        self, entry: ExtensionEntry, record: Callable[[str, bool, str], bool]
    ) -> None:
        declared = list(entry.manifest["payload"]["files"])
        declared_paths = [str(item["path"]) for item in declared]
        actual = list(self._store.payload_names(entry))
        if sorted(declared_paths) != actual:
            record(
                "payload-digest",
                False,
                "Declared payload files do not match the files on disk.",
            )
            return
        for item in declared:
            content = self._store.payload_bytes(entry, str(item["path"]))
            if content_digest(content) != str(item["digest"]):
                record(
                    "payload-digest",
                    False,
                    f"Payload file {item['path']} does not match its declared digest.",
                )
                return
        expected = content_digest(
            canonical_json_bytes({"files": sorted(declared, key=lambda item: str(item["path"]))})
        )
        if expected != str(entry.manifest["payload"]["payload_digest"]):
            record(
                "payload-digest", False, "The aggregate payload digest does not match the files."
            )
            return
        record(
            "payload-digest",
            True,
            "Every payload file digest and the aggregate payload digest match.",
        )

    def _check_compatibility(
        self, manifest: dict[str, Any], record: Callable[[str, bool, str], bool]
    ) -> None:
        extension_class = str(manifest["extension_class"])
        interface = INTERFACE_BY_CLASS.get(extension_class)
        if interface is None:
            record("compatibility", False, "Extension class has no registered SDK interface.")
            return
        if str(manifest["sdk_interface_version"]) != interface.interface_version:
            record(
                "compatibility",
                False,
                f"SDK interface {manifest['sdk_interface_version']} is not the supported "
                f"{interface.interface_version} for {extension_class}.",
            )
            return
        compatibility = manifest["compatibility"]
        current = _version_tuple(self._oak_version)
        minimum = _version_tuple(str(compatibility["minimum_oak_version"]))
        maximum_value = compatibility["maximum_oak_version"]
        if current < minimum:
            record(
                "compatibility",
                False,
                f"OAK {self._oak_version} is older than the declared minimum "
                f"{compatibility['minimum_oak_version']}.",
            )
            return
        if maximum_value is not None and current > _version_tuple(str(maximum_value)):
            record(
                "compatibility",
                False,
                f"OAK {self._oak_version} is newer than the declared maximum {maximum_value}.",
            )
            return
        record(
            "compatibility",
            True,
            f"SDK interface {interface.interface_version} and OAK {self._oak_version} satisfy "
            "the declared range.",
        )

    def _check_signature(
        self, manifest: dict[str, Any], record: Callable[[str, bool, str], bool]
    ) -> None:
        signature = manifest.get("signature")
        if not isinstance(signature, dict):
            record("signature", False, "Extension manifest is unsigned.")
            return
        if str(signature.get("role")) != STEWARD_ROLE:
            record("signature", False, "Extension signature does not use the steward role.")
            return
        anchors = self._anchor_loader()
        key_id = str(signature.get("key_id"))
        pinned_key = anchors.get(key_id)
        if pinned_key is None:
            record("signature", False, "Extension signature key is not a pinned trust anchor.")
            return
        if str(signature.get("public_key_base64")) != pinned_key:
            record(
                "signature",
                False,
                "Embedded public key does not match the pinned trust anchor.",
            )
            return
        derived = content_digest(
            canonical_json_bytes(
                {
                    "algorithm": "ed25519",
                    "public_key_base64": pinned_key,
                    "role": STEWARD_ROLE,
                }
            )
        )
        if derived != key_id:
            record("signature", False, "Signature key identifier does not derive from its key.")
            return
        try:
            base64.b64decode(pinned_key, validate=True)
        except ValueError:
            record("signature", False, "Pinned trust anchor key is unreadable.")
            return
        verified = verify_signature(
            algorithm=str(signature.get("algorithm")),
            public_key_base64=pinned_key,
            message=signed_payload_bytes(manifest),
            signature_base64=str(signature.get("signature_base64")),
        )
        record(
            "signature",
            verified,
            "Steward signature verified against the pinned local trust anchor."
            if verified
            else "Steward signature failed verification against the pinned anchor.",
        )

    def _check_payload_content(
        self,
        entry: ExtensionEntry,
        record: Callable[[str, bool, str], bool],
        *,
        occurred_at: str,
    ) -> None:
        extension_class = str(entry.manifest["extension_class"])
        names = self._store.payload_names(entry)
        try:
            if extension_class == "policy-pack":
                self._check_policy_pack_payload(entry, names, record, occurred_at=occurred_at)
            elif extension_class == "deployment-adapter":
                self._check_binding_payload(
                    entry,
                    names,
                    record,
                    key="renderer_id",
                    registry=RENDERER_IDENTITY_BY_ID,
                    label="deployment renderer",
                )
            elif extension_class == "runner-adapter":
                self._check_binding_payload(
                    entry,
                    names,
                    record,
                    key="runner_adapter_id",
                    registry=ADAPTER_IDENTITY_BY_ID,
                    label="runner adapter",
                )
            elif extension_class in {"component-manifest", "architecture-pattern"}:
                schema = f"{extension_class}.schema.json"
                for name in names:
                    document = load_yaml_document(
                        self._store.payload_bytes(entry, name).decode("utf-8")
                    )
                    self._registry.validate(schema, document)
                record(
                    "payload-content",
                    True,
                    f"All {len(names)} payload document(s) validate against {schema}.",
                )
            else:  # pragma: no cover - schema restricts classes
                record("payload-content", False, "Extension class is not supported.")
        except (OAKError, ContractValidationError, ValueError) as error:
            record("payload-content", False, f"Payload content failed validation: {error}")

    def _check_policy_pack_payload(
        self,
        entry: ExtensionEntry,
        names: tuple[str, ...],
        record: Callable[[str, bool, str], bool],
        *,
        occurred_at: str,
    ) -> None:
        if names != ("pack.yaml",):
            record("payload-content", False, "A policy-pack extension carries exactly pack.yaml.")
            return
        pack = load_yaml_document(self._store.payload_bytes(entry, "pack.yaml").decode("utf-8"))
        self._registry.validate("policy-pack.schema.json", pack)
        effective, reason = pack_effective_window(pack, at=occurred_at)
        if not effective:
            record("payload-content", False, f"Policy pack is not usable now: {reason}.")
            return
        engine = self._engine_loader()
        for test in pack["tests"]:
            evaluation = engine.evaluate(pack, dict(test["subject"]))
            expected_reasons = sorted(str(code) for code in test["expected_reason_codes"])
            if evaluation.outcome != str(test["expected_outcome"]) or (
                list(evaluation.reasons) != expected_reasons
            ):
                record(
                    "payload-content",
                    False,
                    f"Embedded pack test failed: {test['name']} produced "
                    f"{evaluation.outcome} {list(evaluation.reasons)}.",
                )
                return
        record(
            "payload-content",
            True,
            f"Policy pack validates and all {len(pack['tests'])} embedded tests passed "
            "under the built-in engine.",
        )

    def _check_binding_payload(
        self,
        entry: ExtensionEntry,
        names: tuple[str, ...],
        record: Callable[[str, bool, str], bool],
        *,
        key: str,
        registry: dict[str, dict[str, str]],
        label: str,
    ) -> None:
        if names != ("adapter.yaml",):
            record(
                "payload-content",
                False,
                f"A {label} extension carries exactly adapter.yaml.",
            )
            return
        binding = load_yaml_document(
            self._store.payload_bytes(entry, "adapter.yaml").decode("utf-8")
        )
        identifier = binding.get(key)
        if not isinstance(identifier, str) or identifier not in registry:
            record(
                "payload-content",
                False,
                f"adapter.yaml must bind {key} to a registered in-tree {label}.",
            )
            return
        allowed_keys = {key, "configuration", "notes"}
        unexpected = sorted(set(binding) - allowed_keys)
        if unexpected:
            record(
                "payload-content",
                False,
                f"adapter.yaml contains unsupported keys: {', '.join(unexpected)}.",
            )
            return
        record(
            "payload-content",
            True,
            f"adapter.yaml binds the registered {label} {identifier}; extensions never "
            "carry executable code.",
        )


def _version_tuple(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value)
    if not numbers:
        raise OAKError("OAK-EXTENSION-VERSION", "version has no comparable numbers")
    return tuple(int(number) for number in numbers)
