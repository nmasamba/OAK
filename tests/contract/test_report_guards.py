# SPDX-License-Identifier: Apache-2.0
"""OAK-S13-002: each report guard bites. Every rule gets a planted violation it must catch.

The guards in `scripts/check_report.py` run over a live composition in `make validate`; a
guard that passes everything would pass that too. These tests plant one violation per
rule in the golden document (or the palette) and require the guard to name it.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

import pytest

from scripts import check_report
from tests.report_support import GOLDEN_REPORT


def _golden() -> dict[str, Any]:
    return json.loads(GOLDEN_REPORT.read_text(encoding="utf-8"))


def _section(document: dict[str, Any], identifier: str) -> dict[str, Any]:
    return next(item for item in document["sections"] if item["id"] == identifier)


def _first_quantity(document: dict[str, Any]) -> dict[str, Any]:
    table = next(b for b in _section(document, "comparison")["blocks"] if b["kind"] == "table")
    return table["rows"][0]["cells"][2]


def test_the_golden_passes_every_guard() -> None:
    document = _golden()
    assert check_report.guard_r1_words(document, "golden") == []
    assert check_report.guard_r2_numbers(document, "golden") == []
    assert check_report.guard_r3_pictures(document, "golden") == []
    assert check_report.guard_r4_contrast() == []


def _assurance_word(document: dict[str, Any]) -> None:
    _section(document, "cover")["subtitle"] = "A certified decision."


def _edition_word(document: dict[str, Any]) -> None:
    _section(document, "options")["title"] = "The Enterprise option wins"


def _raw_variant(document: dict[str, Any]) -> None:
    _first_quantity(document)["source"] = "candidate-03@0.1.0#/balanced_enterprise"


@pytest.mark.parametrize("plant", (_assurance_word, _edition_word, _raw_variant))
def test_r1_catches_forbidden_words(plant: Callable[[dict[str, Any]], None]) -> None:
    document = _golden()
    plant(document)
    assert check_report.guard_r1_words(document, "planted")


def _no_unit(document: dict[str, Any]) -> None:
    _first_quantity(document)["unit"] = ""


def _no_source(document: dict[str, Any]) -> None:
    _first_quantity(document)["source"] = "a guess"


def _unlabelled_synthetic(document: dict[str, Any]) -> None:
    _first_quantity(document)["basis"] = "estimated"


def _estimate_without_estimator(document: dict[str, Any]) -> None:
    quantity = _first_quantity(document)
    quantity["estimator"] = None
    quantity["basis"] = "estimated"


def _no_value(document: dict[str, Any]) -> None:
    _first_quantity(document)["value"] = None


def _unknown_without_reason(document: dict[str, Any]) -> None:
    table = next(b for b in _section(document, "risks")["blocks"] if b["kind"] == "table")
    table["rows"][1]["cells"][4]["reason"] = ""


def _bare_number(document: dict[str, Any]) -> None:
    _section(document, "options")["subtitle"] = "We looked at 4 options."


@pytest.mark.parametrize(
    "plant",
    (
        _no_unit,
        _no_source,
        _unlabelled_synthetic,
        _estimate_without_estimator,
        _no_value,
        _unknown_without_reason,
        _bare_number,
    ),
)
def test_r2_catches_numbers_without_their_unit_source_or_reason(
    plant: Callable[[dict[str, Any]], None],
) -> None:
    document = _golden()
    plant(document)
    assert check_report.guard_r2_numbers(document, "planted")


def test_r2_leaves_identifiers_versions_and_dates_alone() -> None:
    document = _golden()
    _section(document, "options")["subtitle"] = (
        "candidate-03 at 0.1.7 on 2026-08-18, see OAK-FR-CAT-001 and sha256:abc123."
    )
    assert check_report.guard_r2_numbers(document, "planted") == []


def _orphan_picture(document: dict[str, Any]) -> None:
    diagram = next(
        b for b in _section(document, "architecture")["blocks"] if b["kind"] == "diagram"
    )
    diagram["table_id"] = "nowhere"


def _table_missing_a_node(document: dict[str, Any]) -> None:
    section = _section(document, "architecture")
    table = next(
        b for b in section["blocks"] if b["kind"] == "table" and b["id"] == "topology-nodes"
    )
    table["rows"] = table["rows"][:1]


def _chart_missing_an_option(document: dict[str, Any]) -> None:
    table = next(
        b
        for b in _section(document, "comparison")["blocks"]
        if b["kind"] == "table" and b["id"] == "comparison"
    )
    table["columns"] = table["columns"][:-1]
    for row in table["rows"]:
        row["cells"] = row["cells"][:-1]


@pytest.mark.parametrize(
    "plant", (_orphan_picture, _table_missing_a_node, _chart_missing_an_option)
)
def test_r3_catches_a_picture_without_its_table(plant: Callable[[dict[str, Any]], None]) -> None:
    document = _golden()
    plant(document)
    assert check_report.guard_r3_pictures(document, "planted")


def test_r4_catches_a_text_pair_under_four_and_a_half(monkeypatch: pytest.MonkeyPatch) -> None:
    from oak.adapters.report import palette

    pairs = (*palette.TEXT_PAIRS, ("planted pale text", "#B0B0B0", "#FFFFFF"))
    monkeypatch.setattr(palette, "TEXT_PAIRS", pairs)
    failures = check_report.guard_r4_contrast()
    assert failures and "planted pale text" in failures[0]


def test_the_guards_are_run_over_every_recordable_step() -> None:
    reports = {stop: copy.deepcopy(_golden()) for stop in ("a", "b")}
    _section(reports["b"], "cover")["subtitle"] = "A certified decision."
    assert [failure.split()[1].split("/")[0] for failure in check_report.check(reports)] == ["b"]
