# SPDX-License-Identifier: Apache-2.0
"""The architecture report, composed from a design case's own records.

`report_document` is a pure function: the same records, versions and recording context
give the same document, byte for byte once canonicalised. Every value it writes names
the record it came from (`<id>@<version>#<JSON pointer>`), and every number is a
quantity with its unit, basis and source. A record the case does not hold yet becomes a
"Not yet" block naming the step that produces it; a record the case will never hold
unless someone adds one (a decision cost model, a regulatory nexus) says the case holds
none. Nothing here invents a value, ranks by a hidden score or claims an approval: the
report authorizes nothing.

Template text is plain English, with titles of twelve words or fewer and sentences of
twenty or fewer. Counts in a title or sentence are words, so that no bare number appears
without its unit and source. Notes a model proposed are passed in already checked and are
quoted on their slide under their own label, beside the template text.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from oak.application.report.formatting import format_number, format_unit
from oak.application.report.labels import (
    PROVENANCE_WORDS,
    candidate_label,
    count_words,
    humanise,
    is_baseline,
)
from oak.application.report.topology import layout_topology

COMPOSER_VERSION = "oak-report-composer-1.0.0"
SCHEMA_VERSION = "0.1.0"
TEMPLATE = "template"
NOTE_LABEL = "Proposed by model"
# The six commands the workspace's "Copy install steps" copies; a contract test keeps the
# two lists equal. The report shows them as text and runs nothing.
INSTALL_STEPS = (
    "oak sign",
    "oak approve architecture",
    "oak approve apply",
    "oak dispatch apply",
    "oak-runner run-once",
    "oak ingest",
)
RECORDABLE_STATUSES = (
    "candidate_selected",
    "assurance_planned",
    "bundle_compiled",
    "deployment_approved",
    "deployed",
    "observing",
)
MAIN_SECTIONS = tuple(str(number) for number in range(1, 15))
_DIGEST = re.compile(r"\bsha(?:256|512):[0-9A-Fa-f]+")
PROPOSAL_REF_EXTENSION = "oak.community/interpretation_proposal_ref"
CONFIRMATIONS_EXTENSION = "oak.community/confirmations"
EXPLANATION_EXTENSION = "oak.community/explanation"
PATTERN_REF_EXTENSION = "oak.community/pattern_ref"
ESTIMATOR_EXTENSION = "oak.community/estimator_metadata"
MODEL_EXTENSION = "oak.community/model"
COMPONENT_OBJECTIVES_EXTENSION = "oak.community/objectives"
OBJECTIVE_NAMES = {
    "monthly_cost": "Monthly cost",
    "latency_p95": "Latency p95",
    "quality": "Quality",
    "operability": "Operability",
    "energy": "Energy",
}
COMPONENT_INPUT_LABELS = {
    "monthly_cost_usd": "Monthly cost",
    "latency_p95_ms": "Latency p95",
    "energy_wh": "Energy",
    "quality_score": "Quality",
    "operability_score": "Operability",
}
COMPONENT_INPUT_UNITS = {
    "monthly_cost_usd": "USD/month",
    "latency_p95_ms": "milliseconds",
    "energy_wh": "Wh/request",
    "quality_score": "normalized fixture score",
    "operability_score": "normalized fixture score",
}
UNIT_SUFFIXES = (
    ("_gib", "GiB"),
    ("_gb", "GB"),
    ("_mb", "MB"),
    ("_ms", "milliseconds"),
    ("_per_second", "per second"),
    ("_seconds", "seconds"),
    ("_hours", "hours"),
    ("_months", "months"),
    ("_percent", "%"),
    ("_watts", "watts"),
    ("_usd", "USD"),
)
# Intent fields whose name carries no unit suffix but whose unit the schema fixes.
FIELD_UNITS = {
    "concurrency": "concurrent requests",
    "expected_users": "users",
    "team_size": "people",
}
FIXTURE_COMPONENT_PREFIX = "component.fixture-"
# The longest record text the report holds (a decision's rationale), and a list item's.
MAXIMUM_TEXT = 12000
MAXIMUM_LIST_ITEM = 1000
SHORTENED = " … (shortened; the full text is in the record named in the source)"
NO_UNIT = "The record states a number here but no unit."
NO_NUMBER = "The record holds no number here."
CONSTRAINT_WORDS = {
    "pass": "pass",
    "fail": "fail",
    "unknown": "unknown",
    "not_applicable": "not applicable",
}
FLAG_WORDS = {
    "selected": "Selected",
    "frontier": "On the frontier",
    "dominated": "Dominated",
    "infeasible": "Infeasible",
}


@dataclass(frozen=True, slots=True)
class ReportRecords:
    """Every record the report reads, already digest-checked by the repository port.

    ``inputs`` lists each one as `{kind, id, version, digest, media_type}` for the record
    appendix; the composer reads nothing that is not listed there.
    """

    case: dict[str, Any]
    case_ref: dict[str, Any]
    intent: dict[str, Any]
    candidates: tuple[dict[str, Any], ...]
    inputs: tuple[dict[str, Any], ...]
    patterns: dict[str, dict[str, Any]] = field(default_factory=dict)
    decision: dict[str, Any] | None = None
    contract: dict[str, Any] | None = None
    evaluations: tuple[dict[str, Any], ...] = ()
    assurance_plan: dict[str, Any] | None = None
    bundle: dict[str, Any] | None = None
    components: dict[str, dict[str, Any]] = field(default_factory=dict)
    snapshot: dict[str, Any] | None = None
    policy_decisions: tuple[dict[str, Any], ...] = ()
    approvals: dict[str, dict[str, Any]] = field(default_factory=dict)
    observations: tuple[dict[str, Any], ...] = ()
    regulatory_nexus: dict[str, Any] | None = None
    cost_model: dict[str, Any] | None = None
    proposal: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class Narrative:
    """Checked notes a model proposed, one per main slide at most, and their record."""

    mode: str
    narrative_ref: dict[str, Any]
    model: str
    notes: dict[str, str]


# ----- small builders ---------------------------------------------------------------


def _escape(part: Any) -> str:
    return str(part).replace("~", "~0").replace("/", "~1")


def _version_of(document: dict[str, Any]) -> str:
    release = document.get("release")
    if isinstance(release, dict) and isinstance(release.get("version"), str):
        return str(release["version"])
    return str(document.get("version", document.get("sequence", "0")))


def source(document: dict[str, Any], *parts: Any) -> str:
    pointer = "".join(f"/{_escape(part)}" for part in parts)
    return f"{document['id']}@{_version_of(document)}#{pointer}"


def _clip(text: str, limit: int = MAXIMUM_TEXT) -> str:
    """Record text that fits the report, shortened visibly rather than silently or not at all."""

    if len(text) <= limit:
        return text
    return text[: limit - len(SHORTENED)].rstrip() + SHORTENED


def _text(text: str, mark: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"type": "text", "text": _clip(text), "mark": mark}


def _list(items: Iterable[str], mark: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": "list",
        "items": [_clip(str(item), MAXIMUM_LIST_ITEM) for item in items],
        "mark": mark,
    }


def _evaluation_fixture(evaluation: dict[str, Any]) -> str | None:
    """The fixture set an evaluation ran over, when it ran over one."""

    fixture = evaluation.get("fixture_version")
    if isinstance(fixture, str) and fixture:
        return fixture
    limitations = " ".join(str(item) for item in evaluation.get("limitations") or [])
    return str(evaluation.get("id")) if "synthetic" in limitations.lower() else None


def _status(status: str, word: str, reason: str | None = None) -> dict[str, Any]:
    return {
        "type": "status",
        "status": status,
        "word": word,
        "reason": None if reason is None else _clip(reason, MAXIMUM_LIST_ITEM),
    }


def _unknown(reason: str, *, unit: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"type": "unknown", "reason": _clip(reason, MAXIMUM_LIST_ITEM)}
    if unit:
        value["unit"] = unit
    return value


def _quantity(
    value: float | int | None,
    unit: str | None,
    basis: str,
    origin: str,
    *,
    lower: float | int | None = None,
    upper: float | int | None = None,
    confidence: float | None = None,
    estimator: str | None = None,
    synthetic: bool = False,
) -> dict[str, Any]:
    """A number with its unit, basis and source; without a number or a unit it is unknown."""

    if not unit:
        return _unknown(NO_UNIT)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return _unknown(NO_NUMBER)
    if synthetic or (estimator is not None and estimator.startswith("fixture-")):
        basis = "synthetic estimate"
    short = format_number(value)
    if lower is not None and upper is not None:
        short += f" ({format_number(lower)} to {format_number(upper)})"
    shown = f"{format_number(value)} {format_unit(unit)}"
    if lower is not None and upper is not None:
        shown += f" ({format_number(lower)} to {format_number(upper)})"
    return {
        "type": "quantity",
        "value": value,
        "lower": lower,
        "upper": upper,
        "unit": unit,
        "basis": basis,
        "confidence": confidence,
        "estimator": estimator,
        "source": origin,
        "text": shown,
        "short": short,
    }


def _count(
    count: int,
    singular: str,
    plural: str,
    origin: str,
    *,
    estimator: str | None = None,
    synthetic: bool = False,
) -> dict[str, Any]:
    return _quantity(
        count,
        singular if count == 1 else plural,
        "counted",
        origin,
        estimator=estimator,
        synthetic=synthetic,
    )


def _fact(label: str, value: dict[str, Any], origin: str) -> dict[str, Any]:
    return {"label": label, "value": value, "source": origin}


def _facts(items: Sequence[dict[str, Any]], heading: str | None = None) -> dict[str, Any]:
    return {"kind": "facts", "heading": heading, "items": list(items)}


def _row(cells: Sequence[dict[str, Any]], origin: str) -> dict[str, Any]:
    return {"cells": list(cells), "source": origin}


def _table(
    identifier: str,
    caption: str,
    columns: Sequence[str],
    rows: Sequence[dict[str, Any]],
    heading: str | None = None,
    *,
    display: str = "full",
) -> dict[str, Any]:
    """A table. ``display="short"`` shows quantities without their unit, because a
    column of the table names it; the quantity itself still carries the unit."""

    return {
        "kind": "table",
        "id": identifier,
        "heading": heading,
        "caption": caption,
        "columns": list(columns),
        "rows": list(rows),
        "display": display,
    }


def _quote(label: str, text: str, attribution: str, origin: str) -> dict[str, Any]:
    return {
        "kind": "quote",
        "label": label,
        "text": _clip(text),
        "attribution": attribution,
        "source": origin,
    }


def _callout(label: str, text: str, origin: str) -> dict[str, Any]:
    return {"kind": "callout", "label": label, "text": _clip(text), "source": origin}


def _paragraph(text: str, origin: str = TEMPLATE) -> dict[str, Any]:
    return {"kind": "paragraph", "text": _clip(text), "source": origin}


def _not_yet(what: str, step: str, hint: str | None) -> dict[str, Any]:
    return {"kind": "not_yet", "what": what, "step": step, "hint": hint, "source": TEMPLATE}


def _commands(lines: Sequence[str], note: str, heading: str | None = None) -> dict[str, Any]:
    return {
        "kind": "commands",
        "heading": heading,
        "lines": list(lines),
        "note": note,
        "source": TEMPLATE,
    }


def _date(timestamp: Any) -> str:
    return str(timestamp)[:10] if isinstance(timestamp, str) and timestamp else "unknown"


def _when(timestamp: Any) -> str:
    """`2026-08-18T12:00:00Z` → "2026-08-18 12:00 UTC"; anything else as recorded."""

    if not isinstance(timestamp, str) or not timestamp:
        return "unknown"
    try:
        instant = _instant(timestamp)
    except ValueError:
        return timestamp
    return instant.strftime("%Y-%m-%d %H:%M UTC")


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _sentence_list(items: Sequence[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def _title_within(preferred: str, fallback: str, limit: int = 12) -> str:
    return preferred if len(preferred.split()) <= limit else fallback


# ----- the composition context -------------------------------------------------------


class _Context:
    """The records with the lookups every section needs, computed once."""

    def __init__(self, records: ReportRecords, generated_at: str) -> None:
        self.records = records
        self.case = records.case
        self.intent = records.intent
        self.generated_at = generated_at
        self.status = str(self.case["status"])
        selected_ref = self.case.get("selected_candidate_ref") or {}
        by_id = {str(candidate["id"]): candidate for candidate in records.candidates}
        selected = by_id.get(str(selected_ref.get("id")))
        if selected is None:
            raise ValueError("a report needs the selected candidate among the candidates")
        self.selected: dict[str, Any] = selected
        baselines = [candidate for candidate in records.candidates if is_baseline(candidate)]
        self.baseline = baselines[0] if baselines else None
        others = [candidate for candidate in records.candidates if candidate not in baselines]
        self.ordered = [*baselines, *others]
        self.provenance: dict[str, dict[str, Any]] = dict(self.intent.get("provenance") or {})
        self.synthetic_estimators = {
            fixture
            for fixture in (_evaluation_fixture(item) for item in records.evaluations)
            if fixture is not None
        } | {
            str(objective.get("estimator_ref"))
            for candidate in records.candidates
            for objective in candidate.get("objectives") or []
            if str(objective.get("estimator_ref")).startswith("fixture-")
        }

    def name(self, candidate: dict[str, Any]) -> str:
        return f"{candidate_label(candidate)} ({candidate['id']})"

    def label(self, candidate: dict[str, Any]) -> str:
        return candidate_label(candidate)

    def flag(self, candidate: dict[str, Any]) -> dict[str, Any]:
        pareto = candidate.get("pareto") or {}
        if candidate.get("status") == "infeasible":
            reasons = candidate.get("rejection_reasons") or []
            return _status("infeasible", FLAG_WORDS["infeasible"], "; ".join(reasons) or None)
        if candidate is self.selected:
            return _status("selected", FLAG_WORDS["selected"])
        dominated_by = pareto.get("dominated_by") or []
        if dominated_by:
            return _status(
                "dominated", FLAG_WORDS["dominated"], f"Dominated by {', '.join(dominated_by)}."
            )
        if pareto.get("frontier_member") is True:
            return _status("frontier", FLAG_WORDS["frontier"])
        return _status("unknown", "Unranked", "The record carries no frontier result.")

    def objective(self, candidate: dict[str, Any], name: str) -> tuple[int, dict[str, Any]] | None:
        for index, objective in enumerate(candidate.get("objectives") or []):
            if objective.get("name") == name:
                return index, objective
        return None

    def objective_quantity(self, candidate: dict[str, Any], name: str) -> dict[str, Any]:
        found = self.objective(candidate, name)
        if found is None:
            return _unknown(f"{self.name(candidate)} records no {humanise(name).lower()} estimate.")
        index, objective = found
        if objective.get("value") is None and objective.get("unknown_reason"):
            # K4: the objective's own reason, with its recorded unit, never the generic one.
            return _unknown(
                str(objective["unknown_reason"]), unit=_recorded_unit(objective.get("unit"))
            )
        return _quantity(
            objective.get("value"),
            _recorded_unit(objective.get("unit")),
            "estimated",
            source(candidate, "objectives", index),
            lower=objective.get("lower"),
            upper=objective.get("upper"),
            confidence=objective.get("confidence"),
            estimator=objective.get("estimator_ref"),
        )

    def mark(self, pointer: str) -> dict[str, Any]:
        entry = self.provenance.get(pointer)
        if entry is None:
            parent = pointer.rsplit("/", 1)[0]
            entry = self.provenance.get(parent)
        if entry is None:
            return {
                "class": "unknown",
                "status": "open",
                "word": "No provenance record",
                "confidence": None,
            }
        kind = str(entry.get("source") or "unknown")
        if entry.get("confirmed_by"):
            status = "confirmed"
        elif entry.get("confirmation_required"):
            status = "open"
        elif kind == "explicit":
            status = "stated"
        else:
            status = "assumed"
        word = PROVENANCE_WORDS.get(kind, "Unknown")
        if status != "stated":
            word = f"{word}, {status}"
        return {
            "class": kind if kind in PROVENANCE_WORDS else "unknown",
            "status": status,
            "word": word,
            "confidence": entry.get("confidence"),
        }

    def intent_source(self, pointer: str) -> str:
        return f"{self.intent['id']}@{self.intent['version']}#{pointer}"

    def case_source(self, *parts: Any) -> str:
        return source(self.case, *parts)

    def pattern_description(self, candidate: dict[str, Any]) -> tuple[str, str] | None:
        reference = (candidate.get("extensions") or {}).get(PATTERN_REF_EXTENSION)
        if not isinstance(reference, dict):
            return None
        pattern = self.records.patterns.get(str(reference.get("id")))
        if pattern is None or not isinstance(pattern.get("description"), str):
            return None
        return str(pattern["description"]), source(pattern, "description")

    def explanation(self, candidate: dict[str, Any]) -> dict[str, Any]:
        value = (candidate.get("extensions") or {}).get(EXPLANATION_EXTENSION)
        return value if isinstance(value, dict) else {}

    def feasible(self) -> list[dict[str, Any]]:
        return [candidate for candidate in self.ordered if candidate.get("status") != "infeasible"]


def _blocks_state(blocks: Sequence[dict[str, Any]]) -> str:
    waiting = [block for block in blocks if block["kind"] == "not_yet"]
    if waiting and len(waiting) == len(blocks):
        return "not_yet"
    return "partial" if waiting else "ready"


def _section(
    identifier: str,
    number: str,
    title: str,
    subtitle: str,
    blocks: Sequence[dict[str, Any]],
    detail_in: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "id": identifier,
        "number": number,
        "kind": "main" if number.isdigit() else "appendix",
        "title": title,
        "subtitle": subtitle,
        "state": _blocks_state(blocks),
        "detail_in": list(detail_in),
        "blocks": list(blocks),
        "note": None,
    }


# ----- not-yet steps -----------------------------------------------------------------


def _missing_assurance(ctx: _Context) -> dict[str, Any]:
    return _not_yet("The assurance plan", "Plan assurance", f"oak assure {ctx.selected['id']}")


def _missing_bundle(ctx: _Context, what: str) -> dict[str, Any]:
    return _not_yet(what, "Compile the bundle", f"oak plan {ctx.selected['id']} --target <profile>")


def _missing_evaluation(ctx: _Context) -> dict[str, Any]:
    return _not_yet(
        "An evaluation of the selected design", "Evaluate it", f"oak evaluate {ctx.selected['id']}"
    )


def _missing_observation() -> dict[str, Any]:
    return _not_yet(
        "Observed cost, latency, quality and energy", "Install, then observe", "oak observe"
    )


# ----- main sections -------------------------------------------------------------------


def _cover(ctx: _Context, generated_by: str) -> dict[str, Any]:
    label = ctx.label(ctx.selected)
    case_title = str(ctx.case.get("title") or ctx.case["id"])
    title = _title_within(f"{case_title}: build the {label} design", f"Build the {label} design")
    stakeholders = (ctx.intent.get("spec") or {}).get("stakeholders") or {}
    prepared_for: list[dict[str, Any]] = []
    for field_name, word in (
        ("end_users", "Users"),
        ("operators", "Operators"),
        ("accountable_owner", "Accountable owner"),
    ):
        value = stakeholders.get(field_name)
        pointer = f"/spec/stakeholders/{field_name}"
        if isinstance(value, list) and value:
            prepared_for.append(
                _fact(word, _list(value, ctx.mark(f"{pointer}/0")), ctx.intent_source(pointer))
            )
        elif isinstance(value, str) and value:
            prepared_for.append(
                _fact(word, _text(value, ctx.mark(pointer)), ctx.intent_source(pointer))
            )
    if not prepared_for:
        prepared_for.append(
            _fact(
                "Prepared for",
                _unknown("The brief names no stakeholders."),
                ctx.intent_source("/spec/stakeholders"),
            )
        )
    facts = [
        _fact("Case", _text(case_title), ctx.case_source("title")),
        *prepared_for,
        _fact("Prepared by", _text(generated_by), TEMPLATE),
        _fact("Date", _text(_date(ctx.generated_at)), TEMPLATE),
    ]
    blocks: list[dict[str, Any]] = [
        _facts(facts),
        _callout("Recommended", ctx.name(ctx.selected), ctx.case_source("selected_candidate_ref")),
    ]
    if ctx.baseline is not None and ctx.baseline is not ctx.selected:
        blocks.append(
            _callout("Baseline beside it", ctx.name(ctx.baseline), source(ctx.baseline, "id"))
        )
    decision = ctx.records.decision
    if decision is not None and isinstance(decision.get("rationale"), str):
        blocks.append(
            _quote(
                "The owner's rationale",
                str(decision["rationale"]),
                f"{decision.get('owner', 'unknown')}, {_date(decision.get('decided_at'))}",
                source(decision, "rationale"),
            )
        )
    return _section(
        "cover", "1", title, "A decision on one design case, read from its records.", blocks, ("C",)
    )


def _method(ctx: _Context, oak_version: str, narrative: Narrative | None) -> dict[str, Any]:
    proposal_ref = (ctx.intent.get("extensions") or {}).get(PROPOSAL_REF_EXTENSION)
    if isinstance(proposal_ref, dict):
        details = ((ctx.records.proposal or {}).get("extensions") or {}).get(MODEL_EXTENSION)
        model = details.get("model_id") if isinstance(details, dict) else None
        read = (
            f"A model ({model}) proposed values; a person confirmed, corrected or "
            "rejected each one."
            if model
            else "A model proposed values; a person confirmed, corrected or rejected each one."
        )
        read_source = ctx.intent_source(f"/extensions/{_escape(PROPOSAL_REF_EXTENSION)}")
    else:
        read = "The deterministic interpreter read the brief. No model was used."
        read_source = ctx.intent_source("/provenance")
    facts = [
        _fact("OAK version", _text(oak_version), TEMPLATE),
        _fact(
            "Case",
            _text(f"{ctx.case['id']} at version {ctx.case['version']}"),
            ctx.case_source("version"),
        ),
        _fact("How the brief was read", _text(read), read_source),
    ]
    confirmations = (ctx.intent.get("extensions") or {}).get(CONFIRMATIONS_EXTENSION) or []
    pointer = f"/extensions/{_escape(CONFIRMATIONS_EXTENSION)}"
    facts.append(
        _fact(
            "Answers a person gave",
            _count(len(confirmations), "answer", "answers", ctx.intent_source(pointer)),
            ctx.intent_source(pointer),
        )
    )
    snapshot = ctx.records.snapshot
    if snapshot is not None:
        facts.append(
            _fact(
                "Catalogue snapshot",
                _text(f"{snapshot['id']}, valid at {_when(snapshot.get('valid_at'))}"),
                source(snapshot, "valid_at"),
            )
        )
        facts.append(
            _fact(
                "Catalogue policy",
                _text(str(snapshot.get("policy_version"))),
                source(snapshot, "policy_version"),
            )
        )
        reviews = sorted(
            str(entry["next_review_at"])
            for entry in snapshot.get("entries", [])
            if isinstance(entry.get("next_review_at"), str)
        )
        if reviews:
            facts.append(
                _fact(
                    "Next catalogue review", _text(_when(reviews[0])), source(snapshot, "entries")
                )
            )
    else:
        facts.append(
            _fact(
                "Catalogue snapshot",
                _unknown("The case holds no catalogue snapshot."),
                ctx.case_source("extensions"),
            )
        )
    classes = Counter(str(entry.get("source") or "unknown") for entry in ctx.provenance.values())
    rows = [
        _row(
            [
                _text(PROVENANCE_WORDS.get(kind, humanise(kind))),
                _count(classes[kind], "value", "values", ctx.intent_source("/provenance")),
            ],
            ctx.intent_source("/provenance"),
        )
        for kind in sorted(classes)
    ]
    if narrative is None:
        closing = "Composed from the case's records. No model wrote it."
    else:
        closing = (
            f"Composed from the case's records. Notes labelled {NOTE_LABEL} came from "
            f"{narrative.model}, after OAK's checks."
        )
    blocks = [
        _facts(facts),
        _table(
            "claims",
            "Values in the confirmed intent, by where they came from",
            ["Where it came from", "Values"],
            rows,
        ),
        _paragraph(closing),
    ]
    return _section(
        "method",
        "2",
        _title_within(
            "Composed from the case's records; no model wrote it"
            if narrative is None
            else "Composed from the case's records, with labelled model notes",
            "How this report was made",
        ),
        "Versions, how the brief was read, and where each value came from.",
        blocks,
        ("A", "F"),
    )


_ASKED_FIELDS: tuple[tuple[str, str], ...] = (
    ("/spec/purpose/problem", "Problem"),
    ("/spec/purpose/desired_outcomes", "Desired outcome"),
    ("/spec/purpose/baseline", "Baseline today"),
    ("/spec/decision/autonomy", "Decision autonomy"),
    ("/spec/decision/reversibility", "Reversibility"),
    ("/spec/data/classifications", "Data class"),
    ("/spec/data/extensions/oak.community~1production_data_permitted", "Production data permitted"),
    ("/spec/deployment_environment/modes", "Deployment"),
    ("/spec/deployment_environment/network_constraints", "Network"),
    ("/spec/hardware/cpu_architectures", "CPU architecture"),
    ("/spec/hardware/accelerators", "Accelerator"),
    ("/spec/hardware/ram_gib", "Memory"),
    ("/spec/hardware/vram_gib", "Accelerator memory"),
    ("/spec/hardware/storage_gib", "Storage"),
)


def _resolve(document: Any, pointer: str) -> Any:
    current = document
    for raw in pointer.lstrip("/").split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def _unit_for(field_name: str) -> str | None:
    if field_name in FIELD_UNITS:
        return FIELD_UNITS[field_name]
    for suffix, unit in UNIT_SUFFIXES:
        if field_name.endswith(suffix):
            return unit
    return None


def _recorded_unit(unit: Any) -> str | None:
    return str(unit) if isinstance(unit, str) and unit.strip() else None


def _unit_words(unit: str | None) -> str:
    return format_unit(unit) if unit else "no unit recorded"


def _basis_for(mark: dict[str, Any]) -> str:
    return {"confirmed": "confirmed", "stated": "declared", "open": "assumed"}.get(
        str(mark["status"]), "measured" if mark["class"] == "measured" else "assumed"
    )


def _intent_value(ctx: _Context, pointer: str, value: Any) -> dict[str, Any]:
    mark = ctx.mark(pointer)
    if isinstance(value, bool):
        return _text("yes" if value else "no", mark)
    if isinstance(value, (int, float)):
        field_name = pointer.rsplit("/", 1)[-1]
        return _quantity(
            value,
            _unit_for(field_name),
            _basis_for(mark),
            ctx.intent_source(pointer),
            confidence=mark["confidence"],
        )
    return _text(
        str(value).replace("_", " ")
        if pointer.endswith(("autonomy", "reversibility"))
        else str(value),
        mark,
    )


def _asked(ctx: _Context) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    open_values = 0
    assumed_values = 0
    missing_values = 0
    for pointer, label in _ASKED_FIELDS:
        value = _resolve(ctx.intent, pointer)
        if value is None or value == []:
            if pointer.startswith(("/spec/hardware/accelerators", "/spec/hardware/vram_gib")):
                continue
            missing_values += 1
            rows.append(
                _row(
                    [_text(label), _unknown("The brief does not state it."), _text("Not stated")],
                    ctx.intent_source(pointer),
                )
            )
            continue
        items = list(enumerate(value)) if isinstance(value, list) else [(None, value)]
        for index, item in items:
            item_pointer = pointer if index is None else f"{pointer}/{index}"
            mark = ctx.mark(item_pointer)
            if mark["status"] == "open":
                open_values += 1
            elif mark["status"] == "assumed":
                assumed_values += 1
            shown = _intent_value(ctx, item_pointer, item)
            if shown["type"] == "text":
                shown = {**shown, "mark": None}
            rows.append(
                _row(
                    [_text(label), shown, _text(mark["word"], mark)],
                    ctx.intent_source(item_pointer),
                )
            )
    if open_values == 1:
        title = "One value still waits for a person's confirmation"
    elif open_values:
        title = (
            f"{_capital(count_words(open_values))} values still wait for a person's confirmation"
        )
    elif assumed_values and missing_values:
        title = (
            f"{_capital(count_words(assumed_values))} "
            f"{'value is' if assumed_values == 1 else 'values are'} assumed and "
            f"{count_words(missing_values)} {'is' if missing_values == 1 else 'are'} "
            "not stated in the brief"
        )
    elif assumed_values == 1:
        title = "One value is assumed; the rest are stated or confirmed"
    elif assumed_values:
        title = (
            f"{_capital(count_words(assumed_values))} values are assumed; "
            "the rest are stated or confirmed"
        )
    elif missing_values == 1:
        title = "One value is not stated in the brief"
    elif missing_values:
        title = f"{_capital(count_words(missing_values))} values are not stated in the brief"
    else:
        title = "Every value is stated in the brief or confirmed"
    return _section(
        "asked",
        "3",
        _title_within(title, "What the brief asks for"),
        "Each value as the confirmed intent holds it, with where it came from.",
        [
            _table(
                "asked",
                "What the brief asks for, as the confirmed intent holds it",
                ["Asked", "Value", "Where it came from"],
                rows,
            )
        ],
        ("A",),
    )


def _options(ctx: _Context) -> dict[str, Any]:
    decision = ctx.records.decision or {}
    why_not = {
        str((alternative.get("candidate_ref") or {}).get("id")): alternative
        for alternative in decision.get("alternatives") or []
    }
    rows = []
    blocked = 0
    for candidate in ctx.ordered:
        described = ctx.pattern_description(candidate)
        what = _text(described[0]) if described else _unknown("No pattern description is recorded.")
        reasons = list(candidate.get("rejection_reasons") or [])
        if candidate.get("status") == "infeasible":
            blocked += 1
        if candidate is ctx.selected:
            reason_value = _text("Selected by the owner.")
        elif reasons:
            reason_value = _list(reasons)
        elif str(candidate["id"]) in why_not:
            reason_value = _text(str(why_not[str(candidate["id"])].get("reason")))
        else:
            reason_value = _text("Not selected; no reason is recorded.")
        rows.append(
            _row(
                [_text(ctx.name(candidate)), ctx.flag(candidate), what, reason_value],
                source(candidate, "status"),
            )
        )
    total = len(ctx.ordered)
    title = f"{_capital(count_words(total))} options considered; " + (
        f"{count_words(blocked)} cannot be built" if blocked else "all can be built"
    )
    return _section(
        "options",
        "4",
        _title_within(title, "The options considered"),
        "Baseline first, with why each one lost or what blocks it.",
        [
            _table(
                "options",
                "Every option the case holds",
                ["Option", "Flag", "What it is", "Why not, or what blocks it"],
                rows,
            )
        ],
        ("B",),
    )


def _risks(ctx: _Context) -> dict[str, Any]:
    constraint_ids: list[str] = []
    for candidate in ctx.ordered:
        for constraint in candidate.get("hard_constraints") or []:
            if constraint["id"] not in constraint_ids:
                constraint_ids.append(constraint["id"])
    rows = []
    failing: set[str] = set()
    for constraint_id in constraint_ids:
        cells = [_text(humanise(constraint_id))]
        origin: str | None = None
        for candidate in ctx.ordered:
            found = next(
                (
                    (index, constraint)
                    for index, constraint in enumerate(candidate.get("hard_constraints") or [])
                    if constraint["id"] == constraint_id
                ),
                None,
            )
            if found is None:
                cells.append(
                    _status(
                        "not_applicable", "not applicable", "The option records no such constraint."
                    )
                )
                continue
            index, constraint = found
            origin = origin or source(candidate, "hard_constraints", index)
            result = str(constraint.get("result"))
            if result in {"fail", "unknown"}:
                failing.add(str(candidate["id"]))
            reason = constraint.get("reason") if result != "pass" else None
            cells.append(
                _status(
                    result if result in CONSTRAINT_WORDS else "unknown",
                    CONSTRAINT_WORDS.get(result, "unknown"),
                    str(reason) if reason else None,
                )
            )
        # The cells come from each option's own constraint; the row names the first.
        rows.append(_row(cells, origin or source(ctx.ordered[0], "hard_constraints")))
    risk_rows = [
        _row(
            [
                _text(ctx.name(candidate)),
                _list(candidate.get("risks") or [])
                if candidate.get("risks")
                else _text("None recorded."),
            ],
            source(candidate, "risks"),
        )
        for candidate in ctx.ordered
    ]
    count = len(failing)
    if count == 0:
        title = "No option fails or leaves a hard constraint unknown"
    elif count == 1:
        title = "One option fails or leaves a hard constraint unknown"
    else:
        title = f"{_capital(count_words(count))} options fail or leave a hard constraint unknown"
    return _section(
        "risks",
        "5",
        _title_within(title, "Where each option could fail"),
        "Hard constraints by option: pass, fail, unknown or not applicable.",
        [
            _table(
                "constraints",
                "Hard constraints by option",
                ["Constraint", *[ctx.label(candidate) for candidate in ctx.ordered]],
                rows,
            ),
            _table("option-risks", "Each option's main risks", ["Option", "Risks"], risk_rows),
        ],
        ("B",),
    )


def _comparison(ctx: _Context) -> dict[str, Any]:
    names = [
        name
        for name in OBJECTIVE_NAMES
        if any(ctx.objective(candidate, name) for candidate in ctx.ordered)
    ]
    series = []
    rows = []
    for name in names:
        bars = []
        unit: str | None = None
        cells = []
        for candidate in ctx.ordered:
            quantity = ctx.objective_quantity(candidate, name)
            cells.append(quantity)
            if quantity["type"] == "quantity":
                unit = quantity["unit"]
                bars.append({"label": ctx.label(candidate), "value": quantity})
        series.append({"objective": OBJECTIVE_NAMES[name], "unit": _unit_words(unit), "bars": bars})
        found = ctx.objective(ctx.selected, name)
        direction = (found[1].get("direction") if found else None) or "minimize"
        rows.append(
            _row(
                [
                    _text(OBJECTIVE_NAMES[name]),
                    _text(
                        f"{_unit_words(unit)}, "
                        f"{'lower' if direction == 'minimize' else 'higher'} is better"
                    ),
                    *cells,
                ],
                source(ctx.selected, "objectives", found[0]) if found else TEMPLATE,
            )
        )
    rows.append(
        _row(
            [_text("Flag"), _text("how the option fared"), *[ctx.flag(c) for c in ctx.ordered]],
            source(ctx.selected, "pareto"),
        )
    )
    selected_pareto = ctx.selected.get("pareto") or {}
    on_frontier = selected_pareto.get("frontier_member") is True
    label = ctx.label(ctx.selected)
    title = (
        f"{label} is on the frontier beside the baseline"
        if on_frontier
        else f"{label} is off the frontier"
    )
    estimators = sorted(
        {
            str(objective.get("estimator_ref"))
            for candidate in ctx.ordered
            for objective in candidate.get("objectives") or []
        }
    )
    synthetic = bool(estimators) and all(item.startswith("fixture-") for item in estimators)
    subtitle = (
        "Point estimate and range per objective. Every figure is a synthetic estimate."
        if synthetic
        else "Point estimate and range per objective, with estimator and confidence."
    )
    weights = []
    for name in names:
        found = ctx.objective(ctx.selected, name)
        if found is None:
            continue
        index, objective = found
        weights.append(
            _row(
                [
                    _text(OBJECTIVE_NAMES[name]),
                    _quantity(
                        objective.get("weight"),
                        "of 1",
                        "declared",
                        source(ctx.selected, "objectives", index, "weight"),
                    ),
                    _text(str(objective.get("estimator_ref"))),
                    _quantity(
                        objective.get("confidence"),
                        "of 1",
                        "declared",
                        source(ctx.selected, "objectives", index, "confidence"),
                    ),
                ],
                source(ctx.selected, "objectives", index),
            )
        )
    summary = selected_pareto.get("sensitivity_summary")
    blocks = [
        {
            "kind": "chart",
            "heading": None,
            "description": (
                "Ranges for each objective, one bar per option on a shared scale. "
                "The table lists the same numbers."
            ),
            "series": series,
            "table_id": "comparison",
            "source": source(ctx.selected, "objectives"),
        },
        _table(
            "comparison",
            "Each objective by option: point estimate and range",
            ["Objective", "Unit", *[ctx.label(candidate) for candidate in ctx.ordered]],
            rows,
            display="short",
        ),
        _table(
            "weights",
            f"How {label} weighs each objective",
            ["Objective", "Weight", "Estimator", "Confidence"],
            weights,
        ),
        _paragraph(str(summary), source(ctx.selected, "pareto", "sensitivity_summary"))
        if summary
        else _paragraph("The selected option records no sensitivity summary."),
    ]
    return _section(
        "comparison",
        "6",
        _title_within(title, "How the options compare"),
        subtitle,
        blocks,
        ("B", "D"),
    )


def _recommendation(ctx: _Context) -> dict[str, Any]:
    decision = ctx.records.decision
    label = ctx.label(ctx.selected)
    blocks: list[dict[str, Any]] = [
        _callout("Selected", ctx.name(ctx.selected), ctx.case_source("selected_candidate_ref"))
    ]
    if ctx.baseline is not None and ctx.baseline is not ctx.selected:
        blocks.append(
            _callout("Baseline beside it", ctx.name(ctx.baseline), source(ctx.baseline, "id"))
        )
    alternatives_count = 0
    if decision is not None:
        blocks.append(
            _quote(
                "The owner's rationale",
                str(decision.get("rationale")),
                f"{decision.get('owner')}, {_date(decision.get('decided_at'))}",
                source(decision, "rationale"),
            )
        )
        blocks.append(
            _facts(
                [
                    _fact(
                        "Decided by", _text(str(decision.get("owner"))), source(decision, "owner")
                    ),
                    _fact(
                        "Decided at",
                        _text(_when(decision.get("decided_at"))),
                        source(decision, "decided_at"),
                    ),
                ]
            )
        )
        alternatives = decision.get("alternatives") or []
        alternatives_count = len(alternatives)
        by_id = {str(candidate["id"]): candidate for candidate in ctx.records.candidates}
        blocks.append(
            _table(
                "alternatives",
                "Each alternative and why it was not chosen",
                ["Alternative", "Why not"],
                [
                    _row(
                        [
                            _text(
                                ctx.name(by_id[str(alternative["candidate_ref"]["id"])])
                                if str(alternative["candidate_ref"]["id"]) in by_id
                                else str(alternative["candidate_ref"]["id"])
                            ),
                            _text(str(alternative.get("reason"))),
                        ],
                        source(decision, "alternatives", index),
                    )
                    for index, alternative in enumerate(alternatives)
                ],
            )
        )
    else:
        blocks.append(
            _not_yet(
                "The owner's decision record",
                "Select a candidate",
                f"oak select {ctx.selected['id']} --rationale <why>",
            )
        )
    satisfied = ctx.explanation(ctx.selected).get("satisfied_requirements") or []
    pointer = ("extensions", EXPLANATION_EXTENSION, "satisfied_requirements")
    blocks.append(
        _table(
            "satisfied",
            f"Requirements {label} satisfies",
            ["Constraint", "Reason", "Requirements"],
            [
                _row(
                    [
                        _text(humanise(str(item.get("constraint_id")))),
                        _text(str(item.get("reason"))),
                        _list(item.get("requirement_ids") or []),
                    ],
                    source(ctx.selected, *pointer, index),
                )
                for index, item in enumerate(satisfied)
            ],
        )
        if satisfied
        else _paragraph("The selected option records no satisfied requirements.")
    )
    title = (
        f"The owner chose {label} over {count_words(alternatives_count)} alternatives"
        if alternatives_count != 1
        else f"The owner chose {label} over one alternative"
    )
    return _section(
        "recommendation",
        "7",
        _title_within(title, f"{label} is recommended"),
        "The owner's words are quoted as theirs; the rest is from records.",
        blocks,
        ("C",),
    )


def _cost(ctx: _Context) -> dict[str, Any]:
    compared = [ctx.selected] + (
        [ctx.baseline] if ctx.baseline is not None and ctx.baseline is not ctx.selected else []
    )
    rows = [
        _row(
            [
                _text(ctx.name(candidate)),
                ctx.objective_quantity(candidate, "monthly_cost"),
                ctx.objective_quantity(candidate, "energy"),
            ],
            source(candidate, "objectives"),
        )
        for candidate in compared
    ]
    blocks: list[dict[str, Any]] = [
        _table(
            "cost",
            "Monthly cost and energy, selected beside baseline",
            ["Option", "Monthly cost", "Energy"],
            rows,
        )
    ]
    model = ctx.records.cost_model
    if model is not None:
        outcome_rows = []
        for index, outcome in enumerate(model.get("outcomes") or []):
            for position, dimension in enumerate(outcome.get("dimensions") or []):
                outcome_rows.append(
                    _row(
                        [
                            _text(humanise(str(outcome.get("id")))),
                            _text(humanise(str(dimension.get("kind")))),
                            _quantity(
                                dimension.get("most_likely"),
                                str(dimension.get("unit")),
                                "assumed",
                                source(model, "outcomes", index, "dimensions", position),
                                lower=dimension.get("low"),
                                upper=dimension.get("high"),
                                confidence=outcome.get("confidence"),
                            ),
                        ],
                        source(model, "outcomes", index),
                    )
                )
        blocks.append(
            _table(
                "decision-cost",
                "The decision cost model's outcomes",
                ["Outcome", "Dimension", "Most likely (low to high)"],
                outcome_rows,
            )
        )
    else:
        blocks.append(
            _callout(
                "Benefit not estimated",
                "The case holds no decision cost model. OAK computes no benefit or return.",
                ctx.case_source("decision_cost_model_ref"),
            )
        )
    title = "Cost and energy are estimates; no benefit is estimated"
    selected_cost = ctx.objective(ctx.selected, "monthly_cost")
    baseline_cost = ctx.objective(ctx.baseline, "monthly_cost") if ctx.baseline else None
    if (
        selected_cost
        and baseline_cost
        and ctx.baseline is not ctx.selected
        and isinstance(selected_cost[1].get("value"), (int, float))
        and isinstance(baseline_cost[1].get("value"), (int, float))
    ):
        more = selected_cost[1]["value"] - baseline_cost[1]["value"]
        comparison = "more than" if more > 0 else "less than" if more < 0 else "the same as"
        title = (
            f"{ctx.label(ctx.selected)} is estimated to cost {comparison} the baseline per month"
        )
    return _section(
        "cost",
        "8",
        _title_within(title, "Cost"),
        "Point estimate and range, the selected option beside the baseline.",
        blocks,
        ("D",),
    )


def _architecture(ctx: _Context) -> dict[str, Any]:
    layout = layout_topology(ctx.selected.get("topology"))
    nodes = layout["nodes"]
    if layout["edges"]:
        sentences = []
        for edge in layout["edges"]:
            source_role = next(node["role"] for node in nodes if node["id"] == edge["from"])
            target_role = next(node["role"] for node in nodes if node["id"] == edge["to"])
            sentences.append(
                f"{source_role} feeds {target_role}"
                + (f" over {edge['label']}" if edge["label"] else "")
            )
        description = f"{'; '.join(sentences)}. The table lists the same."
    elif nodes:
        description = (
            f"{_capital(count_words(len(nodes)))} node"
            f"{'' if len(nodes) == 1 else 's'}: "
            f"{', '.join(node['role'] for node in nodes)}. The table lists the same."
        )
    else:
        description = "No nodes are recorded."
    topology = ctx.selected.get("topology") or {}
    node_rows = [
        _row(
            [
                _text(str(node.get("id"))),
                _text(str(node.get("role"))),
                _text(str(node.get("component_ref") or "none")),
                _list(node.get("data_classifications") or []),
            ],
            source(ctx.selected, "topology", "nodes", index),
        )
        for index, node in enumerate(topology.get("nodes") or [])
    ]
    edge_rows = [
        _row(
            [
                _text(str(edge.get("from"))),
                _text(str(edge.get("to"))),
                _text(str(edge.get("interface"))),
                _text(str(edge.get("data") or "not recorded")),
                _text(str(edge.get("security") or "not recorded")),
            ],
            source(ctx.selected, "topology", "edges", index),
        )
        for index, edge in enumerate(topology.get("edges") or [])
    ]
    blocks: list[dict[str, Any]] = [
        {
            "kind": "diagram",
            "heading": None,
            "description": description,
            "width": layout["width"],
            "height": layout["height"],
            "nodes": nodes,
            "edges": layout["edges"],
            "table_id": "topology-nodes",
            "source": source(ctx.selected, "topology"),
        },
        _table("topology-nodes", "Nodes", ["Node", "Role", "Component", "Data"], node_rows),
    ]
    if edge_rows:
        blocks.append(
            _table(
                "topology-edges",
                "Edges",
                ["From", "To", "Interface", "Data", "Security"],
                edge_rows,
            )
        )
    bundle = ctx.records.bundle
    if bundle is not None:
        component_rows = [
            _row(
                [
                    _text(str(item.get("manifest_id"))),
                    _text(str(item.get("version"))),
                    _status(
                        "pass" if item.get("licence_decision") == "allowed" else "unknown",
                        str(item.get("licence_decision") or "unknown"),
                    ),
                    _text(str(item.get("digest"))),
                ],
                source(bundle, "component_lock", index),
            )
            for index, item in enumerate(bundle.get("component_lock") or [])
        ]
        blocks.append(
            _table(
                "components",
                "Components as compiled",
                ["Component", "Version", "Licence decision", "Digest"],
                component_rows,
            )
        )
        target = bundle.get("target") or {}
        blocks.append(
            _facts(
                [
                    _fact(
                        "Target class",
                        _text(str(target.get("class"))),
                        source(bundle, "target", "class"),
                    ),
                    _fact(
                        "Environment",
                        _text(str(target.get("environment"))),
                        source(bundle, "target", "environment"),
                    ),
                    _fact(
                        "Network mode",
                        _text(str(target.get("network_mode"))),
                        source(bundle, "target", "network_mode"),
                    ),
                    _fact(
                        "Target fingerprint",
                        _text(str(target.get("fingerprint"))),
                        source(bundle, "target", "fingerprint"),
                    ),
                ],
                heading="The target",
            )
        )
    else:
        component_rows = [
            _row(
                [
                    _text(str(item.get("manifest_id"))),
                    _text(str(item.get("version"))),
                    _status(
                        "unknown",
                        "decided at compile",
                        "A licence decision is recorded when the bundle is compiled.",
                    ),
                    _text(str(item.get("digest"))),
                ],
                source(ctx.selected, "components", index),
            )
            for index, item in enumerate(ctx.selected.get("components") or [])
        ]
        blocks.append(
            _table(
                "components",
                "Components as designed",
                ["Component", "Version", "Licence decision", "Digest"],
                component_rows,
            )
        )
        blocks.append(_missing_bundle(ctx, "The compiled target"))
    count = len(nodes)
    edges = len(layout["edges"])
    title = (
        f"{ctx.label(ctx.selected)}: {count_words(count)} node{'s' if count != 1 else ''}, "
        f"{count_words(edges)} connection{'s' if edges != 1 else ''}"
    )
    return _section(
        "architecture",
        "9",
        _title_within(title, "Target architecture"),
        "Drawn as the workspace draws it; the tables list the same.",
        blocks,
        ("D", "E"),
    )


def _security(ctx: _Context) -> dict[str, Any]:
    spec = ctx.intent.get("spec") or {}
    data = spec.get("data") or {}
    classes = data.get("classifications") or []
    production = (data.get("extensions") or {}).get("oak.community/production_data_permitted")
    production_pointer = "/spec/data/extensions/oak.community~1production_data_permitted"
    facts = [
        _fact(
            "Data classes",
            _list(classes, ctx.mark("/spec/data/classifications/0"))
            if classes
            else _unknown("The brief states no data class."),
            ctx.intent_source("/spec/data/classifications"),
        ),
        _fact(
            "Production data permitted",
            _text("yes" if production else "no", ctx.mark(production_pointer))
            if isinstance(production, bool)
            else _unknown("Nobody has said yet."),
            ctx.intent_source(production_pointer),
        ),
    ]
    blocks: list[dict[str, Any]] = []
    bundle = ctx.records.bundle
    if bundle is not None:
        facts.append(
            _fact(
                "Network mode",
                _text(str((bundle.get("target") or {}).get("network_mode"))),
                source(bundle, "target", "network_mode"),
            )
        )
        names = [str(item.get("name")) for item in bundle.get("secret_references") or []]
        facts.append(
            _fact(
                "Secret references, by name only",
                _list(names) if names else _text("None."),
                source(bundle, "secret_references"),
            )
        )
    tenancy = spec.get("security_tenancy") or {}
    for field_name, word in (
        ("egress_policy", "Egress policy"),
        ("tenant_model", "Tenancy"),
        ("identity_provider", "Identity provider"),
    ):
        value = tenancy.get(field_name)
        if isinstance(value, str) and value:
            pointer = f"/spec/security_tenancy/{field_name}"
            facts.append(_fact(word, _text(value, ctx.mark(pointer)), ctx.intent_source(pointer)))
    blocks.append(_facts(facts))
    if bundle is None:
        blocks.append(_missing_bundle(ctx, "The network mode and secret references"))
    nexus = ctx.records.regulatory_nexus
    if nexus is not None:
        blocks.append(
            _facts(
                [
                    _fact(
                        "Regulatory nexus",
                        _text(f"{nexus.get('id')}: {nexus.get('status')}"),
                        source(nexus, "status"),
                    ),
                ]
            )
        )
    else:
        blocks.append(
            _callout(
                "Regulatory nexus",
                "The case holds no regulatory nexus record.",
                ctx.case_source("regulatory_nexus_ref"),
            )
        )
    if ctx.records.policy_decisions:
        blocks.append(
            _table(
                "policy",
                "Policy decisions",
                ["Decision", "Outcome", "Reasons", "Evaluated at"],
                [
                    _row(
                        [
                            _text(str(decision.get("id"))),
                            _text(str(decision.get("outcome"))),
                            _list(decision.get("reasons") or []),
                            _text(_when(decision.get("evaluated_at"))),
                        ],
                        source(decision, "outcome"),
                    )
                    for decision in ctx.records.policy_decisions
                ],
            )
        )
    else:
        blocks.append(
            _paragraph("The case holds no policy decision.", ctx.case_source("extensions"))
        )
    blocks.append(
        _paragraph(
            "Installing needs a signed plan and two separate approvals, given in a terminal. "
            "The web workspace holds none of it."
        )
    )
    restricted = [str(item) for item in classes if str(item) != "public"]
    if not classes:
        title = "The data classes are not stated yet"
    elif restricted:
        title = f"{_capital(_sentence_list(restricted))} data is in scope"
    else:
        title = "Public data only"
    if isinstance(production, bool):
        title += "; production data is " + ("permitted" if production else "not permitted")
    return _section(
        "security",
        "10",
        _title_within(title, "Security and data"),
        "Data, network, secrets by name, regulation and policy.",
        blocks,
        ("C",),
    )


def _approval_state(approval: dict[str, Any] | None, now: str) -> tuple[str, str]:
    if approval is None:
        return "absent", "absent"
    if approval.get("revoked") is True:
        return "revoked", "revoked"
    expires = approval.get("expires_at")
    if isinstance(expires, str) and _instant(expires) <= _instant(now):
        return "expired", "expired"
    return "current", "current"


def _governance(ctx: _Context) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    contract = ctx.records.contract
    metric_names: dict[str, str] = {}
    if contract is not None:
        metric_names = {
            str(metric["id"]): str(metric.get("name") or metric["id"])
            for metric in contract.get("metrics") or []
        }
        blocks.append(
            _table(
                "gates",
                "Gates in the evaluation contract",
                ["Gate", "Stage", "Required metrics", "Critical failures", "Approver roles"],
                [
                    _row(
                        [
                            _text(humanise(str(gate.get("id")))),
                            _text(str(gate.get("stage"))),
                            _list(
                                metric_names.get(str(item), str(item))
                                for item in gate.get("required_metric_ids") or []
                            ),
                            _list(gate.get("critical_failures") or []),
                            _list(gate.get("approver_roles") or []),
                        ],
                        source(contract, "gates", index),
                    )
                    for index, gate in enumerate(contract.get("gates") or [])
                ],
            )
        )
    else:
        blocks.append(_not_yet("The evaluation contract", "Generate candidates", "oak candidates"))
    plan = ctx.records.assurance_plan
    blocked = 0
    if plan is not None:
        rows = []
        for field_name, word in (
            ("controls", "Control"),
            ("required_tests", "Test"),
            ("evidence_requirements", "Evidence"),
        ):
            for index, item in enumerate(plan.get(field_name) or []):
                status = str(item.get("status"))
                rows.append(
                    _row(
                        [
                            _text(word),
                            _text(str(item.get("description"))),
                            _text(str(item.get("owner"))),
                            _status(
                                status if status in {"required", "satisfied"} else "unknown",
                                status.replace("_", " "),
                            ),
                        ],
                        source(plan, field_name, index),
                    )
                )
        blocks.append(
            _table(
                "assurance",
                "Controls, tests and evidence",
                ["Kind", "What", "Owner", "Status"],
                rows,
            )
        )
        blocker_rows = []
        for index, blocker in enumerate(plan.get("gate_blockers") or []):
            status = str(blocker.get("status"))
            if status == "blocked":
                blocked += 1
            blocker_rows.append(
                _row(
                    [
                        _text(humanise(str(blocker.get("gate")))),
                        _status(
                            status if status in {"clear", "blocked"} else "unknown",
                            status,
                            str(blocker.get("reason")),
                        ),
                        _text(str(blocker.get("owner"))),
                    ],
                    source(plan, "gate_blockers", index),
                )
            )
        blocks.append(_table("blockers", "Gate blockers", ["Gate", "State", "Owner"], blocker_rows))
    else:
        blocks.append(_missing_assurance(ctx))
    approvals = ctx.records.approvals
    if ctx.case.get("runner_plan_ref") is not None:
        rows = []
        for action in ("architecture", "apply"):
            approval = approvals.get(action)
            state, word = _approval_state(approval, ctx.generated_at)
            rows.append(
                _row(
                    [
                        _text(f"Approve {action}"),
                        _status(state, word),
                        _text(_when(approval.get("expires_at")))
                        if approval
                        else _text("not given"),
                    ],
                    source(approval, "expires_at") if approval else ctx.case_source("extensions"),
                )
            )
        blocks.append(
            _table(
                "approvals",
                "The two approvals an install needs",
                ["Approval", "State", "Expires"],
                rows,
            )
        )
    else:
        blocks.append(_missing_bundle(ctx, "The plan the two install approvals bind to"))
    if plan is None:
        title = "Gates are set; the assurance plan does not exist yet"
    elif blocked:
        title = (
            "One gate is blocked before any install"
            if blocked == 1
            else f"{_capital(count_words(blocked))} gates are blocked before any install"
        )
    else:
        title = "No gate is blocked"
    return _section(
        "governance",
        "11",
        _title_within(title, "Governance and gates"),
        "Gates, controls, tests and evidence, each with owner and status.",
        blocks,
        ("C",),
    )


def _evidence(ctx: _Context) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    selected_evaluations = [
        evaluation
        for evaluation in ctx.records.evaluations
        if (evaluation.get("candidate_ref") or {}).get("id") == ctx.selected["id"]
    ]
    contract = ctx.records.contract or {}
    metric_names = {
        str(metric["id"]): str(metric.get("name") or metric["id"])
        for metric in contract.get("metrics") or []
    }
    status_word = "unknown"
    if selected_evaluations:
        evaluation = selected_evaluations[-1]
        status_word = str(evaluation.get("status"))
        # An offline evaluation runs over a fixture set: its figures are synthetic.
        fixture = _evaluation_fixture(evaluation)
        rows = []
        for index, metric in enumerate(evaluation.get("metrics") or []):
            unit = _recorded_unit(metric.get("unit"))
            result = str(metric.get("result"))
            rows.append(
                _row(
                    [
                        _text(
                            metric_names.get(
                                str(metric.get("metric_id")), str(metric.get("metric_id"))
                            )
                        ),
                        _quantity(
                            metric.get("value"),
                            unit,
                            "measured",
                            source(evaluation, "metrics", index, "value"),
                            estimator=fixture,
                            synthetic=fixture is not None,
                        ),
                        _text(str(metric.get("direction")).replace("_", " ")),
                        _quantity(
                            metric.get("threshold"),
                            unit,
                            "declared",
                            source(evaluation, "metrics", index, "threshold"),
                        ),
                        _count(
                            int(metric.get("sample_size") or 0),
                            "case",
                            "cases",
                            source(evaluation, "metrics", index, "sample_size"),
                            estimator=fixture,
                            synthetic=fixture is not None,
                        ),
                        _status(result if result in {"pass", "fail"} else "unknown", result),
                    ],
                    source(evaluation, "metrics", index),
                )
            )
        blocks.append(
            _table(
                "metrics",
                "Metrics against their thresholds",
                ["Metric", "Value", "Must be", "Threshold", "Sample", "Result"],
                rows,
            )
        )
        limitations = evaluation.get("limitations") or []
        if limitations:
            blocks.append(
                _facts(
                    [_fact("Limitations", _list(limitations), source(evaluation, "limitations"))]
                )
            )
    else:
        blocks.append(_missing_evaluation(ctx))
    observations = ctx.records.observations
    if observations:
        record = observations[-1]
        rows = []
        for index, row in enumerate(record.get("calibration") or []):
            predicted = row.get("predicted") or {}
            observed = row.get("observed") or {}
            unit = _recorded_unit(row.get("unit")) or _recorded_unit(predicted.get("unit"))
            estimator = (row.get("estimator") or {}).get("ref")
            observed_value = (
                _quantity(
                    observed.get("value"),
                    unit,
                    "measured",
                    source(record, "calibration", index, "observed", "value"),
                )
                if observed.get("status") != "unknown" and observed.get("value") is not None
                else _unknown(str(observed.get("reason") or "Not observed."))
            )
            rows.append(
                _row(
                    [
                        _text(
                            OBJECTIVE_NAMES.get(
                                str(row.get("name")), humanise(str(row.get("name")))
                            )
                        ),
                        _quantity(
                            predicted.get("value"),
                            unit,
                            "estimated",
                            source(record, "calibration", index, "predicted"),
                            lower=predicted.get("lower"),
                            upper=predicted.get("upper"),
                            estimator=estimator,
                            synthetic=estimator in ctx.synthetic_estimators,
                        ),
                        observed_value,
                    ],
                    source(record, "calibration", index),
                )
            )
        blocks.append(
            _table(
                "calibration",
                "Predicted beside observed",
                ["Measure", "Predicted", "Observed"],
                rows,
            )
        )
    else:
        blocks.append(_missing_observation())
    if not selected_evaluations:
        title = "The selected design is not evaluated yet"
    else:
        result = {"pass": "passed", "fail": "failed"}.get(status_word, "was inconclusive")
        title = f"The offline evaluation {result}; " + (
            "observations are recorded" if observations else "nothing is observed yet"
        )
    return _section(
        "evidence",
        "12",
        _title_within(title, "Evidence so far"),
        "Metrics with sample sizes and limitations; predictions beside observations.",
        blocks,
        ("E",),
    )


def _sensitivity(ctx: _Context) -> dict[str, Any]:
    explanation = ctx.explanation(ctx.selected)
    uncertainties = explanation.get("uncertainties") or []
    unresolved = [
        question
        for question in ctx.intent.get("unresolved") or []
        if question.get("status") != "resolved"
    ]
    pareto = ctx.selected.get("pareto") or {}
    facts = [
        _fact(
            "Sensitivity",
            _text(str(pareto["sensitivity_summary"]))
            if pareto.get("sensitivity_summary")
            else _unknown("The selected option records no sensitivity summary."),
            source(ctx.selected, "pareto", "sensitivity_summary"),
        ),
        _fact(
            "Uncertainties",
            _list(
                f"{humanise(str(item.get('constraint_id')))}: {item.get('reason')}"
                for item in uncertainties
            )
            if uncertainties
            else _text("None recorded."),
            source(ctx.selected, "extensions", EXPLANATION_EXTENSION, "uncertainties"),
        ),
        _fact(
            "Assumptions",
            _list(ctx.selected.get("assumptions") or [])
            if ctx.selected.get("assumptions")
            else _text("None recorded."),
            source(ctx.selected, "assumptions"),
        ),
        _fact(
            "Omissions",
            _list(ctx.selected.get("omissions") or [])
            if ctx.selected.get("omissions")
            else _text("None recorded."),
            source(ctx.selected, "omissions"),
        ),
        _fact(
            "Open questions",
            _list(str(question.get("question")) for question in unresolved)
            if unresolved
            else _text("None. Every question in the brief is answered."),
            ctx.intent_source("/unresolved"),
        ),
    ]
    open_count = len(unresolved)
    uncertain = len(uncertainties)
    title = (
        f"{_capital(count_words(open_count))} open question"
        f"{'s' if open_count != 1 else ''} and {count_words(uncertain)} "
        f"uncertaint{'ies' if uncertain != 1 else 'y'} remain"
    )
    return _section(
        "sensitivity",
        "13",
        _title_within(title, "What would change this"),
        "Sensitivity, uncertainties, assumptions, omissions and open questions.",
        [_facts(facts)],
        ("A", "D"),
    )


def _next_steps(ctx: _Context) -> dict[str, Any]:
    selected_id = ctx.selected["id"]
    plan_steps = {
        "candidate_selected": (
            f"oak assure {selected_id}",
            f"oak plan {selected_id} --target <profile>",
            *INSTALL_STEPS,
        ),
        "assurance_planned": (f"oak plan {selected_id} --target <profile>", *INSTALL_STEPS),
        "bundle_compiled": INSTALL_STEPS,
        "deployment_approved": INSTALL_STEPS[3:],
        "deployed": ("oak observe",),
        "observing": ("oak observe",),
    }
    titles = {
        "candidate_selected": "Plan assurance and compile before signing, approving and installing",
        "assurance_planned": "Compile the bundle, then sign, approve and install",
        "bundle_compiled": "Sign, approve twice and install, all from a terminal",
        "deployment_approved": "Dispatch, run the runner once and ingest its result",
        "deployed": "Installed; record what was observed next",
        "observing": "Installed and observed; observe again after changes",
    }
    lines = list(plan_steps.get(ctx.status, ()))
    blocks = [
        _paragraph(f"The case is at {ctx.status.replace('_', ' ')}.", ctx.case_source("status")),
        _commands(lines, "Text only. The report runs nothing; a person runs each command."),
    ]
    return _section(
        "next-steps",
        "14",
        titles.get(ctx.status, "Next steps"),
        "Read from the case status. The commands run only in your terminal.",
        blocks,
    )


# ----- appendices ----------------------------------------------------------------------


def _appendix_assumptions(ctx: _Context) -> dict[str, Any]:
    rows = []
    covered: set[str] = set()
    for pointer in sorted(ctx.provenance):
        entry = ctx.provenance[pointer]
        if entry.get("source") == "explicit":
            continue
        covered.add(pointer)
        value = _resolve(ctx.intent, pointer)
        mark = ctx.mark(pointer)
        who = (
            f"{entry.get('confirmed_by')}, {_when(entry.get('confirmed_at'))}"
            if entry.get("confirmed_by")
            else "not confirmed"
        )
        if isinstance(value, list):
            shown: dict[str, Any] = _list(str(item) for item in value)
        elif value is None or isinstance(value, dict):
            shown = _unknown("The intent holds no value here.")
        else:
            shown = _intent_value(ctx, pointer, value)
            if shown["type"] == "text":
                shown = {**shown, "mark": None}
        rows.append(
            _row(
                [_text(pointer), shown, _text(mark["word"], mark), _text(who)],
                ctx.intent_source(f"/provenance/{_escape(pointer)}"),
            )
        )
    for index, assumption in enumerate(ctx.case.get("assumptions") or []):
        if str(assumption.get("path")) in covered:
            continue
        rows.append(
            _row(
                [
                    _text(str(assumption.get("path"))),
                    _text(str(assumption.get("statement"))),
                    _text(
                        f"{PROVENANCE_WORDS.get(str(assumption.get('source')), 'Unknown')}, "
                        f"{assumption.get('status')}"
                    ),
                    _text("case assumption"),
                ],
                ctx.case_source("assumptions", index),
            )
        )
    blocks: list[dict[str, Any]] = (
        [
            _table(
                "provenance",
                "Values that are not facts stated in the brief",
                ["Field", "Value", "Class and status", "Who and when"],
                rows,
            )
        ]
        if rows
        else [_paragraph("Every value is a fact stated in the brief.")]
    )
    return _section(
        "appendix-assumptions",
        "A",
        "Every value not stated in the brief, with who confirmed it",
        "Field, value, class, status, and who confirmed it when.",
        blocks,
    )


def _best_and_worst(ctx: _Context, candidate: dict[str, Any]) -> tuple[list[str], list[str]]:
    best: list[str] = []
    worst: list[str] = []
    feasible = ctx.feasible()
    if candidate not in feasible or len(feasible) < 2:
        return best, worst
    for name, word in OBJECTIVE_NAMES.items():
        values = []
        for other in feasible:
            found = ctx.objective(other, name)
            if found is not None and isinstance(found[1].get("value"), (int, float)):
                values.append((other, found[1]))
        own = ctx.objective(candidate, name)
        if own is None or len(values) < 2:
            continue
        direction = own[1].get("direction")
        numbers = [objective["value"] for _, objective in values]
        top = min(numbers) if direction == "minimize" else max(numbers)
        bottom = max(numbers) if direction == "minimize" else min(numbers)
        if top == bottom:
            continue
        if own[1]["value"] == top:
            best.append(word.lower())
        elif own[1]["value"] == bottom:
            worst.append(word.lower())
    return best, worst


def _appendix_candidates(ctx: _Context) -> dict[str, Any]:
    blocks = []
    for candidate in ctx.ordered:
        best, worst = _best_and_worst(ctx, candidate)
        items = [_fact("Flag", ctx.flag(candidate), source(candidate, "pareto"))]
        for index, constraint in enumerate(candidate.get("hard_constraints") or []):
            result = str(constraint.get("result"))
            items.append(
                _fact(
                    humanise(str(constraint.get("id"))),
                    _status(
                        result if result in CONSTRAINT_WORDS else "unknown",
                        CONSTRAINT_WORDS.get(result, "unknown"),
                        str(constraint.get("reason")) if result != "pass" else None,
                    ),
                    source(candidate, "hard_constraints", index),
                )
            )
        for name, word in OBJECTIVE_NAMES.items():
            if ctx.objective(candidate, name) is not None:
                items.append(
                    _fact(
                        word,
                        ctx.objective_quantity(candidate, name),
                        source(candidate, "objectives"),
                    )
                )
        items.append(
            _fact(
                "Best of the feasible options on",
                _list(best) if best else _text("none"),
                source(candidate, "objectives"),
            )
        )
        weaknesses = [f"weakest on {item}" for item in worst] + list(candidate.get("risks") or [])
        weaknesses += list(candidate.get("omissions") or [])
        items.append(
            _fact(
                "Weaknesses",
                _list(weaknesses) if weaknesses else _text("none recorded"),
                source(candidate, "risks"),
            )
        )
        blocks.append(_facts(items, heading=ctx.name(candidate)))
    return _section(
        "appendix-candidates",
        "B",
        "One card per option, flagged by how it fared",
        "Constraints, objectives, strengths and weaknesses for each option.",
        blocks,
    )


def _appendix_controls(ctx: _Context) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    plan = ctx.records.assurance_plan
    if plan is not None:
        blocks.append(
            _table(
                "controls",
                "Assurance controls",
                ["Control", "What", "Owner", "Status"],
                [
                    _row(
                        [
                            _text(str(item.get("id"))),
                            _text(str(item.get("description"))),
                            _text(str(item.get("owner"))),
                            _status(
                                str(item.get("status"))
                                if item.get("status") in {"required", "satisfied"}
                                else "unknown",
                                str(item.get("status")),
                            ),
                        ],
                        source(plan, "controls", index),
                    )
                    for index, item in enumerate(plan.get("controls") or [])
                ],
            )
        )
    else:
        blocks.append(_missing_assurance(ctx))
    decision = ctx.records.decision
    if decision is not None:
        purpose = ((ctx.intent.get("spec") or {}).get("purpose") or {}).get("problem")
        blocks.append(
            _facts(
                [
                    _fact(
                        "Context",
                        _text(str(purpose)) if purpose else _unknown("No problem is stated."),
                        ctx.intent_source("/spec/purpose/problem"),
                    ),
                    _fact(
                        "Decision",
                        _text(f"{ctx.name(ctx.selected)}: {decision.get('rationale')}"),
                        source(decision, "rationale"),
                    ),
                    _fact(
                        "Alternatives",
                        _list(
                            f"{(item.get('candidate_ref') or {}).get('id')}: {item.get('reason')}"
                            for item in decision.get("alternatives") or []
                        ),
                        source(decision, "alternatives"),
                    ),
                    _fact(
                        "Consequences, as the records it depends on",
                        _list(decision.get("dependency_digests") or []),
                        source(decision, "dependency_digests"),
                    ),
                ],
                heading="The selection decision, as a record",
            )
        )
    if ctx.records.policy_decisions:
        blocks.append(
            _table(
                "policy-rules",
                "Policy decisions and their rules",
                ["Decision", "Rule", "Matched", "Outcome"],
                [
                    _row(
                        [
                            _text(str(decision_document.get("id"))),
                            _text(str(rule.get("rule_id"))),
                            _text("yes" if rule.get("matched") else "no"),
                            _text(str(rule.get("outcome"))),
                        ],
                        source(decision_document, "rule_results", index),
                    )
                    for decision_document in ctx.records.policy_decisions
                    for index, rule in enumerate(decision_document.get("rule_results") or [])
                ],
            )
        )
    else:
        blocks.append(
            _paragraph("The case holds no policy decision.", ctx.case_source("extensions"))
        )
    return _section(
        "appendix-controls",
        "C",
        "Controls, the decision record and policy",
        "What must hold, what was decided, and which rules applied.",
        blocks,
    )


def _appendix_estimates(ctx: _Context) -> dict[str, Any]:
    # One row per distinct way an objective was estimated, naming every option that shares it.
    grouped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for candidate in ctx.ordered:
        metadata = (candidate.get("extensions") or {}).get(ESTIMATOR_EXTENSION) or {}
        for index, objective in enumerate(candidate.get("objectives") or []):
            group_key = (
                str(objective.get("name")),
                str(objective.get("direction")),
                str(objective.get("unit")),
                str(objective.get("estimator_ref")),
                f"{objective.get('confidence')}|{metadata.get('calibration')}",
            )
            entry = grouped.setdefault(
                group_key,
                {
                    "objective": objective,
                    "candidate": candidate,
                    "index": index,
                    "labels": [],
                    "calibration": metadata.get("calibration"),
                },
            )
            entry["labels"].append(ctx.label(candidate))
    rows = []
    for entry in grouped.values():
        objective = entry["objective"]
        candidate = entry["candidate"]
        index = entry["index"]
        name = str(objective.get("name"))
        rows.append(
            _row(
                [
                    _text(OBJECTIVE_NAMES.get(name, humanise(name))),
                    _text(
                        f"{'lower' if objective.get('direction') == 'minimize' else 'higher'} "
                        f"is better, in {format_unit(str(objective.get('unit')))}"
                    ),
                    _text(str(objective.get("estimator_ref"))),
                    _quantity(
                        objective.get("confidence"),
                        "of 1",
                        "declared",
                        source(candidate, "objectives", index, "confidence"),
                    ),
                    _text(str(entry["calibration"] or "not recorded")),
                    _list(entry["labels"]),
                ],
                source(candidate, "objectives", index),
            )
        )
    blocks: list[dict[str, Any]] = [
        _table(
            "estimators",
            "Each objective's definition, estimator and confidence",
            ["Objective", "Definition", "Estimator", "Confidence", "Calibration", "Options"],
            rows,
        )
    ]
    component_rows = []
    for key in sorted(ctx.records.components):
        manifest = ctx.records.components[key]
        inputs = (manifest.get("extensions") or {}).get(COMPONENT_OBJECTIVES_EXTENSION) or {}
        # A fixture component's inputs and measurements are synthetic, not observed.
        fixture = str(manifest.get("id", "")).startswith(FIXTURE_COMPONENT_PREFIX)
        for name in sorted(inputs):
            component_rows.append(
                _row(
                    [
                        _text(str(manifest.get("id"))),
                        _text(COMPONENT_INPUT_LABELS.get(name, humanise(name))),
                        _quantity(
                            inputs[name],
                            COMPONENT_INPUT_UNITS.get(name),
                            "declared",
                            source(manifest, "extensions", COMPONENT_OBJECTIVES_EXTENSION, name),
                            estimator=str(manifest.get("id")) if fixture else None,
                            synthetic=fixture,
                        ),
                        _text("estimator input"),
                        _text("not measured"),
                    ],
                    source(manifest, "extensions", COMPONENT_OBJECTIVES_EXTENSION),
                )
            )
        for index, measurement in enumerate(manifest.get("measurements") or []):
            component_rows.append(
                _row(
                    [
                        _text(str(manifest.get("id"))),
                        _text(
                            COMPONENT_INPUT_LABELS.get(
                                str(measurement.get("metric")),
                                humanise(str(measurement.get("metric"))),
                            )
                        ),
                        _quantity(
                            measurement.get("value"),
                            _recorded_unit(measurement.get("unit")),
                            "measured",
                            source(manifest, "measurements", index, "value"),
                            estimator=(
                                str(measurement.get("evidence_ref") or manifest.get("id"))
                                if fixture
                                else None
                            ),
                            synthetic=fixture,
                        ),
                        _text(f"{measurement.get('workload')} on {measurement.get('hardware')}"),
                        _text(
                            f"{_date(measurement.get('measured_at'))}, "
                            f"{measurement.get('evidence_ref')}"
                        ),
                    ],
                    source(manifest, "measurements", index),
                )
            )
    if component_rows:
        blocks.append(
            _table(
                "component-inputs",
                "Each component's inputs",
                ["Component", "Input", "Value", "Workload and hardware", "Measured"],
                component_rows,
            )
        )
    estimators = {
        str(objective.get("estimator_ref"))
        for candidate in ctx.ordered
        for objective in candidate.get("objectives") or []
    }
    title = (
        "Every figure is a synthetic estimate from a fixture estimator"
        if estimators and all(item.startswith("fixture-") for item in estimators)
        else "Every estimate names its estimator and confidence"
    )
    return _section(
        "appendix-estimates",
        "D",
        title,
        "Objective definitions, estimators, confidence, and component inputs.",
        blocks,
    )


def _appendix_evidence(ctx: _Context) -> dict[str, Any]:
    rows = []
    for key in sorted(ctx.records.components):
        manifest = ctx.records.components[key]
        for index, evidence in enumerate(manifest.get("evidence") or []):
            rows.append(
                _row(
                    [
                        _text(str(evidence.get("title"))),
                        _text(str(manifest.get("id"))),
                        _text(str(evidence.get("source_type"))),
                        _text(str(evidence.get("version") or "not recorded")),
                        _text(str(evidence.get("uri") or "no link recorded")),
                        _text(_date(evidence.get("checked_at"))),
                        _quantity(
                            evidence.get("confidence"),
                            "of 1",
                            "declared",
                            source(manifest, "evidence", index, "confidence"),
                        ),
                    ],
                    source(manifest, "evidence", index),
                )
            )
    blocks: list[dict[str, Any]] = [
        _table(
            "evidence",
            "Evidence behind each component",
            ["Title", "Component", "Source type", "Version", "Link", "Checked", "Confidence"],
            rows,
        )
        if rows
        else _paragraph("No component evidence is recorded.")
    ]
    snapshot = ctx.records.snapshot
    if snapshot is not None:
        blocks.append(
            _facts(
                [
                    _fact("Snapshot", _text(str(snapshot.get("id"))), source(snapshot, "id")),
                    _fact(
                        "Valid at",
                        _text(_when(snapshot.get("valid_at"))),
                        source(snapshot, "valid_at"),
                    ),
                    _fact(
                        "Policy",
                        _text(str(snapshot.get("policy_version"))),
                        source(snapshot, "policy_version"),
                    ),
                    _fact(
                        "Eligible components",
                        _list(snapshot.get("eligible_manifest_ids") or []),
                        source(snapshot, "eligible_manifest_ids"),
                    ),
                    _fact(
                        "Rejected components",
                        _list(snapshot.get("rejected_manifest_ids") or [])
                        if snapshot.get("rejected_manifest_ids")
                        else _text("none"),
                        source(snapshot, "rejected_manifest_ids"),
                    ),
                ],
                heading="The catalogue snapshot",
            )
        )
    requirement_ids = sorted(
        {
            str(item)
            for candidate in ctx.ordered
            for constraint in candidate.get("hard_constraints") or []
            for item in constraint.get("requirement_ids") or []
        }
    )
    blocks.append(
        _facts(
            [
                _fact(
                    "Requirements cited",
                    _list(requirement_ids) if requirement_ids else _text("none"),
                    source(ctx.selected, "hard_constraints"),
                ),
                _fact(
                    "Evidence the selected option cites",
                    _list(ctx.selected.get("evidence_refs") or [])
                    if ctx.selected.get("evidence_refs")
                    else _text("none"),
                    source(ctx.selected, "evidence_refs"),
                ),
            ]
        )
    )
    return _section(
        "appendix-evidence",
        "E",
        "Evidence behind the components, with dates",
        "Titles, sources, versions and check dates; the snapshot's validity.",
        blocks,
    )


def _appendix_record(ctx: _Context, oak_version: str, renderer: dict[str, Any]) -> dict[str, Any]:
    rows = [
        _row(
            [
                _text(str(item["kind"]).replace("_", " ")),
                _text(str(item["id"])),
                _text(str(item["version"])),
                _text(str(item["digest"])),
            ],
            f"{item['id']}@{item['version']}#",
        )
        for item in ctx.records.inputs
    ]
    libraries = ", ".join(
        f"{name} {version}" for name, version in sorted((renderer.get("libraries") or {}).items())
    )
    return _section(
        "appendix-record",
        "F",
        "Every input record, by digest",
        "Identifiers, versions and digests; the composer and renderer versions.",
        [
            _table(
                "inputs",
                "The records this report was composed from",
                ["Kind", "Identifier", "Version", "Digest"],
                rows,
            ),
            _facts(
                [
                    _fact("Composer", _text(COMPOSER_VERSION), TEMPLATE),
                    _fact(
                        "Renderer",
                        _text(f"{renderer.get('name')} {renderer.get('version')}"),
                        TEMPLATE,
                    ),
                    _fact("Renderer libraries", _text(libraries or "none"), TEMPLATE),
                    _fact("OAK version", _text(oak_version), TEMPLATE),
                ]
            ),
        ],
    )


# ----- the document --------------------------------------------------------------------


def report_document(
    records: ReportRecords,
    *,
    report_id: str,
    generated_at: str,
    generated_by: str,
    oak_version: str,
    renderer: dict[str, Any],
    narrative: Narrative | None = None,
) -> dict[str, Any]:
    """The architecture report for one case, from its records alone.

    ``generated_at`` is the recording time and also the instant approval expiry is judged
    at, so the same recording gives the same words. ``narrative`` holds notes a model
    proposed and OAK already checked; without it the report makes no claim about a model.
    """

    status = str(records.case["status"])
    if status not in RECORDABLE_STATUSES:
        raise ValueError(f"a report is composed from candidate_selected onwards, not {status}")
    ctx = _Context(records, generated_at)
    sections = [
        _cover(ctx, generated_by),
        _method(ctx, oak_version, narrative),
        _asked(ctx),
        _options(ctx),
        _risks(ctx),
        _comparison(ctx),
        _recommendation(ctx),
        _cost(ctx),
        _architecture(ctx),
        _security(ctx),
        _governance(ctx),
        _evidence(ctx),
        _sensitivity(ctx),
        _next_steps(ctx),
        _appendix_assumptions(ctx),
        _appendix_candidates(ctx),
        _appendix_controls(ctx),
        _appendix_estimates(ctx),
        _appendix_evidence(ctx),
        _appendix_record(ctx, oak_version, renderer),
    ]
    if narrative is not None:
        reference = narrative.narrative_ref
        for section in sections:
            text = narrative.notes.get(section["number"])
            if text is not None and section["number"] in MAIN_SECTIONS:
                section["note"] = {
                    "text": text,
                    "label": NOTE_LABEL,
                    "model": narrative.model,
                    "source": f"{reference['id']}@{reference['version']}#/notes",
                }
    return {
        "schema_version": SCHEMA_VERSION,
        "id": report_id,
        "version": "0.1.0",
        "case_ref": dict(records.case_ref),
        "case_status": status,
        "generated_at": generated_at,
        "generated_by": generated_by,
        "oak_version": oak_version,
        "composer_version": COMPOSER_VERSION,
        "renderer": renderer,
        "narrative": {
            "mode": narrative.mode if narrative else "deterministic",
            "narrative_ref": dict(narrative.narrative_ref) if narrative else None,
            "label": NOTE_LABEL if narrative else None,
            "model": narrative.model if narrative else None,
        },
        "sections": sections,
        "inputs": [dict(item) for item in records.inputs],
        "extensions": {},
    }


def narrator_facts(document: dict[str, Any]) -> dict[str, Any]:
    """What a model in a model mode is shown: each main slide's own words, nothing else.

    Titles, subtitles and the text of every fact, cell, callout and paragraph on slides
    1 to 14. The brief document, credentials, digests and the appendices are not included.
    """

    slides = []
    for section in document["sections"]:
        if section["number"] not in MAIN_SECTIONS:
            continue
        lines: list[str] = []
        for block in section["blocks"]:
            lines.extend(_DIGEST.sub("(digest)", line) for line in _block_lines(block))
        slides.append(
            {
                "section": section["number"],
                "title": section["title"],
                "subtitle": section["subtitle"],
                "lines": lines,
            }
        )
    return {"report_id": document["id"], "slides": slides}


def value_text(value: dict[str, Any]) -> str:
    kind = value["type"]
    if kind == "text":
        return str(value["text"])
    if kind == "list":
        return "; ".join(value["items"])
    if kind == "quantity":
        return str(value["text"])
    if kind == "status":
        return f"{value['word']}" + (f" ({value['reason']})" if value.get("reason") else "")
    return f"unknown: {value['reason']}"


def _block_lines(block: dict[str, Any]) -> list[str]:
    kind = block["kind"]
    if kind == "facts":
        return [f"{item['label']}: {value_text(item['value'])}" for item in block["items"]]
    if kind == "table":
        return [" | ".join(block["columns"])] + [
            " | ".join(value_text(cell) for cell in row["cells"]) for row in block["rows"]
        ]
    if kind in {"callout", "quote"}:
        return [f"{block['label']}: {block['text']}"]
    if kind == "paragraph":
        return [str(block["text"])]
    if kind == "commands":
        return list(block["lines"])
    if kind == "not_yet":
        return [f"Not yet: {block['what']} ({block['step']})"]
    if kind in {"diagram", "chart"}:
        return [str(block["description"])]
    return []
