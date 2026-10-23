# SPDX-License-Identifier: Apache-2.0
"""OAK-S14-001: what a research run may send is a pure function of closed vocabularies.

ADR-0018, OAK-NFR-SEC-003 and OAK-FR-CAT-005. Over every committed brief's intent and the
synthetic intents under ``tests/fixtures/research/intents/``, every string the terms
document would send is a value from ``catalogue/research/capabilities.yaml`` or
``catalogue/research/licences.yaml``, plus two fixed query literals. Free text from the
intent, however hostile, never reaches a term. This is guard S2's property, proven here on
fixtures; ``scripts/check_research.py`` runs the same property live in ``make validate``.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from oak.adapters.catalogue import LocalCatalogue, ResearchVocabularyLoader
from oak.adapters.intake import LocalBriefIntake
from oak.compiler import (
    DeterministicBriefInterpreter,
    classify_hardware,
    derive_research_terms,
    terms_digest,
)
from oak.compiler.research_terms import FIXED_QUERY_VALUES
from oak.contracts import SchemaRegistry, load_yaml_document
from oak.domain import OAKError, ResearchVocabulary

ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = ROOT / "catalogue"
FIXTURE_INTENTS = sorted((ROOT / "tests/fixtures/research/intents").glob("*.yaml"))
NOW = "2026-10-20T12:00:00Z"


def _vocabulary() -> ResearchVocabulary:
    return ResearchVocabularyLoader(CATALOGUE).load()


def _patterns() -> tuple[dict[str, Any], ...]:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    return LocalCatalogue(CATALOGUE, registry).load().patterns


def _committed_intents() -> list[tuple[str, dict[str, Any]]]:
    intents: list[tuple[str, dict[str, Any]]] = []
    for brief in sorted((ROOT / "examples/briefs").glob("*.yaml")):
        if brief.name.endswith("-answers.yaml"):
            continue
        result = DeterministicBriefInterpreter().interpret(
            LocalBriefIntake().read(brief), created_at=NOW
        )
        intents.append((brief.name, result.intent_document))
    intents.append(
        (
            "example-intent.yaml",
            load_yaml_document((ROOT / "examples/example-intent.yaml").read_text()),
        )
    )
    return intents


def _every_intent() -> list[tuple[str, dict[str, Any]]]:
    synthetic = [(path.name, yaml.safe_load(path.read_text())) for path in FIXTURE_INTENTS]
    return _committed_intents() + synthetic


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    return []


def _sent_vocabulary(vocabulary: ResearchVocabulary) -> set[str]:
    allowed: set[str] = set(FIXED_QUERY_VALUES)
    for entry in vocabulary.capabilities["capabilities"].values():
        allowed.update(entry["hub_pipeline_tags"])
        allowed.update(entry["hub_filters"])
    for kind in vocabulary.capabilities["harness_kinds"].values():
        allowed.update(kind["github_topics"])
    return allowed


def _local_vocabulary(vocabulary: ResearchVocabulary) -> set[str]:
    allowed = set(vocabulary.capabilities["capabilities"])
    allowed.update(str(entry["id"]) for entry in vocabulary.hardware_classes["classes"])
    for entry in vocabulary.licences["licences"]:
        allowed.add(str(entry["spdx_id"]))
        allowed.add(str(entry["github_keyword"]))
        allowed.add(str(entry["hub_tag"]))
    return allowed


def test_the_fixture_intents_exist_and_cover_the_hostile_case() -> None:
    names = {path.name for path in FIXTURE_INTENTS}
    assert {"hostile-free-text.yaml", "no-hardware.yaml", "cpu-small.yaml"} <= names


@pytest.mark.parametrize(
    ("name", "intent"), _every_intent(), ids=lambda value: value if isinstance(value, str) else ""
)
def test_every_sent_term_comes_from_the_closed_vocabularies(
    name: str, intent: dict[str, Any]
) -> None:
    vocabulary = _vocabulary()
    terms = derive_research_terms(intent, vocabulary, _patterns())

    sent = _strings(terms["sent"])
    assert sent, name
    outside = sorted(set(sent) - _sent_vocabulary(vocabulary))
    assert outside == [], f"{name}: sent strings outside the vocabulary: {outside}"
    local = _strings(dict(terms["local"]))
    outside_local = sorted(set(local) - _local_vocabulary(vocabulary))
    assert outside_local == [], f"{name}: local strings outside the vocabulary: {outside_local}"


def test_hostile_free_text_in_the_hardware_section_never_reaches_a_term() -> None:
    path = ROOT / "tests/fixtures/research/intents/hostile-free-text.yaml"
    intent = yaml.safe_load(path.read_text())
    terms = derive_research_terms(intent, _vocabulary(), _patterns())

    serialised = json.dumps(terms)
    assert "planted" not in serialised
    assert "invalid" not in serialised
    assert "2099" not in serialised
    assert terms["local"]["hardware_class"] == "accelerator-large"


def test_the_terms_are_deterministic_and_their_digest_is_stable() -> None:
    intent = load_yaml_document((ROOT / "examples/example-intent.yaml").read_text())
    first = derive_research_terms(intent, _vocabulary(), _patterns())
    second = derive_research_terms(copy.deepcopy(intent), _vocabulary(), _patterns())

    assert first == second
    assert terms_digest(first, source_mode="live", hosts=["b", "a"]) == terms_digest(
        second, source_mode="live", hosts=["a", "b"]
    )
    assert terms_digest(first, source_mode="live", hosts=[]).startswith("sha256:")
    # The destination is part of what is consented to (F1-1).
    assert terms_digest(first, source_mode="fixture", hosts=[]) != terms_digest(
        first, source_mode="live", hosts=[]
    )
    assert terms_digest(first, source_mode="live", hosts=["a"]) != terms_digest(
        first, source_mode="live", hosts=["a", "b"]
    )
    assert first["version"] == "community-research-terms-1.0.0"
    assert first["local"]["capabilities"] == ["citation_drafting", "independent_verification"]
    assert first["sent"]["hub"]["pipeline_tags"] == ["text-generation"]
    assert "licences" not in first["sent"]["github"]
    assert first["local"]["licence_keywords"] == ["apache-2.0", "bsd-3-clause", "mit"]
    assert first["sent"]["github"]["pushed_within_days"] == 180
    assert "serving_runtime" in first["sent"]["github"]["topics"]


def test_the_terms_read_nothing_from_the_intent_but_its_hardware_numbers() -> None:
    """Changing every other section, however much, changes no term."""

    base = load_yaml_document((ROOT / "examples/example-intent.yaml").read_text())
    mutated = copy.deepcopy(base)
    for section, value in mutated["spec"].items():
        if section != "hardware" and isinstance(value, dict):
            for key in value:
                if isinstance(value[key], str):
                    value[key] = "topic:planted"
                elif isinstance(value[key], list):
                    value[key] = ["license:planted"]
    mutated["id"] = "intent.planted"

    assert derive_research_terms(base, _vocabulary(), _patterns()) == derive_research_terms(
        mutated, _vocabulary(), _patterns()
    )


@pytest.mark.parametrize(
    ("hardware", "expected"),
    [
        ({}, "unknown"),
        ({"accelerators": [], "ram_gib": 8}, "cpu-small"),
        ({"accelerators": [], "ram_gib": 32}, "cpu-medium"),
        ({"accelerators": [], "ram_gib": 64}, "cpu-large"),
        ({"accelerators": ["x"], "vram_gib": None}, "accelerator-small"),
        ({"accelerators": ["x"], "vram_gib": 16}, "accelerator-medium"),
        ({"accelerators": ["x"], "vram_gib": 80}, "accelerator-large"),
        ({"accelerators": "not-a-list", "ram_gib": True}, "unknown"),
    ],
)
def test_the_hardware_class_follows_the_first_matching_rule(
    hardware: dict[str, Any], expected: str
) -> None:
    intent = {"spec": {"hardware": hardware}} if hardware else {"spec": {}}

    assert classify_hardware(intent, _vocabulary()) == expected


def test_a_freshness_window_outside_one_to_365_days_is_refused() -> None:
    intent = load_yaml_document((ROOT / "examples/example-intent.yaml").read_text())
    for days in (0, 366):
        with pytest.raises(OAKError) as error:
            derive_research_terms(intent, _vocabulary(), _patterns(), freshness_window_days=days)
        assert error.value.code == "OAK-RESEARCH-VOCABULARY"


def test_a_binding_that_names_a_non_model_role_is_refused() -> None:
    vocabulary = _vocabulary()
    broken = copy.deepcopy(vocabulary.bindings[0])
    broken["model_role_id"] = "role.retrieval"
    broken["serving_edge"]["to"] = "role.retrieval"
    poisoned = ResearchVocabulary(
        capabilities=vocabulary.capabilities,
        hardware_classes=vocabulary.hardware_classes,
        licences=vocabulary.licences,
        harness_repositories=vocabulary.harness_repositories,
        bindings=(broken,),
    )
    with pytest.raises(OAKError) as error:
        derive_research_terms({"spec": {}}, poisoned, _patterns())
    assert error.value.code == "OAK-RESEARCH-VOCABULARY"


def test_the_curated_loader_never_reads_the_research_directory() -> None:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    documents = LocalCatalogue(CATALOGUE, registry).load()

    identifiers = {str(item["id"]) for item in documents.manifests + documents.patterns}
    assert not any(identifier.startswith("research.") for identifier in identifiers)
    assert len(documents.manifests) == 3 and len(documents.patterns) == 4


def test_the_harness_list_is_a_draft_until_the_owner_reviews_it() -> None:
    vocabulary = _vocabulary()

    assert vocabulary.harness_repositories["reviewed_by"] is None
    assert vocabulary.harness_repositories["reviewed_at"] is None
    assert vocabulary.harness_repositories["repositories"]


@pytest.mark.parametrize(
    ("file_name", "mutate", "message"),
    [
        (
            "capabilities.yaml",
            lambda d: d["capabilities"]["citation_drafting"]["hub_pipeline_tags"].append(
                "Text Gen"
            ),
            "token shape",
        ),
        (
            "capabilities.yaml",
            lambda d: d["capabilities"]["citation_drafting"].update(harness_kind="planted"),
            "unknown harness kind",
        ),
        (
            "capabilities.yaml",
            lambda d: d["harness_kinds"]["serving_runtime"].update(role="installer"),
            "malformed",
        ),
        (
            "hardware-classes.yaml",
            lambda d: d["classes"].append({"id": "planted", "accelerators": "present"}),
            "fallback",
        ),
        (
            "hardware-classes.yaml",
            lambda d: d["classes"][0].update(ram_gib_at_least=-1),
            "threshold",
        ),
        (
            "licences.yaml",
            lambda d: d["licences"][0].update(classification="free"),
            "classification",
        ),
        (
            "licences.yaml",
            lambda d: d["licences"][0].update(github_keyword="apache 2.0"),
            "token shape",
        ),
        (
            "licences.yaml",
            lambda d: d["licences"].append(dict(d["licences"][0], spdx_id="apache-2.0")),
            "repeated",
        ),
        (
            "harness-repositories.yaml",
            lambda d: d["repositories"][0].update(repository="../../etc"),
            "malformed",
        ),
        (
            "harness-repositories.yaml",
            lambda d: d["repositories"][0].update(source="https://planted.invalid/x"),
            "GitHub address",
        ),
        ("harness-repositories.yaml", lambda d: d.update(reviewed_at="yesterday"), "date"),
        (
            "harness-repositories.yaml",
            lambda d: d["repositories"][0].update(kind="installer"),
            "unknown kind",
        ),
    ],
)
def test_a_vocabulary_outside_its_closed_shape_is_refused(
    tmp_path: Path, file_name: str, mutate: Any, message: str
) -> None:
    root = tmp_path / "catalogue"
    research = root / "research"
    research.mkdir(parents=True)
    (research / "bindings").mkdir()
    for path in (CATALOGUE / "research").glob("*.yaml"):
        (research / path.name).write_text(path.read_text())
    for path in (CATALOGUE / "research/bindings").glob("*.yaml"):
        (research / "bindings" / path.name).write_text(path.read_text())
    target = research / file_name
    document = yaml.safe_load(target.read_text())
    mutate(document)
    target.write_text(yaml.safe_dump(document, sort_keys=False))

    with pytest.raises(OAKError) as error:
        ResearchVocabularyLoader(root).load()
    assert error.value.code == "OAK-RESEARCH-VOCABULARY"
    assert message in str(error.value)


def test_a_binding_whose_edge_does_not_join_the_two_roles_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "catalogue"
    research = root / "research"
    (research / "bindings").mkdir(parents=True)
    for path in (CATALOGUE / "research").glob("*.yaml"):
        (research / path.name).write_text(path.read_text())
    binding = yaml.safe_load((CATALOGUE / "research/bindings/balanced.yaml").read_text())
    binding["serving_edge"]["to"] = "role.retrieval"
    (research / "bindings/balanced.yaml").write_text(yaml.safe_dump(binding, sort_keys=False))

    with pytest.raises(OAKError) as error:
        ResearchVocabularyLoader(root).load()
    assert error.value.code == "OAK-RESEARCH-VOCABULARY"
