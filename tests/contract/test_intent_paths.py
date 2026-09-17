# SPDX-License-Identifier: Apache-2.0
"""OAK-S9-004: the admissible intent paths are exactly the schema's typed leaves.

The checked-in tuple is what bounds a model proposal. If the intent schema gains a field,
this test fails until someone decides whether the model may populate it; if the tuple
gains a path the schema does not declare, it fails too.
"""

import json
from pathlib import Path

from oak.compiler.interpretation import SECTION_CONFIRMATION_TABLE, SPEC_SECTIONS
from oak.contracts import ADMISSIBLE_INTENT_PATHS, intent_section, is_admissible_intent_path
from oak.domain.intake import ClarificationQuestion

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_DATA_PATH = "/spec/data/extensions/oak.community~1production_data_permitted"


def _schema(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _schema_derived_paths() -> set[str]:
    schema = _schema("system-intent.schema.json")
    spec = schema["$defs"]["spec"]
    paths: set[str] = set()
    for section, reference in spec["properties"].items():
        definition = schema["$defs"][reference["$ref"].rsplit("/", 1)[1]]
        for field in definition["properties"]:
            if field != "extensions":
                paths.add(f"/spec/{section}/{field}")
    paths.add(PRODUCTION_DATA_PATH)
    return paths


def test_the_tuple_equals_the_schema_leaves_minus_extension_slots() -> None:
    assert set(ADMISSIBLE_INTENT_PATHS) == _schema_derived_paths()


def test_the_tuple_is_sorted_unique_and_index_free() -> None:
    assert list(ADMISSIBLE_INTENT_PATHS) == sorted(set(ADMISSIBLE_INTENT_PATHS))
    for path in ADMISSIBLE_INTENT_PATHS:
        assert path.startswith("/spec/"), path
        segments = path.split("/")[3:]
        assert segments, path
        assert not any(segment.isdigit() for segment in segments), path
        if "extensions" in segments:
            assert path == PRODUCTION_DATA_PATH
        assert is_admissible_intent_path(path)


def test_nothing_outside_the_typed_spec_is_admissible() -> None:
    for path in (
        "/spec",
        "/spec/",
        "/spec/purpose",
        "/spec/purpose/extensions",
        "/spec/purpose/extensions/oak.community~1anything",
        "/spec/purpose/desired_outcomes/0",
        "/spec/data/extensions",
        "/provenance/x",
        "/status",
        "spec/purpose/problem",
        "/spec/purpose/problem/",
        "/spec/purpose/../status",
    ):
        assert not is_admissible_intent_path(path), path


def test_every_section_has_a_confirmation_entry_with_valid_enums() -> None:
    assert set(SECTION_CONFIRMATION_TABLE) == set(SPEC_SECTIONS)
    assert {intent_section(path) for path in ADMISSIBLE_INTENT_PATHS} == set(SPEC_SECTIONS)
    case_question = _schema("design-case.schema.json")["$defs"]["question"]["properties"]
    intent_question = _schema("system-intent.schema.json")["properties"]["unresolved"]["items"][
        "properties"
    ]
    for section, entry in SECTION_CONFIRMATION_TABLE.items():
        assert entry.materiality in case_question["materiality"]["enum"], section
        assert entry.blocking_stage in case_question["blocking_stage"]["enum"], section
        assert entry.blocking_gate in intent_question["blocking_gate"]["enum"], section
        assert entry.question.endswith("."), section
        assert entry.reason.endswith("."), section
        question = ClarificationQuestion(
            id=f"question.model.{section}",
            path=f"/spec/{section}",
            question=entry.question,
            reason=entry.reason,
            materiality=entry.materiality,
            blocking_stage=entry.blocking_stage,
            blocking_gate=entry.blocking_gate,
        )
        # The presentation hint never reaches either serialized document.
        assert "rank_hint" not in question.case_document()
        assert "rank_hint" not in question.intent_document()
