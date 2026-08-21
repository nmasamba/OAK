# SPDX-License-Identifier: Apache-2.0
"""OAK-S7-005/006 portal examples stay inside documented API behavior."""

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKSTAGE = ROOT / "examples" / "backstage"
PORTAL = ROOT / "examples" / "portal"
OPENAPI = json.loads((ROOT / "openapi" / "oak.openapi.json").read_text(encoding="utf-8"))
PATH_PATTERN = re.compile(r"/v1/[A-Za-z0-9_{}.:\-]+(?:/[A-Za-z0-9_{}.:\-]+)*")


def _normalized_openapi_paths() -> set[str]:
    normalized = set()
    for path in OPENAPI["paths"]:
        normalized.add(re.sub(r"\{[^}]+\}", "{}", path))
    return normalized


def _referenced_paths(text: str) -> set[str]:
    found = set()
    for match in PATH_PATTERN.findall(text):
        found.add(re.sub(r"\{[^}]+\}", "{}", match))
    return found


def test_every_rest_path_in_the_backstage_examples_is_a_documented_path() -> None:
    documented = _normalized_openapi_paths()
    referenced: set[str] = set()
    for path in sorted(BACKSTAGE.glob("*")):
        referenced |= _referenced_paths(path.read_text(encoding="utf-8"))
    for path in sorted(PORTAL.glob("*.md")):
        referenced |= _referenced_paths(path.read_text(encoding="utf-8"))
    assert referenced, "the examples must reference documented REST paths"
    undocumented = {path for path in referenced if path not in documented}
    assert not undocumented, f"undocumented API paths referenced: {sorted(undocumented)}"


def test_the_backstage_wiring_references_no_privileged_operation() -> None:
    # Prose may name the prohibited operations to document them; the wiring
    # files that a portal would actually load may not touch them.
    forbidden = (":approve", "runner-jobs", "secrets", ":cancel", "policy-override")
    for path in sorted(BACKSTAGE.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        for term in forbidden:
            assert term not in text, (path.name, term)


def test_the_backstage_yaml_examples_parse_and_carry_no_credentials() -> None:
    names = ("catalog-info.yaml", "catalog-api.yaml", "template.yaml", "app-config.oak.yaml")
    for name in names:
        text = (BACKSTAGE / name).read_text(encoding="utf-8")
        documents = [document for document in yaml.safe_load_all(text) if document is not None]
        # Single-document files only: the governance validator rejects multi-document
        # YAML anywhere in the tree.
        assert len(documents) == 1, name
        assert isinstance(documents[0], dict), name
        lowered = text.casefold()
        for needle in ("password", "secret:", "token:", "authorization"):
            assert needle not in lowered, (name, needle)


def test_no_backstage_type_leaks_into_the_core() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        if "backstage" in path.read_text(encoding="utf-8").casefold():
            offenders.append(str(path))
    assert not offenders, offenders


def test_the_committed_publisher_identity_is_public_material_only() -> None:
    identity = json.loads((PORTAL / "webhook-publisher.identity.json").read_text("utf-8"))
    assert set(identity) == {"role", "key_id", "algorithm", "public_key_base64", "trust_level"}
    assert identity["role"] == "webhook-publisher"
    assert identity["trust_level"] == "development"
    assert "private" not in json.dumps(identity).casefold()
