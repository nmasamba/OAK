# SPDX-License-Identifier: Apache-2.0
"""OAK-S7-006 headless case/plan/webhook validator tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from oak.adapters.persistence import FileWorkspaceRepository
from oak.bootstrap import create_design_case_service
from oak.contracts import SchemaRegistry
from oak.domain import ArtifactReference, OAKError, canonical_json_bytes
from oak.interfaces.cli.main import app as cli_app
from oak.interfaces.cli.validate import validate_bundle, validate_export, validate_webhook
from tests.runner_support import ROOT, build_compiled_case

pytestmark = pytest.mark.integration

WEBHOOK_EXAMPLE = ROOT / "examples" / "example-webhook-envelope.yaml"
PUBLISHER_IDENTITY = ROOT / "examples" / "portal" / "webhook-publisher.identity.json"

runner = CliRunner()


@pytest.fixture(scope="module")
def compiled_workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp_path = tmp_path_factory.mktemp("validate")
    return build_compiled_case(tmp_path).workspace


def _write_bundle(workspace: Path, destination: Path) -> None:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    repository = FileWorkspaceRepository(workspace, registry)
    case = repository.current_case()
    assert case is not None
    references = {
        "architecture-decision.json": case["extensions"]["oak.community/selection_decision_ref"],
        "assurance-plan.json": case["assurance_plan_ref"],
        "semantic-manifest.json": case["extensions"]["oak.community/semantic_manifest_ref"],
        "deployment-bundle.json": case["deployment_bundle_ref"],
        "runner-plan.json": case["runner_plan_ref"],
    }
    destination.mkdir(parents=True)
    for name, reference in references.items():
        document = repository.read_json_artifact(ArtifactReference.from_document(reference))
        (destination / name).write_bytes(canonical_json_bytes(document) + b"\n")


def test_a_real_export_validates_and_a_tampered_object_is_refused(
    compiled_workspace: Path, tmp_path: Path
) -> None:
    export_directory = tmp_path / "export"
    create_design_case_service(compiled_workspace).export_to(export_directory)
    result = validate_export(export_directory)
    assert result["valid"] is True
    assert result["case_id"] == "design-case.public-manual-qa"
    assert result["case_version"] == "0.1.7"
    assert result["status"] == "bundle_compiled"

    victim = sorted((export_directory / "objects" / "sha256").iterdir())[0]
    victim.write_bytes(victim.read_bytes() + b" ")
    with pytest.raises(OAKError) as denial:
        validate_export(export_directory)
    assert denial.value.code in {"OAK-IMPORT-DIGEST", "OAK-IMPORT-INVALID"}


def test_a_real_bundle_validates_and_tampering_is_refused(
    compiled_workspace: Path, tmp_path: Path
) -> None:
    bundle_directory = tmp_path / "bundle"
    _write_bundle(compiled_workspace, bundle_directory)
    result = validate_bundle(bundle_directory)
    assert result["valid"] is True
    assert result["runner_plan_id"].startswith("runner-plan.")

    tampered = json.loads((bundle_directory / "deployment-bundle.json").read_text())
    tampered["created_at"] = "2030-01-01T00:00:00Z"
    (bundle_directory / "deployment-bundle.json").write_bytes(
        canonical_json_bytes(tampered) + b"\n"
    )
    with pytest.raises(OAKError) as denial:
        validate_bundle(bundle_directory)
    assert denial.value.code == "OAK-VALIDATE-DIGEST"


def test_an_injected_execution_field_is_refused(compiled_workspace: Path, tmp_path: Path) -> None:
    bundle_directory = tmp_path / "bundle"
    _write_bundle(compiled_workspace, bundle_directory)
    poisoned = json.loads((bundle_directory / "architecture-decision.json").read_text())
    poisoned["extensions"]["oak.community/hook"] = {"Command": "rm -rf /"}
    (bundle_directory / "architecture-decision.json").write_bytes(
        canonical_json_bytes(poisoned) + b"\n"
    )
    with pytest.raises(OAKError) as denial:
        validate_bundle(bundle_directory)
    assert denial.value.code == "OAK-VALIDATE-EXECUTION-FIELD"


def test_a_missing_bundle_file_is_refused(compiled_workspace: Path, tmp_path: Path) -> None:
    bundle_directory = tmp_path / "bundle"
    _write_bundle(compiled_workspace, bundle_directory)
    (bundle_directory / "runner-plan.json").unlink()
    with pytest.raises(OAKError) as denial:
        validate_bundle(bundle_directory)
    assert denial.value.code == "OAK-VALIDATE-UNSAFE-PATH"


def test_the_committed_webhook_example_verifies_only_under_the_pinned_key(
    tmp_path: Path,
) -> None:
    result = validate_webhook(WEBHOOK_EXAMPLE, str(PUBLISHER_IDENTITY))
    assert result["valid"] is True
    assert result["event_type"] == "brief_interpreted"

    original_text = WEBHOOK_EXAMPLE.read_text(encoding="utf-8")
    tampered_text = original_text.replace("sequence: 1\n", "sequence: 99\n")
    assert tampered_text != original_text
    tampered_path = tmp_path / "tampered.yaml"
    tampered_path.write_text(tampered_text, encoding="utf-8")
    with pytest.raises(OAKError) as denial:
        validate_webhook(tampered_path, str(PUBLISHER_IDENTITY))
    assert denial.value.code == "OAK-VALIDATE-WEBHOOK-SIGNATURE"

    with pytest.raises(OAKError) as wrong_key:
        validate_webhook(WEBHOOK_EXAMPLE, "QXR0YWNrZXJLZXlBdHRhY2tlcktleUF0dGFja2VyS2V5QQ==")
    assert wrong_key.value.code == "OAK-VALIDATE-WEBHOOK-KEY"


def test_an_execution_field_in_a_webhook_envelope_is_refused(tmp_path: Path) -> None:
    # A publisher-signed envelope carrying an execution field inside its
    # free-form extensions must be refused, even though the schema's extensions
    # object permits arbitrary values.
    import yaml

    original = yaml.safe_load(WEBHOOK_EXAMPLE.read_text(encoding="utf-8"))
    original["extensions"] = {"vendor.example/hook": {"argv": ["sh", "-c", "curl evil"]}}
    poisoned = tmp_path / "poisoned.yaml"
    poisoned.write_text(yaml.safe_dump(original), encoding="utf-8")
    with pytest.raises(OAKError) as denial:
        validate_webhook(poisoned, str(PUBLISHER_IDENTITY))
    assert denial.value.code == "OAK-VALIDATE-EXECUTION-FIELD"


def test_a_yaml_alias_bearing_webhook_envelope_is_refused(tmp_path: Path) -> None:
    # Anchor expansion would let a tiny source allocate an enormous structure at
    # parse time; the untrusted-YAML reader refuses anchors/aliases outright.
    envelope = tmp_path / "aliased.yaml"
    envelope.write_text(
        "a: &a [x, x, x, x]\nb: &b [*a, *a, *a, *a]\ntop: [*b, *b, *b]\n",
        encoding="utf-8",
    )
    with pytest.raises(OAKError) as denial:
        validate_webhook(envelope, str(PUBLISHER_IDENTITY))
    assert denial.value.code == "OAK-VALIDATE-MALFORMED"


def test_an_execution_field_in_an_export_object_is_refused(
    compiled_workspace: Path, tmp_path: Path
) -> None:
    export_directory = tmp_path / "export"
    create_design_case_service(compiled_workspace).export_to(export_directory)
    # Poison one canonical object's free-form extensions with an execution field
    # and repoint the manifest entry at the new digest so schema/lineage still
    # pass; only the execution-field scan should catch it.
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    repository = FileWorkspaceRepository(compiled_workspace, registry)
    case = repository.current_case()
    assert case is not None
    reference = case["assurance_plan_ref"]
    document = repository.read_json_artifact(ArtifactReference.from_document(reference))
    document.setdefault("extensions", {})["vendor.example/hook"] = {"command": "rm -rf /"}
    poisoned_bytes = canonical_json_bytes(document)
    from oak.domain import content_digest

    poisoned_digest = content_digest(poisoned_bytes)
    old_hex = str(reference["digest"]).removeprefix("sha256:")
    new_hex = poisoned_digest.removeprefix("sha256:")
    (export_directory / "objects" / "sha256" / new_hex).write_bytes(poisoned_bytes)
    manifest_path = export_directory / "manifest.json"
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(manifest_text.replace(old_hex, new_hex), encoding="utf-8")
    with pytest.raises(OAKError) as denial:
        validate_export(export_directory)
    assert denial.value.code == "OAK-VALIDATE-EXECUTION-FIELD"


def test_cli_validate_exit_codes(compiled_workspace: Path, tmp_path: Path) -> None:
    export_directory = tmp_path / "export"
    create_design_case_service(compiled_workspace).export_to(export_directory)
    passed = runner.invoke(cli_app, ["validate", "export", str(export_directory)])
    assert passed.exit_code == 0, passed.output

    unknown = runner.invoke(cli_app, ["validate", "everything", str(export_directory)])
    assert unknown.exit_code == 2

    missing_key = runner.invoke(cli_app, ["validate", "webhook", str(WEBHOOK_EXAMPLE)])
    assert missing_key.exit_code == 2
