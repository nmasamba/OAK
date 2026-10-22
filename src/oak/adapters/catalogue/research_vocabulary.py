# SPDX-License-Identifier: Apache-2.0
"""Bounded loader for the research vocabularies under ``catalogue/research/``.

Sprint 14 (ADR-0018). The five documents are data: the capability map, the hardware
classes, the licence list, the owner-reviewed harness list and the research bindings. Every
term a research run sends comes from them, so each value is held to a closed ASCII token
shape here, before the pure terms function ever sees it. The curated loader never reads
this directory, and this loader never reads the curated one.
"""

import re
from pathlib import Path
from typing import Any

from oak.adapters.catalogue.local_catalogue import read_bounded_catalogue_document
from oak.domain import OAKError, ResearchVocabulary

MAXIMUM_BINDINGS = 16
MAXIMUM_ENTRIES = 64
TOKEN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SPDX_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]{0,63}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]{1,64}/[A-Za-z0-9_.-]{1,100}$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9.-]{0,79}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HARNESS_ROLES = frozenset({"serving", None})
COMPONENT_CATEGORIES = frozenset({"model", "software"})
LICENCE_CLASSIFICATIONS = frozenset(
    {
        "osi_approved",
        "open_source_ai",
        "restricted",
        "source_available",
        "proprietary",
        "dataset_specific",
        "not_applicable",
        "unknown",
    }
)
HARDWARE_PRESENCE = frozenset({"present", "absent"})


class ResearchVocabularyLoader:
    """Reads and shape-checks the research vocabularies; raises ``OAK-RESEARCH-VOCABULARY``."""

    def __init__(self, root: Path) -> None:
        self._root = root / "research"

    def load(self) -> ResearchVocabulary:
        if self._root.is_symlink() or not self._root.is_dir():
            raise OAKError("OAK-RESEARCH-VOCABULARY", "research vocabulary directory is missing")
        capabilities = self._document("capabilities.yaml", "research.capabilities")
        hardware = self._document("hardware-classes.yaml", "research.hardware-classes")
        licences = self._document("licences.yaml", "research.licences")
        harnesses = self._document("harness-repositories.yaml", "research.harness-repositories")
        bindings_directory = self._root / "bindings"
        if bindings_directory.is_symlink() or not bindings_directory.is_dir():
            raise OAKError("OAK-RESEARCH-VOCABULARY", "research bindings directory is missing")
        binding_paths = sorted(bindings_directory.glob("*.yaml"))
        if not binding_paths or len(binding_paths) > MAXIMUM_BINDINGS:
            raise OAKError("OAK-RESEARCH-VOCABULARY", "research bindings count is out of range")
        bindings = tuple(self._read(path) for path in binding_paths)
        try:
            _check_capabilities(capabilities)
            _check_hardware_classes(hardware)
            _check_licences(licences)
            _check_harness_repositories(harnesses, capabilities)
            for binding in bindings:
                _check_binding(binding)
        except ValueError as error:
            raise OAKError("OAK-RESEARCH-VOCABULARY", str(error)) from error
        return ResearchVocabulary(
            capabilities=capabilities,
            hardware_classes=hardware,
            licences=licences,
            harness_repositories=harnesses,
            bindings=bindings,
        )

    def _document(self, name: str, identifier: str) -> dict[str, Any]:
        document = self._read(self._root / name)
        if document.get("id") != identifier or document.get("schema_version") != "0.1.0":
            raise OAKError("OAK-RESEARCH-VOCABULARY", f"{name} has an unexpected identity")
        return document

    def _read(self, path: Path) -> dict[str, Any]:
        try:
            return read_bounded_catalogue_document(path)
        except ValueError as error:
            raise OAKError(
                "OAK-RESEARCH-VOCABULARY", "research vocabulary document failed bounded reading"
            ) from error


def _tokens(value: Any, what: str) -> list[str]:
    if not isinstance(value, list) or len(value) > MAXIMUM_ENTRIES:
        raise ValueError(f"{what} must be a bounded list")
    for item in value:
        if not isinstance(item, str) or not TOKEN.match(item):
            raise ValueError(f"{what} holds a value outside the token shape")
    if len(set(value)) != len(value):
        raise ValueError(f"{what} repeats a value")
    return value


def _check_capabilities(document: dict[str, Any]) -> None:
    capabilities = document.get("capabilities")
    kinds = document.get("harness_kinds")
    if (
        not isinstance(capabilities, dict)
        or not capabilities
        or len(capabilities) > MAXIMUM_ENTRIES
    ):
        raise ValueError("capabilities must be a bounded mapping")
    if not isinstance(kinds, dict) or not kinds or len(kinds) > MAXIMUM_ENTRIES:
        raise ValueError("harness_kinds must be a bounded mapping")
    for name, kind in kinds.items():
        if not isinstance(name, str) or not TOKEN.match(name) or not isinstance(kind, dict):
            raise ValueError("harness kind is malformed")
        if set(kind) != {"role", "github_topics"} or kind["role"] not in HARNESS_ROLES:
            raise ValueError(f"harness kind {name} is malformed")
        _tokens(kind["github_topics"], f"harness kind {name} topics")
    for name, entry in capabilities.items():
        if not isinstance(name, str) or not TOKEN.match(name) or not isinstance(entry, dict):
            raise ValueError("capability is malformed")
        expected = {"component_category", "hub_pipeline_tags", "hub_filters", "harness_kind"}
        if set(entry) != expected or entry["component_category"] not in COMPONENT_CATEGORIES:
            raise ValueError(f"capability {name} is malformed")
        _tokens(entry["hub_pipeline_tags"], f"capability {name} pipeline tags")
        _tokens(entry["hub_filters"], f"capability {name} filters")
        if entry["harness_kind"] is not None and entry["harness_kind"] not in kinds:
            raise ValueError(f"capability {name} names an unknown harness kind")


def _check_hardware_classes(document: dict[str, Any]) -> None:
    classes = document.get("classes")
    if not isinstance(classes, list) or not classes or len(classes) > MAXIMUM_ENTRIES:
        raise ValueError("hardware classes must be a bounded list")
    seen: set[str] = set()
    for entry in classes:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise ValueError("hardware class is malformed")
        if not TOKEN.match(entry["id"]) or entry["id"] in seen:
            raise ValueError("hardware class id is malformed or repeated")
        seen.add(entry["id"])
        allowed = {"id", "accelerators", "vram_gib_at_least", "ram_gib_at_least"}
        if set(entry) - allowed:
            raise ValueError(f"hardware class {entry['id']} has an unknown key")
        if "accelerators" in entry and entry["accelerators"] not in HARDWARE_PRESENCE:
            raise ValueError(f"hardware class {entry['id']} has a malformed presence rule")
        for key in ("vram_gib_at_least", "ram_gib_at_least"):
            if key in entry and (
                isinstance(entry[key], bool)
                or not isinstance(entry[key], (int, float))
                or entry[key] < 0
            ):
                raise ValueError(f"hardware class {entry['id']} has a malformed threshold")
    if classes[-1].keys() != {"id"}:
        raise ValueError("the last hardware class must be the unconditional fallback")


def _check_licences(document: dict[str, Any]) -> None:
    licences = document.get("licences")
    if not isinstance(licences, list) or not licences or len(licences) > MAXIMUM_ENTRIES:
        raise ValueError("licences must be a bounded list")
    seen: set[str] = set()
    for entry in licences:
        expected = {
            "spdx_id",
            "classification",
            "github_keyword",
            "hub_tag",
            "source",
            "checked_at",
        }
        if not isinstance(entry, dict) or set(entry) != expected:
            raise ValueError("licence entry is malformed")
        if not isinstance(entry["spdx_id"], str) or not SPDX_ID.match(entry["spdx_id"]):
            raise ValueError("licence spdx id is malformed")
        if entry["spdx_id"].casefold() in seen:
            raise ValueError("licence spdx id is repeated")
        seen.add(entry["spdx_id"].casefold())
        if entry["classification"] not in LICENCE_CLASSIFICATIONS:
            raise ValueError("licence classification is not a known class")
        for key in ("github_keyword", "hub_tag"):
            if not isinstance(entry[key], str) or not TOKEN.match(entry[key]):
                raise ValueError(f"licence {key} is outside the token shape")
        if not isinstance(entry["source"], str) or not entry["source"].startswith("https://"):
            raise ValueError("licence source must be an https address")
        if not isinstance(entry["checked_at"], str) or not DATE.match(entry["checked_at"]):
            raise ValueError("licence checked_at must be a date")


def _check_harness_repositories(document: dict[str, Any], capabilities: dict[str, Any]) -> None:
    repositories = document.get("repositories")
    if not isinstance(repositories, list) or len(repositories) > MAXIMUM_ENTRIES:
        raise ValueError("harness repositories must be a bounded list")
    for key in ("reviewed_by", "reviewed_at"):
        value = document.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"harness list {key} must be null or a non-empty string")
    if document.get("reviewed_at") is not None and not DATE.match(str(document["reviewed_at"])):
        raise ValueError("harness list reviewed_at must be a date")
    seen: set[str] = set()
    for entry in repositories:
        expected = {"repository", "kind", "why", "source", "checked_at"}
        if not isinstance(entry, dict) or set(entry) != expected:
            raise ValueError("harness repository entry is malformed")
        repository = entry["repository"]
        if not isinstance(repository, str) or not REPOSITORY.match(repository):
            raise ValueError("harness repository name is malformed")
        if repository.casefold() in seen:
            raise ValueError("harness repository is repeated")
        seen.add(repository.casefold())
        if entry["kind"] not in capabilities["harness_kinds"]:
            raise ValueError("harness repository names an unknown kind")
        if not isinstance(entry["why"], str) or not 0 < len(entry["why"]) <= 160:
            raise ValueError("harness repository reason is out of bounds")
        if entry["source"] != f"https://github.com/{repository}":
            raise ValueError("harness repository source must be its GitHub address")
        if not isinstance(entry["checked_at"], str) or not DATE.match(entry["checked_at"]):
            raise ValueError("harness repository checked_at must be a date")


def _check_binding(document: dict[str, Any]) -> None:
    expected = {
        "schema_version",
        "id",
        "version",
        "pattern_id",
        "model_role_id",
        "serving_role",
        "serving_edge",
    }
    if set(document) != expected or document["schema_version"] != "0.1.0":
        raise ValueError("research binding is malformed")
    for key in ("id", "pattern_id", "model_role_id", "version"):
        if not isinstance(document[key], str) or not document[key]:
            raise ValueError(f"research binding {key} is malformed")
    if not IDENTIFIER.match(document["id"]) or not document["id"].startswith("research.binding."):
        raise ValueError("research binding id is malformed")
    role = document["serving_role"]
    role_keys = {"id", "role", "component_category", "required_capability", "data_classifications"}
    if not isinstance(role, dict) or set(role) != role_keys:
        raise ValueError("research binding serving role is malformed")
    if role["id"] != "role.serving" or role["component_category"] != "software":
        raise ValueError("research binding serving role must be role.serving, software")
    if role["required_capability"] != "model_serving":
        raise ValueError("research binding serving role must require model_serving")
    edge = document["serving_edge"]
    edge_keys = {"from", "to", "interface", "data", "security"}
    if not isinstance(edge, dict) or set(edge) != edge_keys:
        raise ValueError("research binding serving edge is malformed")
    if edge["from"] != "role.serving" or edge["to"] != document["model_role_id"]:
        raise ValueError("research binding serving edge must join the serving and model roles")
