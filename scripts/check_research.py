# SPDX-License-Identifier: Apache-2.0
"""Research guards S1 to S5: what research sends and keeps stays inside its closed rules.

The guard normalises the recorded fixtures live, with the fixed clock, rather than reading a
committed output: a change to a parser, a gate or a vocabulary that breaks a rule fails
here even if someone refreshed a fixture with it (Sprint 14, ADR-0018).

S1  The research adapter's host allowlist is exactly the three hosts the decision record
    names, the live transport is scoped to them, and the adapter builds no other address.
S2  The derived-terms function emits only terms from its closed vocabularies, over every
    committed brief's intent and the synthetic intents.
S3  No researched manifest, in any fixture or output, is `eligible` or `approved_for_context`.
S4  Every claim in the normalised output carries an evidence class from the closed enum.
S5  No normalised string holds a category C character, a forbidden word, or a value
    outside its bounds; no gap is a placeholder.
"""

from __future__ import annotations

import ast
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oak.adapters.catalogue import LocalCatalogue, ResearchVocabularyLoader  # noqa: E402
from oak.adapters.intake import LocalBriefIntake  # noqa: E402
from oak.adapters.models.huggingface_catalogue import TRUSTED_NAMESPACES  # noqa: E402
from oak.adapters.models.research_fixture import FixtureResearchSource  # noqa: E402
from oak.adapters.models.research_sources import RESEARCH_HOSTS, run_research  # noqa: E402
from oak.bootstrap import create_research_source  # noqa: E402
from oak.compiler import (  # noqa: E402
    DeterministicBriefInterpreter,
    derive_research_terms,
    terms_digest,
)
from oak.compiler.research_terms import FIXED_QUERY_VALUES  # noqa: E402
from oak.contracts import SchemaRegistry, load_yaml_document  # noqa: E402
from oak.domain import EVIDENCE_CLASSES, RESEARCH_EXTENSION  # noqa: E402
from oak.domain.research_rules import COLUMN_LIMIT, IDENTIFIER_LIMIT, NOT_PUBLISHED  # noqa: E402
from oak.domain.vocabulary import forbidden_words  # noqa: E402

EXPECTED_HOSTS = frozenset({"huggingface.co", "router.huggingface.co", "api.github.com"})
PAGE_HOSTS = frozenset({"github.com", "huggingface.co"})
# The reserved host (RFC 2606) a fixture run names in place of a real page address.
FIXTURE_HOST = "fixture.invalid"
FIXED_CLOCK = "2026-10-20T12:00:00Z"
FIXTURES = ROOT / "tests/fixtures/research/live"
PLACEHOLDERS = frozenset(
    {"n/a", "na", "none", "null", "nil", "-", "--", "tbd", "todo", "?", "unknown"}
)


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    return []


def check_s1() -> list[str]:
    failures: list[str] = []
    if RESEARCH_HOSTS != EXPECTED_HOSTS:
        failures.append(
            f"S1 RESEARCH_HOSTS is {sorted(RESEARCH_HOSTS)}, not {sorted(EXPECTED_HOSTS)}"
        )
    source = (ROOT / "src/oak/adapters/models/research_sources.py").read_text(encoding="utf-8")
    for match in re.finditer(r"https?://([A-Za-z0-9.{}_-]+)", source):
        host = match.group(1)
        # Page addresses in a manifest (`https://github.com/<repo>`) are records, never
        # requests; every request goes through the transport, whose allowlist S1 pins below.
        if (
            host.startswith("{")
            or host in EXPECTED_HOSTS
            or host in PAGE_HOSTS
            or host == FIXTURE_HOST
        ):
            continue
        failures.append(f"S1 research_sources.py builds an address for {host!r}")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for candidate in re.findall(r"\b[a-z0-9-]+\.(?:co|com|org|io|net|dev)\b", node.value):
                if candidate not in EXPECTED_HOSTS and candidate not in {
                    "github.com",
                    "huggingface.co",
                }:
                    failures.append(f"S1 research_sources.py names a host {candidate!r}")
    fetch, mode, hosts = create_research_source(occurred_at=FIXED_CLOCK)
    if mode != "live" or hosts != EXPECTED_HOSTS:
        failures.append(f"S1 the live research source is mode {mode!r} with hosts {sorted(hosts)}")
    transport = getattr(fetch, "__self__", None)
    allowed = getattr(transport, "allowed_hosts", None)
    if allowed != EXPECTED_HOSTS:
        failures.append(f"S1 the live transport allows {allowed!r}")
    return failures


def _intents() -> list[tuple[str, dict[str, Any]]]:
    intents: list[tuple[str, dict[str, Any]]] = []
    for brief in sorted((ROOT / "examples/briefs").glob("*.yaml")):
        if brief.name.endswith("-answers.yaml"):
            continue
        result = DeterministicBriefInterpreter().interpret(
            LocalBriefIntake().read(brief), created_at=FIXED_CLOCK
        )
        intents.append((brief.name, result.intent_document))
    intents.append(
        (
            "example-intent.yaml",
            load_yaml_document((ROOT / "examples/example-intent.yaml").read_text()),
        )
    )
    for path in sorted((ROOT / "tests/fixtures/research/intents").glob("*.yaml")):
        intents.append((path.name, yaml.safe_load(path.read_text(encoding="utf-8"))))
    return intents


def check_s2(vocabulary: Any, patterns: tuple[dict[str, Any], ...]) -> list[str]:
    failures: list[str] = []
    allowed: set[str] = set(FIXED_QUERY_VALUES)
    for entry in vocabulary.capabilities["capabilities"].values():
        allowed.update(entry["hub_pipeline_tags"])
        allowed.update(entry["hub_filters"])
    for kind in vocabulary.capabilities["harness_kinds"].values():
        allowed.update(kind["github_topics"])
    for name, intent in _intents():
        terms = derive_research_terms(intent, vocabulary, patterns)
        outside = sorted(set(_strings(terms["sent"])) - allowed)
        if outside:
            failures.append(f"S2 {name}: sent terms outside the vocabularies: {outside}")
        serialised = json.dumps(terms)
        for probe in ("planted", "invalid", "topic:", "license:"):
            if probe in serialised:
                failures.append(f"S2 {name}: {probe!r} reached the terms")
    return failures


def _normalised_output(vocabulary: Any, patterns: tuple[dict[str, Any], ...]) -> Any:
    intent = load_yaml_document((ROOT / "examples/example-intent.yaml").read_text())
    terms = derive_research_terms(intent, vocabulary, patterns)
    source = FixtureResearchSource(FIXTURES, occurred_at=FIXED_CLOCK)
    return run_research(
        source.fetch,
        terms=terms,
        terms_digest=terms_digest(terms),
        vocabulary=vocabulary,
        trusted_namespaces=TRUSTED_NAMESPACES,
        intent_ref={
            "id": "intent.public-manual-qa",
            "version": "0.1.0",
            "digest": "sha256:" + "0" * 64,
        },
        case_id="design-case.guard",
        snapshot_id="research.guard",
        snapshot_version="0.1.0",
        occurred_at=FIXED_CLOCK,
        source_mode="fixture",
        clock=lambda: 0.0,
    )


def _researched_manifests(run: Any) -> list[tuple[str, dict[str, Any]]]:
    found = [(artifact.id, json.loads(artifact.content)) for artifact in run.manifests]
    for path in sorted((ROOT / "catalogue/components").glob("*.yaml")):
        found.append((path.name, load_yaml_document(path.read_text(encoding="utf-8"))))
    for path in sorted((ROOT / "examples").glob("example-component*.yaml")):
        found.append((path.name, load_yaml_document(path.read_text(encoding="utf-8"))))
    return found


def check_s3(run: Any) -> list[str]:
    failures: list[str] = []
    for name, manifest in _researched_manifests(run):
        if RESEARCH_EXTENSION in manifest.get("extensions", {}):
            if manifest.get("status") != "quarantined":
                failures.append(f"S3 {name}: a researched manifest is {manifest.get('status')!r}")
            if manifest.get("availability_class") != "unknown":
                failures.append(f"S3 {name}: research set an availability class")
            licensing = manifest["licensing"]
            if licensing["transitive_review"] == "passed" or any(
                licensing[d]["review_status"] == "passed" for d in ("software", "model", "data")
            ):
                failures.append(f"S3 {name}: research recorded a passed review")
    for item in run.snapshot["items"]:
        if item["verdict"] not in {"passed", "needs_review", "failed"}:
            failures.append(f"S3 {item['id']}: verdict {item['verdict']!r}")
    example = load_yaml_document((ROOT / "examples/example-research-snapshot.yaml").read_text())
    for item in example["items"]:
        if "approved" in json.dumps(item):
            failures.append(f"S3 example item {item['id']} mentions approval")
    return failures


def check_s4(run: Any) -> list[str]:
    failures: list[str] = []
    documents = [
        run.snapshot,
        load_yaml_document((ROOT / "examples/example-research-snapshot.yaml").read_text()),
    ]
    for document in documents:
        for item in document["items"]:
            for claim in item["claims"]:
                if claim.get("evidence_class") not in EVIDENCE_CLASSES:
                    failures.append(
                        f"S4 {item['id']}: claim {claim.get('field')!r} has no evidence class"
                    )
            if not item["claims"] and item["verdict"] != "failed":
                failures.append(f"S4 {item['id']}: an item with no claim reached {item['verdict']}")
        for pairing in document["pairings"]:
            if not pairing["claim_classes"] or set(pairing["claim_classes"]) - set(
                EVIDENCE_CLASSES
            ):
                failures.append(
                    f"S4 pairing {pairing['harness_item_id']}: classes {pairing['claim_classes']}"
                )
    return failures


def check_s5(run: Any) -> list[str]:
    failures: list[str] = []
    for item in run.snapshot["items"]:
        texts = [
            item["source_id"],
            *(str(c["value"]) for c in item["claims"] if isinstance(c["value"], str)),
        ]
        if item.get("family_token"):
            texts.append(str(item["family_token"]))
        for text in texts:
            if any(unicodedata.category(ch).startswith("C") for ch in text):
                failures.append(f"S5 {item['id']}: a control character in {text!r}")
            if forbidden_words(text):
                failures.append(f"S5 {item['id']}: forbidden word in {text!r}")
            if len(text) > IDENTIFIER_LIMIT:
                failures.append(f"S5 {item['id']}: {text[:30]!r} exceeds the identifier bound")
            if text.strip().casefold() in PLACEHOLDERS:
                failures.append(f"S5 {item['id']}: placeholder {text!r} stands in for a gap")
        for claim in item["claims"]:
            if (
                isinstance(claim["value"], str)
                and len(claim["value"]) > COLUMN_LIMIT
                and claim["field"]
                not in {
                    "revision",
                    "commit_id",
                    "release_digest",
                    "created_at",
                    "pushed_at",
                    "release_published_at",
                }
            ):
                failures.append(f"S5 {item['id']}: claim {claim['field']} exceeds the column bound")
    for artifact in run.manifests:
        manifest = json.loads(artifact.content)
        for text in _strings(manifest):
            if any(unicodedata.category(ch).startswith("C") for ch in text):
                failures.append(f"S5 {artifact.id}: a control character in a manifest string")
            if forbidden_words(text):
                failures.append(
                    f"S5 {artifact.id}: forbidden word {forbidden_words(text)} in a manifest string"
                )
            if text.strip().casefold() in PLACEHOLDERS - {"unknown"} and text != NOT_PUBLISHED:
                failures.append(f"S5 {artifact.id}: placeholder {text!r} in a manifest")
    return failures


def main() -> int:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    vocabulary = ResearchVocabularyLoader(ROOT / "catalogue").load()
    patterns = LocalCatalogue(ROOT / "catalogue", registry).load().patterns
    failures = check_s1()
    failures += check_s2(vocabulary, patterns)
    run = _normalised_output(vocabulary, patterns)
    registry.validate("research-snapshot.schema.json", run.snapshot)
    failures += check_s3(run)
    failures += check_s4(run)
    failures += check_s5(run)
    if failures:
        print("\n".join(failures))
        return 1
    print("Research guards S1-S5 passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
