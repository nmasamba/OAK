# SPDX-License-Identifier: Apache-2.0
"""OAK-S13-002: the architecture report is composed from the case's records and nothing else.

The golden is the report for the reference case at `bundle_compiled`; the same case at
`candidate_selected` and `assurance_planned` exercises the "Not yet" states. Each section
is tested with its source record and without it: a missing record must say "Not yet" (or
that the case holds none), never fill the gap.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from oak.adapters.persistence import FileWorkspaceRepository
from oak.application.report import Narrative, ReportRecords, narrator_facts, report_document
from oak.application.report.composer import (
    INSTALL_STEPS,
    MAIN_SECTIONS,
    NO_UNIT,
    SHORTENED,
    _unit_for,
)
from oak.application.report.formatting import format_number
from oak.application.report.records import gather_records
from oak.application.report.topology import layout_topology
from oak.contracts import SchemaRegistry, load_yaml_document
from oak.domain import canonical_json_bytes
from tests.report_support import (
    FIXED_CLOCK,
    FIXED_RENDERER,
    GOLDEN_REPORT,
    STOPS,
    build_reference_case,
)

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = SchemaRegistry.from_directory(ROOT / "schemas")


@pytest.fixture(scope="module")
def reference(tmp_path_factory: pytest.TempPathFactory) -> dict[str, ReportRecords]:
    records = {}
    for stop in STOPS:
        workspace = build_reference_case(tmp_path_factory.mktemp(stop), stop)
        records[stop] = gather_records(FileWorkspaceRepository(workspace, REGISTRY))
    return records


def compose(records: ReportRecords, **overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "report_id": f"report.public-manual-qa.from-{records.case['version']}",
        "generated_at": FIXED_CLOCK,
        "generated_by": "local-user",
        "oak_version": "0.9.0",
        "renderer": FIXED_RENDERER,
    }
    arguments.update(overrides)
    document = report_document(records, **arguments)
    REGISTRY.validate("architecture-report.schema.json", document)
    return document


def section(document: dict[str, Any], identifier: str) -> dict[str, Any]:
    return next(item for item in document["sections"] if item["id"] == identifier)


def blocks(document: dict[str, Any], identifier: str, kind: str) -> list[dict[str, Any]]:
    return [block for block in section(document, identifier)["blocks"] if block["kind"] == kind]


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in strings(item)]
    return []


def facts(document: dict[str, Any], identifier: str) -> dict[str, dict[str, Any]]:
    return {
        item["label"]: item["value"]
        for block in blocks(document, identifier, "facts")
        for item in block["items"]
    }


# ----- the whole document --------------------------------------------------------------


def test_the_reference_report_matches_its_golden_byte_for_byte(
    reference: dict[str, ReportRecords],
) -> None:
    golden = json.loads(GOLDEN_REPORT.read_text(encoding="utf-8"))
    composed = compose(reference["bundle_compiled"])
    assert canonical_json_bytes(composed) == canonical_json_bytes(golden)
    assert canonical_json_bytes(compose(reference["bundle_compiled"])) == canonical_json_bytes(
        composed
    )


def test_the_published_example_is_the_golden() -> None:
    example = load_yaml_document((ROOT / "examples/example-architecture-report.yaml").read_text())
    assert example == json.loads(GOLDEN_REPORT.read_text(encoding="utf-8"))


@pytest.mark.parametrize("stop", STOPS)
def test_every_recordable_step_gives_twenty_sections_in_order(
    reference: dict[str, ReportRecords], stop: str
) -> None:
    document = compose(reference[stop])
    assert [item["number"] for item in document["sections"]] == [
        *MAIN_SECTIONS,
        *"ABCDEF",
    ]
    assert document["case_status"] == stop
    assert document["case_ref"]["version"] == reference[stop].case["version"]


@pytest.mark.parametrize("stop", STOPS)
def test_titles_and_template_sentences_follow_the_copy_rules(
    reference: dict[str, ReportRecords], stop: str
) -> None:
    document = compose(reference[stop])
    for item in document["sections"]:
        assert len(item["title"].split()) <= 12, item["title"]
        template = [item["subtitle"]] + [
            block["text"]
            for block in item["blocks"]
            if block.get("source") == "template" and isinstance(block.get("text"), str)
        ]
        for text in template:
            for sentence in re.split(r"(?<=[.;])\s+", text):
                assert len(sentence.split()) <= 20, sentence


def test_a_report_before_candidate_selected_is_refused(
    reference: dict[str, ReportRecords],
) -> None:
    records = reference["candidate_selected"]
    early = replace(records, case={**records.case, "status": "candidates_ready"})
    with pytest.raises(ValueError, match="candidate_selected"):
        compose(early)


def test_the_brief_document_is_never_embedded(reference: dict[str, ReportRecords]) -> None:
    document = compose(reference["bundle_compiled"])
    brief = (ROOT / "examples/briefs/public-manual-qa.yaml").read_text(encoding="utf-8")
    text = "\n".join(strings(document))
    assert brief not in text
    assert "kind: " not in text and "schema_version: " not in text
    assert all(item["kind"] != "brief_source" for item in document["inputs"])
    assert all(item["kind"] != "source_record" for item in document["inputs"])


def test_every_input_the_composer_read_is_listed_in_the_record(
    reference: dict[str, ReportRecords],
) -> None:
    records = reference["bundle_compiled"]
    document = compose(records)
    listed = {(item["id"], item["version"]) for item in document["inputs"]}
    assert (records.case["id"], records.case["version"]) in listed
    assert ("candidate-03", "0.1.0") in listed
    assert ("decision.candidate-03", "0.1.0") in listed
    assert ("component.fixture-local-model", "1.0.0") in listed
    rows = blocks(document, "appendix-record", "table")[0]["rows"]
    assert len(rows) == len(document["inputs"])


# ----- sections ------------------------------------------------------------------------


def test_cover_states_the_recommendation_and_quotes_the_owner(
    reference: dict[str, ReportRecords],
) -> None:
    document = compose(reference["bundle_compiled"])
    cover = section(document, "cover")
    assert (
        cover["title"] == "Cited answers over public technical manuals: build the Balanced design"
    )
    callouts = {block["label"]: block["text"] for block in blocks(document, "cover", "callout")}
    assert callouts == {
        "Recommended": "Balanced (candidate-03)",
        "Baseline beside it": "Baseline (candidate-00)",
    }
    quote = blocks(document, "cover", "quote")[0]
    assert (quote["label"], quote["text"]) == ("The owner's rationale", "balanced")
    assert quote["source"] == "decision.candidate-03@0.1.0#/rationale"


def test_cover_without_a_decision_or_stakeholders_says_so(
    reference: dict[str, ReportRecords],
) -> None:
    records = reference["bundle_compiled"]
    intent = copy.deepcopy(records.intent)
    intent["spec"]["stakeholders"] = {}
    document = compose(replace(records, decision=None, intent=intent))
    assert blocks(document, "cover", "quote") == []
    assert facts(document, "cover")["Prepared for"]["type"] == "unknown"


def test_method_says_how_the_brief_was_read(reference: dict[str, ReportRecords]) -> None:
    records = reference["bundle_compiled"]
    plain = facts(compose(records), "method")
    assert "No model was used" in plain["How the brief was read"]["text"]
    assert plain["Answers a person gave"]["text"] == "5 answers"
    intent = copy.deepcopy(records.intent)
    intent["extensions"]["oak.community/interpretation_proposal_ref"] = dict(records.case_ref)
    proposal = {"extensions": {"oak.community/model": {"model_id": "example/model"}}}
    modelled = facts(compose(replace(records, intent=intent, proposal=proposal)), "method")
    assert "A model (example/model) proposed values" in modelled["How the brief was read"]["text"]
    without_snapshot = facts(compose(replace(records, snapshot=None)), "method")
    assert without_snapshot["Catalogue snapshot"]["type"] == "unknown"


def test_what_was_asked_marks_every_value_and_names_what_is_missing(
    reference: dict[str, ReportRecords],
) -> None:
    records = reference["bundle_compiled"]
    table = blocks(compose(records), "asked", "table")[0]
    memory = next(row for row in table["rows"] if row["cells"][0]["text"] == "Memory")
    assert memory["cells"][1]["type"] == "quantity"
    assert (memory["cells"][1]["value"], memory["cells"][1]["unit"]) == (32, "GiB")
    assert memory["cells"][1]["basis"] == "confirmed"
    assert memory["cells"][2]["text"] == "Fact from brief, confirmed"
    intent = copy.deepcopy(records.intent)
    intent["spec"]["hardware"] = {}
    for pointer in list(intent["provenance"]):
        if pointer.startswith("/spec/decision/autonomy"):
            intent["provenance"][pointer] = {
                **intent["provenance"][pointer],
                "confirmed_by": None,
                "confirmation_required": True,
            }
    changed = compose(replace(records, intent=intent))
    rows = blocks(changed, "asked", "table")[0]["rows"]
    memory = next(row for row in rows if row["cells"][0]["text"] == "Memory")
    assert memory["cells"][1] == {"type": "unknown", "reason": "The brief does not state it."}
    assert section(changed, "asked")["title"] == "One value still waits for a person's confirmation"
    unstated = copy.deepcopy(records.intent)
    unstated["spec"]["hardware"] = {"cpu_architectures": ["x86_64"]}
    title = section(compose(replace(records, intent=unstated)), "asked")["title"]
    assert title == "Two values are not stated in the brief"


def test_every_numeric_intent_field_has_a_unit() -> None:
    schema = json.loads((ROOT / "schemas/system-intent.schema.json").read_text())
    numeric: list[str] = []

    def walk(node: Any, name: str) -> None:
        if isinstance(node, dict):
            kinds = node.get("type")
            kinds = kinds if isinstance(kinds, list) else [kinds]
            if name and ({"number", "integer"} & set(kinds)):
                numeric.append(name)
            for key, child in (node.get("properties") or {}).items():
                walk(child, key)
            for key in ("items", "$defs", "definitions"):
                child = node.get(key)
                if isinstance(child, dict) and key == "items":
                    walk(child, name)
                elif isinstance(child, dict):
                    for inner in child.values():
                        walk(inner, "")

    walk(schema, "")
    assert {"latency_p95_ms", "expected_users", "team_size"} <= set(numeric)
    assert [name for name in numeric if _unit_for(name) is None] == []


def test_a_number_without_a_unit_stays_unknown(reference: dict[str, ReportRecords]) -> None:
    records = reference["bundle_compiled"]
    candidates = copy.deepcopy(list(records.candidates))
    for candidate in candidates:
        for objective in candidate["objectives"]:
            if objective["name"] == "latency_p95":
                objective["unit"] = ""
    document = compose(replace(records, candidates=tuple(candidates)))
    table = blocks(document, "comparison", "table")[0]
    latency = next(row for row in table["rows"] if row["cells"][0]["text"] == "Latency p95")
    assert latency["cells"][1]["text"] == "no unit recorded, lower is better"
    assert {cell["reason"] for cell in latency["cells"][2:]} == {NO_UNIT}
    assert "as recorded" not in json.dumps(document)


def test_long_record_text_fits_and_says_it_was_shortened(
    reference: dict[str, ReportRecords],
) -> None:
    records = reference["bundle_compiled"]
    decision = {**(records.decision or {}), "rationale": "Because. " * 1333 + "End"}
    assert len(decision["rationale"]) <= 12000
    document = compose(replace(records, decision=decision))
    quotes = [block["text"] for block in blocks(document, "recommendation", "quote")]
    assert decision["rationale"] in quotes
    candidates = copy.deepcopy(list(records.candidates))
    candidates[-1]["rejection_reasons"] = ["Too slow. " * 150]
    reasons = [
        item
        for value in strings(compose(replace(records, candidates=tuple(candidates))))
        for item in [value]
        if item.endswith(SHORTENED)
    ]
    assert reasons and all(len(item) <= 1000 for item in reasons)


def test_options_lists_the_baseline_first_and_why_each_lost(
    reference: dict[str, ReportRecords],
) -> None:
    document = compose(reference["bundle_compiled"])
    rows = blocks(document, "options", "table")[0]["rows"]
    assert [row["cells"][0]["text"] for row in rows] == [
        "Baseline (candidate-00)",
        "Minimal (candidate-01)",
        "Balanced (candidate-03)",
        "High assurance (candidate-04)",
    ]
    assert [row["cells"][1]["word"] for row in rows] == [
        "On the frontier",
        "On the frontier",
        "Selected",
        "Infeasible",
    ]
    assert section(document, "options")["title"] == "Four options considered; one cannot be built"
    without_patterns = compose(replace(reference["bundle_compiled"], patterns={}))
    first = blocks(without_patterns, "options", "table")[0]["rows"][0]
    assert first["cells"][2]["type"] == "unknown"


def test_risks_matrix_keeps_unknown_unknown_with_its_reason(
    reference: dict[str, ReportRecords],
) -> None:
    document = compose(reference["bundle_compiled"])
    matrix = blocks(document, "risks", "table")[0]
    hardware = next(row for row in matrix["rows"] if row["cells"][0]["text"] == "Hardware")
    high_assurance = hardware["cells"][4]
    assert high_assurance["status"] == "unknown"
    assert high_assurance["reason"] == "Required accelerator compatibility is unconfirmed."
    assert section(document, "risks")["title"] == (
        "One option fails or leaves a hard constraint unknown"
    )
    records = reference["bundle_compiled"]
    clean = [
        {
            **candidate,
            "hard_constraints": [
                {**item, "result": "pass", "reason": "ok"} for item in candidate["hard_constraints"]
            ],
        }
        for candidate in records.candidates
    ]
    assert section(compose(replace(records, candidates=tuple(clean))), "risks")["title"] == (
        "No option fails or leaves a hard constraint unknown"
    )


def test_comparison_draws_every_range_and_tables_the_same_numbers(
    reference: dict[str, ReportRecords],
) -> None:
    document = compose(reference["bundle_compiled"])
    chart = blocks(document, "comparison", "chart")[0]
    table = next(t for t in blocks(document, "comparison", "table") if t["id"] == chart["table_id"])
    cost = next(row for row in table["rows"] if row["cells"][0]["text"] == "Monthly cost")
    balanced = cost["cells"][4]
    assert balanced["basis"] == "synthetic estimate"
    assert balanced["estimator"] == "fixture-cost-1.0.0"
    assert (balanced["value"], balanced["lower"], balanced["upper"]) == (36.0, 32.4, 39.6)
    assert balanced["short"] == "36 (32.4 to 39.6)"
    assert table["display"] == "short"
    bars = next(series for series in chart["series"] if series["objective"] == "Monthly cost")
    assert [bar["label"] for bar in bars["bars"]] == [
        "Baseline",
        "Minimal",
        "Balanced",
        "High assurance",
    ]
    assert "synthetic estimate" in section(document, "comparison")["subtitle"]


def test_comparison_without_an_objective_says_unknown(reference: dict[str, ReportRecords]) -> None:
    records = reference["bundle_compiled"]
    stripped = [
        {**candidate, "objectives": [o for o in candidate["objectives"] if o["name"] != "energy"]}
        if candidate["id"] == "candidate-00"
        else candidate
        for candidate in records.candidates
    ]
    document = compose(replace(records, candidates=tuple(stripped)))
    table = blocks(document, "comparison", "table")[0]
    energy = next(row for row in table["rows"] if row["cells"][0]["text"] == "Energy")
    assert energy["cells"][2]["type"] == "unknown"


def test_recommendation_names_the_decider_and_every_alternative(
    reference: dict[str, ReportRecords],
) -> None:
    document = compose(reference["bundle_compiled"])
    assert section(document, "recommendation")["title"] == (
        "The owner chose Balanced over three alternatives"
    )
    alternatives = next(
        t for t in blocks(document, "recommendation", "table") if t["id"] == "alternatives"
    )
    assert len(alternatives["rows"]) == 3
    assert facts(document, "recommendation")["Decided by"]["text"] == "local-user"
    without = compose(replace(reference["bundle_compiled"], decision=None))
    waiting = blocks(without, "recommendation", "not_yet")
    assert waiting and waiting[0]["step"] == "Select a candidate"


def test_cost_sets_the_selected_beside_the_baseline_and_estimates_no_benefit(
    reference: dict[str, ReportRecords],
) -> None:
    document = compose(reference["bundle_compiled"])
    rows = blocks(document, "cost", "table")[0]["rows"]
    assert [row["cells"][0]["text"] for row in rows] == [
        "Balanced (candidate-03)",
        "Baseline (candidate-00)",
    ]
    callout = blocks(document, "cost", "callout")[0]
    assert callout["label"] == "Benefit not estimated"
    assert section(document, "cost")["title"] == (
        "Balanced is estimated to cost more than the baseline per month"
    )
    model = load_yaml_document((ROOT / "examples/example-decision-cost-model.yaml").read_text())
    with_model = compose(replace(reference["bundle_compiled"], cost_model=model))
    assert blocks(with_model, "cost", "callout") == []
    outcomes = [t for t in blocks(with_model, "cost", "table") if t["id"] == "decision-cost"]
    assert outcomes and all(row["cells"][2]["type"] == "quantity" for row in outcomes[0]["rows"])


def test_architecture_draws_the_workspace_layout_and_waits_for_the_bundle(
    reference: dict[str, ReportRecords],
) -> None:
    compiled = compose(reference["bundle_compiled"])
    diagram = blocks(compiled, "architecture", "diagram")[0]
    selected = next(c for c in reference["bundle_compiled"].candidates if c["id"] == "candidate-03")
    expected = layout_topology(selected["topology"])
    assert (diagram["nodes"], diagram["edges"]) == (expected["nodes"], expected["edges"])
    assert (diagram["width"], diagram["height"]) == (544, 120)
    assert any(
        t["id"] == "components" and t["caption"] == "Components as compiled"
        for t in blocks(compiled, "architecture", "table")
    )
    assert facts(compiled, "architecture")["Network mode"]["text"] == "isolated-no-egress"
    early = compose(reference["candidate_selected"])
    assert section(early, "architecture")["state"] == "partial"
    assert blocks(early, "architecture", "not_yet")[0]["step"] == "Compile the bundle"
    designed = next(t for t in blocks(early, "architecture", "table") if t["id"] == "components")
    assert designed["caption"] == "Components as designed"


def test_security_names_secrets_by_name_and_says_what_the_case_lacks(
    reference: dict[str, ReportRecords],
) -> None:
    records = reference["bundle_compiled"]
    document = compose(records)
    assert section(document, "security")["title"] == (
        "Public data only; production data is not permitted"
    )
    assert facts(document, "security")["Secret references, by name only"]["text"] == "None."
    bundle = copy.deepcopy(records.bundle)
    assert bundle is not None
    bundle["secret_references"] = [{"name": "registry-token", "value": "never-shown"}]
    named = compose(replace(records, bundle=bundle))
    assert facts(named, "security")["Secret references, by name only"]["items"] == [
        "registry-token"
    ]
    assert "never-shown" not in "\n".join(strings(named))
    nexus = load_yaml_document((ROOT / "examples/example-regulatory-nexus.yaml").read_text())
    policy = load_yaml_document((ROOT / "examples/example-policy-decision.yaml").read_text())
    full = compose(replace(records, regulatory_nexus=nexus, policy_decisions=(policy,)))
    assert facts(full, "security")["Regulatory nexus"]["text"] == (
        "nexus.public-manual-qa: review_required"
    )
    assert any(t["id"] == "policy" for t in blocks(full, "security", "table"))
    early = compose(reference["candidate_selected"])
    assert blocks(early, "security", "not_yet")[0]["what"] == (
        "The network mode and secret references"
    )


def test_governance_reports_gates_blockers_and_approval_states(
    reference: dict[str, ReportRecords],
) -> None:
    records = reference["bundle_compiled"]
    document = compose(records)
    assert section(document, "governance")["title"] == "One gate is blocked before any install"
    approvals = next(t for t in blocks(document, "governance", "table") if t["id"] == "approvals")
    assert [row["cells"][1]["word"] for row in approvals["rows"]] == ["absent", "absent"]
    live = {
        "id": "approval.architecture.x",
        "version": "0.1.0",
        "revoked": False,
        "expires_at": "2026-08-19T12:00:00Z",
    }
    stale = {
        "id": "approval.apply.x",
        "version": "0.1.0",
        "revoked": False,
        "expires_at": "2026-08-17T12:00:00Z",
    }
    approved = compose(replace(records, approvals={"architecture": live, "apply": stale}))
    table = next(t for t in blocks(approved, "governance", "table") if t["id"] == "approvals")
    assert [row["cells"][1]["word"] for row in table["rows"]] == ["current", "expired"]
    revoked = compose(replace(records, approvals={"architecture": {**live, "revoked": True}}))
    table = next(t for t in blocks(revoked, "governance", "table") if t["id"] == "approvals")
    assert table["rows"][0]["cells"][1]["word"] == "revoked"
    early = compose(reference["candidate_selected"])
    waiting = blocks(early, "governance", "not_yet")
    assert [block["step"] for block in waiting] == ["Plan assurance", "Compile the bundle"]


def test_evidence_shows_metrics_and_waits_for_observations(
    reference: dict[str, ReportRecords],
) -> None:
    records = reference["bundle_compiled"]
    document = compose(records)
    metrics = blocks(document, "evidence", "table")[0]
    citation = metrics["rows"][0]["cells"]
    # The offline evaluation ran over a fixture set: its value and sample are synthetic.
    assert (citation[1]["value"], citation[1]["basis"]) == (0.99, "synthetic estimate")
    assert citation[1]["estimator"] == "public-manual-qa-evaluation-1.0.0"
    assert (citation[3]["value"], citation[3]["unit"]) == (0.98, "proportion")
    assert (citation[4]["text"], citation[4]["basis"]) == ("100 cases", "synthetic estimate")
    assert blocks(document, "evidence", "not_yet")[0]["step"] == "Install, then observe"
    observation = load_yaml_document(
        (ROOT / "examples/example-observation-record.yaml").read_text()
    )
    observed = compose(replace(records, observations=(observation,)))
    calibration = next(t for t in blocks(observed, "evidence", "table") if t["id"] == "calibration")
    assert calibration["rows"][0]["cells"][2]["type"] == "unknown"
    assert blocks(observed, "evidence", "not_yet") == []
    unevaluated = compose(replace(records, evaluations=()))
    assert section(unevaluated, "evidence")["title"] == "The selected design is not evaluated yet"


def test_what_would_change_this_lists_open_questions_and_uncertainties(
    reference: dict[str, ReportRecords],
) -> None:
    records = reference["bundle_compiled"]
    assert section(compose(records), "sensitivity")["title"] == (
        "No open questions and no uncertainties remain"
    )
    intent = copy.deepcopy(records.intent)
    intent["unresolved"][0] = {**intent["unresolved"][0], "status": "open"}
    selected = [copy.deepcopy(candidate) for candidate in records.candidates]
    for candidate in selected:
        if candidate["id"] == "candidate-03":
            candidate["extensions"]["oak.community/explanation"]["uncertainties"] = [
                {"constraint_id": "constraint.hardware", "reason": "Not measured."}
            ]
    changed = compose(replace(records, intent=intent, candidates=tuple(selected)))
    assert section(changed, "sensitivity")["title"] == (
        "One open question and one uncertainty remain"
    )
    assert facts(changed, "sensitivity")["Uncertainties"]["items"] == ["Hardware: Not measured."]


@pytest.mark.parametrize(
    ("status", "first", "count"),
    (
        ("candidate_selected", "oak assure candidate-03", 8),
        ("assurance_planned", "oak plan candidate-03 --target <profile>", 7),
        ("bundle_compiled", "oak sign", 6),
        ("deployment_approved", "oak dispatch apply", 3),
        ("deployed", "oak observe", 1),
        ("observing", "oak observe", 1),
    ),
)
def test_next_steps_follow_the_case_status(
    reference: dict[str, ReportRecords], status: str, first: str, count: int
) -> None:
    records = reference["bundle_compiled"]
    document = compose(replace(records, case={**records.case, "status": status}))
    lines = blocks(document, "next-steps", "commands")[0]["lines"]
    assert (lines[0], len(lines)) == (first, count)
    assert set(INSTALL_STEPS) & set(lines) <= set(INSTALL_STEPS)


def test_appendix_a_lists_only_values_not_stated_in_the_brief(
    reference: dict[str, ReportRecords],
) -> None:
    document = compose(reference["bundle_compiled"])
    rows = blocks(document, "appendix-assumptions", "table")[0]["rows"]
    fields = [row["cells"][0]["text"] for row in rows]
    assert fields == [
        "/spec/data/volume",
        "/spec/decision/task_types/0",
        "/spec/decision/task_types/1",
        "/spec/domain/setting",
    ]
    assert rows[0]["cells"][3]["text"] == "local-user, 2026-08-18 12:00 UTC"
    intent = copy.deepcopy(reference["bundle_compiled"].intent)
    intent["provenance"] = {
        pointer: {**entry, "source": "explicit"} for pointer, entry in intent["provenance"].items()
    }
    case = {**reference["bundle_compiled"].case, "assumptions": []}
    plain = compose(replace(reference["bundle_compiled"], intent=intent, case=case))
    assert blocks(plain, "appendix-assumptions", "paragraph")[0]["text"] == (
        "Every value is a fact stated in the brief."
    )


def test_appendix_b_flags_each_option(reference: dict[str, ReportRecords]) -> None:
    document = compose(reference["bundle_compiled"])
    cards = blocks(document, "appendix-candidates", "facts")
    assert [card["heading"] for card in cards][2] == "Balanced (candidate-03)"
    flags = [card["items"][0]["value"]["word"] for card in cards]
    assert flags == ["On the frontier", "On the frontier", "Selected", "Infeasible"]
    balanced = {item["label"]: item["value"] for item in cards[2]["items"]}
    assert balanced["Best of the feasible options on"]["items"] == ["quality"]


def test_appendix_c_records_the_decision_and_waits_for_assurance(
    reference: dict[str, ReportRecords],
) -> None:
    document = compose(reference["bundle_compiled"])
    record = facts(document, "appendix-controls")
    assert record["Decision"]["text"] == "Balanced (candidate-03): balanced"
    assert len(record["Consequences, as the records it depends on"]["items"]) == 4
    early = compose(reference["candidate_selected"])
    assert blocks(early, "appendix-controls", "not_yet")[0]["step"] == "Plan assurance"


def test_appendix_d_groups_each_estimator_once(reference: dict[str, ReportRecords]) -> None:
    document = compose(reference["bundle_compiled"])
    estimators = blocks(document, "appendix-estimates", "table")[0]
    assert [row["cells"][2]["text"] for row in estimators["rows"]] == [
        "fixture-cost-1.0.0",
        "fixture-latency-1.0.0",
        "fixture-quality-1.0.0",
        "fixture-operability-1.0.0",
        "fixture-energy-1.0.0",
    ]
    assert section(document, "appendix-estimates")["title"] == (
        "Every figure is a synthetic estimate from a fixture estimator"
    )


def test_fixture_components_inputs_and_measurements_are_synthetic(
    reference: dict[str, ReportRecords],
) -> None:
    records = reference["bundle_compiled"]
    inputs = next(
        table
        for table in blocks(compose(records), "appendix-estimates", "table")
        if table["id"] == "component-inputs"
    )
    values = [row["cells"][2] for row in inputs["rows"]]
    assert values and {value["basis"] for value in values} == {"synthetic estimate"}
    assert all(value["estimator"] for value in values)
    evaluations = tuple(
        {**evaluation, "fixture_version": "", "limitations": []}
        for evaluation in records.evaluations
    )
    measured = blocks(compose(replace(records, evaluations=evaluations)), "evidence", "table")[0]
    assert measured["rows"][0]["cells"][1]["basis"] == "measured"


def test_appendix_e_lists_evidence_and_the_snapshot(reference: dict[str, ReportRecords]) -> None:
    document = compose(reference["bundle_compiled"])
    evidence = blocks(document, "appendix-evidence", "table")[0]
    assert {row["cells"][0]["text"] for row in evidence["rows"]} == {
        "Synthetic lexical component declaration",
        "Synthetic local model declaration",
    }
    headings = [block["heading"] for block in blocks(document, "appendix-evidence", "facts")]
    assert "The catalogue snapshot" in headings
    without = compose(replace(reference["bundle_compiled"], snapshot=None))
    headings = [block["heading"] for block in blocks(without, "appendix-evidence", "facts")]
    assert "The catalogue snapshot" not in headings


# ----- notes a model proposed ------------------------------------------------------------


def test_notes_sit_on_main_slides_under_their_label_and_nowhere_else(
    reference: dict[str, ReportRecords],
) -> None:
    reference_ref = {
        "id": "narrative.public-manual-qa.from-0.1.7",
        "version": "0.1.0",
        "digest": "sha256:" + "a" * 64,
        "media_type": None,
        "uri": None,
    }
    narrative = Narrative(
        mode="online",
        narrative_ref=reference_ref,
        model="example-org/example-model",
        notes={"7": "The owner chose the balanced design.", "A": "never placed"},
    )
    document = compose(reference["bundle_compiled"], narrative=narrative)
    noted = [item for item in document["sections"] if item["note"] is not None]
    assert [item["number"] for item in noted] == ["7"]
    assert noted[0]["note"] == {
        "text": "The owner chose the balanced design.",
        "label": "Proposed by model",
        "model": "example-org/example-model",
        "source": "narrative.public-manual-qa.from-0.1.7@0.1.0#/notes",
    }
    assert document["narrative"]["mode"] == "online"
    assert "No model wrote it" not in "\n".join(strings(section(document, "method")))
    plain = compose(reference["bundle_compiled"])
    assert all(item["note"] is None for item in plain["sections"])
    assert plain["narrative"] == {
        "mode": "deterministic",
        "narrative_ref": None,
        "label": None,
        "model": None,
    }


def test_the_model_is_shown_only_the_main_slides_words(
    reference: dict[str, ReportRecords],
) -> None:
    document = compose(reference["bundle_compiled"])
    shown = narrator_facts(document)
    assert [slide["section"] for slide in shown["slides"]] == list(MAIN_SECTIONS)
    text = json.dumps(shown)
    assert "sha256:" not in text
    assert "The records this report was composed from" not in text
    assert "Every value not stated in the brief" not in text


# ----- shared pieces -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "shown"),
    (
        (36.0, "36"),
        (32.4, "32.4"),
        (1200.0, "1,200"),
        (0.511, "0.511"),
        (487.5, "488"),
        (812.5, "813"),
        (1.316, "1.32"),
        (2.444, "2.44"),
        (0, "0"),
        (12345, "12,300"),
        (0.0001234, "0.000123"),
        (-5.55, "-5.55"),
        (None, "unknown"),
    ),
)
def test_numbers_read_as_the_web_shows_them(value: float | int | None, shown: str) -> None:
    assert format_number(value) == shown


def test_the_topology_port_lays_out_the_reference_candidate() -> None:
    topology = {
        "nodes": [
            {"id": "node.retrieval", "role": "Retrieval", "component_ref": "a@1"},
            {"id": "node.generation", "role": "Drafting", "component_ref": "b@1"},
        ],
        "edges": [{"from": "node.retrieval", "to": "node.generation", "interface": "HTTP"}],
    }
    layout = layout_topology(topology)
    assert [(node["id"], node["x"], node["y"]) for node in layout["nodes"]] == [
        ("node.retrieval", 24, 24),
        ("node.generation", 320, 24),
    ]
    assert [(e["x1"], e["y1"], e["x2"], e["y2"]) for e in layout["edges"]] == [(224, 60, 320, 60)]
    assert (layout["width"], layout["height"]) == (544, 120)
    cycle = layout_topology(
        {
            "nodes": [{"id": "a", "role": "A"}, {"id": "b", "role": "B"}],
            "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}, {"from": "a", "to": "z"}],
        }
    )
    assert len(cycle["edges"]) == 2
    assert layout_topology({})["description"] == "No nodes."


# ----- Sprint 14, K4: an unknown objective shows its own reason ---------------------------


def _unknown_cells(value: Any, found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if value.get("type") == "unknown":
            found.append(value)
        for child in value.values():
            _unknown_cells(child, found)
    elif isinstance(value, list):
        for child in value:
            _unknown_cells(child, found)
    return found


def test_an_unknown_objective_shows_its_own_reason_with_its_unit(
    reference: dict[str, ReportRecords],
) -> None:
    records = reference["bundle_compiled"]
    candidates = copy.deepcopy(records.candidates)
    target = next(candidate for candidate in candidates if candidate["id"] == "candidate-04")
    objective = next(item for item in target["objectives"] if item["name"] == "energy")
    reason = "No energy figure is published for component.research.fixture."
    objective.update(
        {"value": None, "lower": None, "upper": None, "confidence": 0.0, "unknown_reason": reason}
    )

    document = compose(replace(records, candidates=tuple(candidates)))

    unknowns = [cell for cell in _unknown_cells(document, []) if cell["reason"] == reason]
    assert unknowns, "the objective's own reason never reached the report"
    assert all(cell["unit"] == "Wh/request" for cell in unknowns)
    assert NO_UNIT not in {cell["reason"] for cell in unknowns}
    chart = next(block for block in blocks(document, "comparison", "chart"))
    energy = next(series for series in chart["series"] if series["objective"] == "Energy")
    assert "High assurance" not in {bar["label"] for bar in energy["bars"]}
    assert len(energy["bars"]) == len(candidates) - 1
