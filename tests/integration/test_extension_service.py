# SPDX-License-Identifier: Apache-2.0
"""Extension supply chain: quarantine by default, explicit verified activation."""

import copy
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from oak.adapters.extensions import LocalExtensionStore
from oak.adapters.policies import BuiltinPolicyEngine, LocalPolicyPackStore
from oak.adapters.signing import LocalEd25519Signer, initialize_trust_directory
from oak.application.extensions import ExtensionService
from oak.contracts import SchemaRegistry
from oak.domain import OAKError, canonical_json_bytes, content_digest
from tests.runner_support import ROOT

pytestmark = pytest.mark.integration

NOW = "2026-08-19T12:00:00Z"
OAK_VERSION = "0.6.0.dev6"


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.from_directory(ROOT / "schemas")


class Harness:
    def __init__(self, tmp_path: Path, registry: SchemaRegistry) -> None:
        self.registry = registry
        self.trust = tmp_path / "trust"
        initialize_trust_directory(self.trust)
        self.store_root = tmp_path / "extensions"
        self.store = LocalExtensionStore(self.store_root, registry)
        self.service = ExtensionService(
            registry,
            self.store,
            BuiltinPolicyEngine,
            self._anchors,
            OAK_VERSION,
        )

    def _anchors(self) -> dict[str, str]:
        import json

        path = self.trust / "extension-steward.identity.json"
        if not path.is_file():
            return {}
        document = json.loads(path.read_text(encoding="utf-8"))
        return {str(document["key_id"]): str(document["public_key_base64"])}

    def steward(self) -> LocalEd25519Signer:
        return LocalEd25519Signer.load(self.trust, "extension-steward")


@pytest.fixture()
def harness(tmp_path: Path, registry: SchemaRegistry) -> Harness:
    return Harness(tmp_path, registry)


def _pack_extension_source(tmp_path: Path, *, mutate_pack: dict[str, Any] | None = None) -> Path:
    source = tmp_path / "source"
    source.mkdir(parents=True, exist_ok=True)
    pack = yaml.safe_load((ROOT / "policy-packs" / "community-baseline.yaml").read_text())
    pack["id"] = "pack.contributed-baseline"
    if mutate_pack:
        pack.update(copy.deepcopy(mutate_pack))
    (source / "pack.yaml").write_text(yaml.safe_dump(pack, sort_keys=True), encoding="utf-8")
    manifest = {
        "schema_version": "0.1.0",
        "id": "extension.contributed-baseline",
        "version": "1.0.0",
        "extension_class": "policy-pack",
        "name": "Contributed baseline policy pack",
        "description": "A contributor-authored copy of the fixture baseline pack.",
        "owner": "contributor",
        "sdk_interface_version": "1.0.0",
        "compatibility": {"minimum_oak_version": "0.6.0", "maximum_oak_version": None},
        "payload": {
            "files": [
                {
                    "path": "pack.yaml",
                    "digest": f"sha256:{'0' * 64}",
                    "media_type": "application/yaml",
                }
            ],
            "payload_digest": f"sha256:{'0' * 64}",
        },
        "licence": {"spdx_expression": "Apache-2.0", "terms_url": None},
        "supply_chain": {
            "signature_status": "absent",
            "provenance_status": "absent",
            "sbom_status": "absent",
        },
        "extensions": {},
    }
    (source / "extension.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8"
    )
    return source


def test_contributor_journey_sign_install_verify_activate(harness: Harness, tmp_path: Path) -> None:
    source = _pack_extension_source(tmp_path)
    signed = harness.service.sign_source(source, harness.steward())
    assert signed["signature"]["role"] == "extension-steward"
    entry = harness.service.install(source)
    assert entry.state == "quarantined"

    report = harness.service.verify("extension.contributed-baseline", None, occurred_at=NOW)
    assert report.passed, report.to_document()
    assert {check["id"] for check in report.checks} == {
        "manifest-schema",
        "payload-digest",
        "compatibility",
        "licence",
        "signature",
        "payload-content",
    }

    activation = harness.service.activate(
        "extension.contributed-baseline", None, actor="local-user", occurred_at=NOW
    )
    assert activation["activated_by"] == "local-user"
    listed = harness.service.list_extensions()
    assert listed[0]["state"] == "active"

    pack_store = LocalPolicyPackStore((harness.store_root / "active-packs",), harness.registry)
    contributed = pack_store.load("pack.contributed-baseline")
    assert contributed["id"] == "pack.contributed-baseline"

    deactivated = harness.service.deactivate("extension.contributed-baseline", None)
    assert deactivated.state == "quarantined"
    with pytest.raises(OAKError) as missing:
        pack_store.load("pack.contributed-baseline")
    assert missing.value.code == "OAK-POLICY-PACK-NOT-FOUND"


def test_unsigned_extension_stays_quarantined(harness: Harness, tmp_path: Path) -> None:
    source = _pack_extension_source(tmp_path)
    signed = harness.service.sign_source(source, harness.steward())
    manifest = dict(signed)
    manifest.pop("signature")
    manifest["supply_chain"] = dict(manifest["supply_chain"], signature_status="absent")
    (source / "extension.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8"
    )
    harness.service.install(source)
    with pytest.raises(OAKError) as denial:
        harness.service.activate(
            "extension.contributed-baseline", None, actor="local-user", occurred_at=NOW
        )
    assert denial.value.code == "OAK-EXTENSION-QUARANTINED"
    assert "signature" in denial.value.message
    assert harness.service.list_extensions()[0]["state"] == "quarantined"


def test_wrong_key_signature_is_not_a_pinned_anchor(harness: Harness, tmp_path: Path) -> None:
    source = _pack_extension_source(tmp_path)
    forged_trust = tmp_path / "forged-trust"
    initialize_trust_directory(forged_trust)
    forged_signer = LocalEd25519Signer.load(forged_trust, "extension-steward")
    harness.service.sign_source(source, forged_signer)
    harness.service.install(source)
    report = harness.service.verify("extension.contributed-baseline", None, occurred_at=NOW)
    signature = next(check for check in report.checks if check["id"] == "signature")
    assert signature["result"] == "fail"
    assert "pinned" in signature["detail"]


def test_tampered_payload_fails_digest_verification(harness: Harness, tmp_path: Path) -> None:
    source = _pack_extension_source(tmp_path)
    harness.service.sign_source(source, harness.steward())
    pack = yaml.safe_load((source / "pack.yaml").read_text())
    pack["description"] = "Tampered after signing."
    (source / "pack.yaml").write_text(yaml.safe_dump(pack, sort_keys=True), encoding="utf-8")
    harness.service.install(source)
    report = harness.service.verify("extension.contributed-baseline", None, occurred_at=NOW)
    digest_check = next(check for check in report.checks if check["id"] == "payload-digest")
    assert digest_check["result"] == "fail"
    with pytest.raises(OAKError) as denial:
        harness.service.activate(
            "extension.contributed-baseline", None, actor="local-user", occurred_at=NOW
        )
    assert denial.value.code == "OAK-EXTENSION-QUARANTINED"


def test_incompatible_sdk_or_oak_version_fails(harness: Harness, tmp_path: Path) -> None:
    source = _pack_extension_source(tmp_path)
    manifest = yaml.safe_load((source / "extension.yaml").read_text())
    manifest["sdk_interface_version"] = "9.0.0"
    (source / "extension.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8"
    )
    harness.service.sign_source(source, harness.steward())
    harness.service.install(source)
    report = harness.service.verify("extension.contributed-baseline", None, occurred_at=NOW)
    compatibility = next(check for check in report.checks if check["id"] == "compatibility")
    assert compatibility["result"] == "fail"

    newer = _pack_extension_source(tmp_path / "newer")
    manifest = yaml.safe_load((newer / "extension.yaml").read_text())
    manifest["id"] = "extension.future-only"
    manifest["compatibility"] = {
        "minimum_oak_version": "9.9.9",
        "maximum_oak_version": None,
    }
    (newer / "extension.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8"
    )
    harness.service.sign_source(newer, harness.steward())
    harness.service.install(newer)
    future = harness.service.verify("extension.future-only", None, occurred_at=NOW)
    compatibility = next(check for check in future.checks if check["id"] == "compatibility")
    assert compatibility["result"] == "fail"


def test_poisoned_pack_test_expectations_fail(harness: Harness, tmp_path: Path) -> None:
    source = _pack_extension_source(
        tmp_path,
        mutate_pack={
            "tests": [
                {
                    "name": "poisoned expectation",
                    "subject": {
                        "candidate": {"hard_requirements": ["no_runtime_egress"]},
                        "intent_spec": {
                            "data": {"classifications": ["public", "internal"]},
                            "regulatory_nexus": {"eu_nexus": "none"},
                        },
                    },
                    "expected_outcome": "allow",
                    "expected_reason_codes": ["POL-NO-EGRESS-OK"],
                }
            ]
        },
    )
    harness.service.sign_source(source, harness.steward())
    harness.service.install(source)
    report = harness.service.verify("extension.contributed-baseline", None, occurred_at=NOW)
    content = next(check for check in report.checks if check["id"] == "payload-content")
    assert content["result"] == "fail"
    assert "Embedded pack test failed" in content["detail"]


def test_expired_pack_payload_cannot_activate(harness: Harness, tmp_path: Path) -> None:
    source = _pack_extension_source(tmp_path, mutate_pack={"expires_at": "2026-01-01T00:00:00Z"})
    harness.service.sign_source(source, harness.steward())
    harness.service.install(source)
    report = harness.service.verify("extension.contributed-baseline", None, occurred_at=NOW)
    content = next(check for check in report.checks if check["id"] == "payload-content")
    assert content["result"] == "fail"
    assert "OAK-POLICY-PACK-EXPIRED" in content["detail"]


def test_deployment_adapter_extension_binds_registered_renderer(
    harness: Harness, tmp_path: Path
) -> None:
    source = tmp_path / "adapter-source"
    source.mkdir()
    (source / "adapter.yaml").write_text(
        yaml.safe_dump(
            {"renderer_id": "renderer.helm-kubernetes", "configuration": {"namespace": "oak"}},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "0.1.0",
        "id": "extension.helm-binding",
        "version": "1.0.0",
        "extension_class": "deployment-adapter",
        "name": "Helm renderer binding",
        "description": "Explicit local configuration for the in-tree Kubernetes renderer.",
        "owner": "contributor",
        "sdk_interface_version": "1.0.0",
        "compatibility": {"minimum_oak_version": "0.6.0", "maximum_oak_version": None},
        "payload": {
            "files": [
                {
                    "path": "adapter.yaml",
                    "digest": f"sha256:{'0' * 64}",
                    "media_type": "application/yaml",
                }
            ],
            "payload_digest": f"sha256:{'0' * 64}",
        },
        "licence": {"spdx_expression": "Apache-2.0", "terms_url": None},
        "supply_chain": {
            "signature_status": "absent",
            "provenance_status": "absent",
            "sbom_status": "absent",
        },
        "extensions": {},
    }
    (source / "extension.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8"
    )
    harness.service.sign_source(source, harness.steward())
    harness.service.install(source)
    activation = harness.service.activate(
        "extension.helm-binding", None, actor="local-user", occurred_at=NOW
    )
    assert activation["extension_id"] == "extension.helm-binding"

    unregistered = tmp_path / "bad-adapter"
    shutil.copytree(source, unregistered)
    (unregistered / "adapter.yaml").write_text(
        yaml.safe_dump({"renderer_id": "renderer.not-registered"}, sort_keys=True),
        encoding="utf-8",
    )
    manifest["id"] = "extension.bad-binding"
    (unregistered / "extension.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8"
    )
    harness.service.sign_source(unregistered, harness.steward())
    harness.service.install(unregistered)
    report = harness.service.verify("extension.bad-binding", None, occurred_at=NOW)
    content = next(check for check in report.checks if check["id"] == "payload-content")
    assert content["result"] == "fail"
    assert "registered in-tree" in content["detail"]


def test_activation_record_binds_manifest_digest(harness: Harness, tmp_path: Path) -> None:
    source = _pack_extension_source(tmp_path)
    harness.service.sign_source(source, harness.steward())
    entry = harness.service.install(source)
    activation = harness.service.activate(
        "extension.contributed-baseline", None, actor="local-user", occurred_at=NOW
    )
    assert activation["manifest_digest"] == content_digest(canonical_json_bytes(entry.manifest))
    active_entry = harness.store.entry("extension.contributed-baseline", None)
    record = harness.store.activation_record(active_entry)
    assert record is not None
    assert record["id"] == activation["id"]
    assert all(check["result"] == "pass" for check in record["verification"]["checks"])


def test_duplicate_install_is_refused(harness: Harness, tmp_path: Path) -> None:
    source = _pack_extension_source(tmp_path)
    harness.service.sign_source(source, harness.steward())
    harness.service.install(source)
    with pytest.raises(OAKError) as duplicate:
        harness.service.install(source)
    assert duplicate.value.code == "OAK-EXTENSION-EXISTS"


def test_only_one_version_of_an_extension_can_be_active(harness: Harness, tmp_path: Path) -> None:
    """A second active version would shadow the first in the id-keyed pack namespace.

    Both versions materialize to ``active-packs/<extension id>.yaml``, so allowing
    two would let one silently overwrite the other and let deactivating either
    strand the survivor with no pack on the policy path.
    """

    first = _pack_extension_source(tmp_path / "v1")
    harness.service.sign_source(first, harness.steward())
    harness.service.install(first)
    harness.service.activate(
        "extension.contributed-baseline", "1.0.0", actor="local-user", occurred_at=NOW
    )

    second = _pack_extension_source(tmp_path / "v2")
    manifest = yaml.safe_load((second / "extension.yaml").read_text())
    manifest["version"] = "2.0.0"
    (second / "extension.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8"
    )
    harness.service.sign_source(second, harness.steward())
    harness.service.install(second)

    with pytest.raises(OAKError) as conflict:
        harness.service.activate(
            "extension.contributed-baseline", "2.0.0", actor="local-user", occurred_at=NOW
        )
    assert conflict.value.code == "OAK-EXTENSION-VERSION-ACTIVE"

    states = {(item["version"], item["state"]) for item in harness.service.list_extensions()}
    assert states == {("1.0.0", "active"), ("2.0.0", "quarantined")}

    # The survivor keeps a usable pack once the prior version is deactivated.
    harness.service.deactivate("extension.contributed-baseline", "1.0.0")
    harness.service.activate(
        "extension.contributed-baseline", "2.0.0", actor="local-user", occurred_at=NOW
    )
    pack_store = LocalPolicyPackStore((harness.store_root / "active-packs",), harness.registry)
    assert pack_store.load("pack.contributed-baseline")["id"] == "pack.contributed-baseline"


def test_alias_bearing_pack_payload_is_refused_not_activated(
    harness: Harness, tmp_path: Path
) -> None:
    """A payload using YAML anchors must fail verification, not activate.

    Anchor expansion lets a small payload allocate an enormous one, and the
    bounded pack store refuses aliases anyway — so a pack that activated here
    would break every later policy read instead of being caught at the gate.
    """

    source = _pack_extension_source(tmp_path)
    pack_text = (source / "pack.yaml").read_text()
    pack_text += "\nextensions:\n  oak.community/anchor: &a [x, x]\n  oak.community/alias: *a\n"
    (source / "pack.yaml").write_text(pack_text, encoding="utf-8")
    harness.service.sign_source(source, harness.steward())
    harness.service.install(source)

    report = harness.service.verify("extension.contributed-baseline", None, occurred_at=NOW)
    content = next(check for check in report.checks if check["id"] == "payload-content")
    assert content["result"] == "fail"
    with pytest.raises(OAKError) as denial:
        harness.service.activate(
            "extension.contributed-baseline", None, actor="local-user", occurred_at=NOW
        )
    assert denial.value.code == "OAK-EXTENSION-QUARANTINED"
