# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-031 (RR-025, and RR-004's catalogue clause): an activated component-manifest or
architecture-pattern extension feeds the compiler's catalogue only while the operator's
trust directory vouches for it, and the catalogue snapshot records where every entry came
from. A failure refuses the compile; nothing is left out quietly.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from oak.adapters.persistence import FileWorkspaceRepository
from oak.contracts import SchemaRegistry
from oak.domain import ArtifactReference, canonical_json_bytes, content_digest
from oak.interfaces.cli.main import app as cli_app

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "templates" / "extensions"
BRIEF = ROOT / "examples" / "briefs" / "public-manual-qa.yaml"
ANSWERS = ROOT / "examples" / "briefs" / "public-manual-qa-answers.yaml"
EXTENSION_ID = "extension.contributed-rerank"
COMPONENT_ID = "component.contributed-rerank"
runner = CliRunner()

pytestmark = pytest.mark.integration


def _output(result) -> str:  # type: ignore[no-untyped-def]
    return str(result.output) + str(result.stderr or "")


def _oak(*arguments: str, cwd: Path) -> Any:
    previous = Path.cwd()
    os.chdir(cwd)
    try:
        return runner.invoke(cli_app, list(arguments))
    finally:
        os.chdir(previous)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("OAK_SERVER", raising=False)
    monkeypatch.setenv("OAK_TRUST_DIRECTORY", str(tmp_path / "trust"))
    monkeypatch.setenv("OAK_EXTENSIONS_DIRECTORY", str(tmp_path / "extensions"))
    monkeypatch.setenv("OAK_ACTOR", "local-user")
    created = _oak("keys", "init", cwd=tmp_path)
    assert created.exit_code == 0, _output(created)
    return tmp_path


def _component_source(
    home: Path, *, component_id: str = COMPONENT_ID, extension_id: str = EXTENSION_ID
) -> Path:
    source = home / "sources" / extension_id
    shutil.copytree(TEMPLATES / "component-manifest", source)
    component = yaml.safe_load((source / "component.yaml").read_text(encoding="utf-8"))
    component["id"] = component_id
    component["name"] = "Contributed reranker"
    (source / "component.yaml").write_text(
        "# SPDX-License-Identifier: Apache-2.0\n" + yaml.safe_dump(component, sort_keys=False),
        encoding="utf-8",
    )
    manifest = yaml.safe_load((source / "extension.yaml").read_text(encoding="utf-8"))
    manifest["id"] = extension_id
    (source / "extension.yaml").write_text(
        "# SPDX-License-Identifier: Apache-2.0\n" + yaml.safe_dump(manifest, sort_keys=True),
        encoding="utf-8",
    )
    return source


def _activate(home: Path, source: Path, extension_id: str) -> None:
    for step in (
        ["extensions", "sign", str(source)],
        ["extensions", "install", str(source)],
        ["extensions", "activate", extension_id],
    ):
        result = _oak(*step, cwd=home)
        assert result.exit_code == 0, f"{step}: {_output(result)}"


def _candidates(home: Path, name: str) -> tuple[Any, Path]:
    workspace = home / name
    assert _oak("init", str(workspace), cwd=home).exit_code == 0
    for step in (["design", str(BRIEF)], ["confirm", "--answers", str(ANSWERS)]):
        result = _oak(*step, cwd=workspace)
        assert result.exit_code == 0, f"{step}: {_output(result)}"
    return _oak("candidates", "--output", "json", cwd=workspace), workspace


def _snapshot(workspace: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    repository = FileWorkspaceRepository(workspace, SchemaRegistry.from_directory(ROOT / "schemas"))
    case = repository.current_case()
    assert case is not None
    reference = case["extensions"]["oak.community/catalogue_snapshot_ref"]
    return repository.read_json_artifact(ArtifactReference.from_document(reference)), case


def _active_directory(home: Path, extension_id: str = EXTENSION_ID) -> Path:
    return home / "extensions" / "active" / f"{extension_id}@0.1.0"


def _refused(home: Path, name: str, code: str) -> None:
    result, _workspace = _candidates(home, name)
    assert result.exit_code == 2, _output(result)
    assert code in _output(result)


def test_an_activated_signed_component_feeds_the_snapshot_with_its_provenance(home: Path) -> None:
    _activate(home, _component_source(home), EXTENSION_ID)
    result, workspace = _candidates(home, "with-extension")
    assert result.exit_code == 0, _output(result)
    snapshot, case = _snapshot(workspace)

    entries = {entry["manifest_ref"]["id"]: entry for entry in snapshot["entries"]}
    assert COMPONENT_ID in entries
    contributed = entries[COMPONENT_ID]
    assert (
        contributed["eligible"] is False
    )  # the template's reviews are pending, as curated rules say
    manifest = yaml.safe_load(
        (_active_directory(home) / "extension.yaml").read_text(encoding="utf-8")
    )
    identity = json.loads((home / "trust" / "extension-steward.identity.json").read_text())
    activation = json.loads((_active_directory(home) / "activation.json").read_text())
    assert contributed["provenance"] == {
        "origin": "extension",
        "extension_id": EXTENSION_ID,
        "extension_version": "0.1.0",
        "manifest_digest": content_digest(canonical_json_bytes(manifest)),
        "signer_key_id": identity["key_id"],
        "activated_at": activation["activated_at"],
    }
    for identifier, entry in entries.items():
        if identifier != COMPONENT_ID:
            assert entry["provenance"] == {"origin": "curated"}
    assert [item["provenance"] for item in snapshot["patterns"]] == [{"origin": "curated"}] * 4
    # Nothing references the contributed component, so the designs are the curated four.
    assert len(case["candidate_refs"]) == 4


def test_a_curated_only_catalogue_records_curated_provenance_everywhere(home: Path) -> None:
    result, workspace = _candidates(home, "curated")
    assert result.exit_code == 0, _output(result)
    snapshot, _case = _snapshot(workspace)
    assert {entry["provenance"]["origin"] for entry in snapshot["entries"]} == {"curated"}
    assert len(snapshot["patterns"]) == 4


def test_a_deactivated_extension_no_longer_feeds(home: Path) -> None:
    _activate(home, _component_source(home), EXTENSION_ID)
    deactivated = _oak("extensions", "deactivate", EXTENSION_ID, cwd=home)
    assert deactivated.exit_code == 0, _output(deactivated)
    result, workspace = _candidates(home, "deactivated")
    assert result.exit_code == 0, _output(result)
    snapshot, _case = _snapshot(workspace)
    assert COMPONENT_ID not in {entry["manifest_ref"]["id"] for entry in snapshot["entries"]}


def test_a_tampered_payload_stops_the_compile(home: Path) -> None:
    _activate(home, _component_source(home), EXTENSION_ID)
    payload = _active_directory(home) / "component.yaml"
    payload.write_text(payload.read_text(encoding="utf-8") + "# edited after activation\n")
    _refused(home, "tampered", "OAK-CATALOGUE-EXTENSION")


def test_a_signer_no_longer_pinned_stops_the_compile(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _activate(home, _component_source(home), EXTENSION_ID)
    # The operator's trust directory moves on: a new steward key, then no key at all.
    monkeypatch.setenv("OAK_TRUST_DIRECTORY", str(home / "other-trust"))
    assert _oak("keys", "init", cwd=home).exit_code == 0
    _refused(home, "other-key", "OAK-CATALOGUE-EXTENSION")
    monkeypatch.setenv("OAK_TRUST_DIRECTORY", str(home / "no-trust"))
    _refused(home, "no-key", "OAK-CATALOGUE-EXTENSION")


def test_a_pack_dropped_into_the_active_directory_is_refused(home: Path) -> None:
    source = _component_source(home)
    for step in (["extensions", "sign", str(source)], ["extensions", "install", str(source)]):
        assert _oak(*step, cwd=home).exit_code == 0
    quarantined = home / "extensions" / "quarantined" / f"{EXTENSION_ID}@0.1.0"
    _active_directory(home).parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(quarantined), str(_active_directory(home)))
    _refused(home, "dropped-in", "OAK-CATALOGUE-EXTENSION")


def test_an_altered_activation_record_is_refused(home: Path) -> None:
    _activate(home, _component_source(home), EXTENSION_ID)
    record_path = _active_directory(home) / "activation.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["manifest_digest"] = "sha256:" + "0" * 64
    record_path.write_text(json.dumps(record), encoding="utf-8")
    _refused(home, "altered-record", "OAK-CATALOGUE-EXTENSION")


def test_a_signature_by_a_key_outside_the_trust_directory_is_refused(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Signed and activated under one trust directory, read under another: the pinned key
    decides, never the key the pack carries."""

    source = _component_source(home)
    monkeypatch.setenv("OAK_TRUST_DIRECTORY", str(home / "foreign-trust"))
    assert _oak("keys", "init", cwd=home).exit_code == 0
    _activate(home, source, EXTENSION_ID)
    monkeypatch.setenv("OAK_TRUST_DIRECTORY", str(home / "trust"))
    _refused(home, "foreign-signer", "OAK-CATALOGUE-EXTENSION")


def test_an_extension_cannot_shadow_a_curated_component(home: Path) -> None:
    """The template as shipped reuses the curated fixture's id; it is refused, not merged."""

    source = home / "sources" / "shadow"
    shutil.copytree(TEMPLATES / "component-manifest", source)
    _activate(home, source, "extension.template-component-manifest")
    _refused(home, "shadow", "OAK-CATALOGUE-DUPLICATE")


def test_a_pattern_extension_cannot_add_a_variant(home: Path) -> None:
    """The pattern schema's variant enum is closed, so a contributed pattern can only
    duplicate a curated variant, which is refused."""

    source = home / "sources" / "pattern"
    shutil.copytree(TEMPLATES / "architecture-pattern", source)
    _activate(home, source, "extension.template-architecture-pattern")
    _refused(home, "pattern", "OAK-CATALOGUE-DUPLICATE")
