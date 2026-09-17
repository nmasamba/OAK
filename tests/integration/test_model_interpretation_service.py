# SPDX-License-Identifier: Apache-2.0
"""OAK-S9-004: the model path through ``DesignCaseService`` with a binding fake adapter.

What is pinned: the model path commits intent, proposal, event and case in one mutation
and only when it ran; a request for the model with no adapter, or a provider failure,
commits nothing; ``auto`` uses the model only for a prose brief; the deterministic path
carries no model-specific key anywhere; every model-proposed value keeps the case in
confirmation until it is confirmed, corrected or rejected; two rounds of five answers reach
``ready_for_candidates``.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from oak.adapters.catalogue import LocalCatalogue
from oak.adapters.intake import LocalBriefIntake
from oak.adapters.persistence import FileWorkspaceRepository
from oak.adapters.targets import LocalTargetProfile
from oak.application import CandidatePlanningService, CommandContext, DesignCaseService
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry
from oak.domain import ArtifactReference, OAKError
from oak.ports import ModelInterpreterPort
from tests.model_support import BindingFakeModelInterpreter, model_factory

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
PROSE = ROOT / "examples/briefs/public-manual-qa-prose.md"
STRUCTURED = ROOT / "examples/briefs/public-manual-qa.yaml"
T0 = "2026-08-17T10:00:00Z"
T1 = "2026-08-17T10:05:00Z"
T2 = "2026-08-17T10:10:00Z"
T3 = "2026-08-17T10:15:00Z"
PROPOSAL_REF = "oak.community/interpretation_proposal_ref"
INTERPRETER = "oak.community/interpreter"
REGISTRY = SchemaRegistry.from_directory(ROOT / "schemas")


def _context(key: str, expected: str | None, occurred_at: str) -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key=key,
        expected_version=expected,
        correlation_id=f"correlation-{key}",
        interface_origin="cli",
        occurred_at=occurred_at,
    )


def _service(
    workspace: Path, adapter: ModelInterpreterPort | None, *, with_factory: bool = True
) -> DesignCaseService:
    repository = FileWorkspaceRepository(workspace, REGISTRY)
    service = DesignCaseService(
        repository,
        LocalBriefIntake(),
        DeterministicBriefInterpreter(),
        REGISTRY,
        model_interpreter_factory=model_factory(adapter) if with_factory else None,
    )
    service.initialize(workspace_id="workspace.model-path", tenant_id="local", created_at=T0)
    return service


def _manifest(workspace: Path) -> dict[str, Any]:
    return FileWorkspaceRepository(workspace, REGISTRY).manifest()


def _kinds(workspace: Path) -> list[str]:
    return sorted(entry["kind"] for entry in _manifest(workspace)["artifact_index"])


def _events(workspace: Path) -> list[dict[str, Any]]:
    repository = FileWorkspaceRepository(workspace, REGISTRY)
    return [
        repository.read_json_artifact(ArtifactReference.from_document(entry))
        for entry in repository.manifest()["audit_events"]
    ]


def _answers(case_id: str, answers: list[tuple[str, str, Any]]) -> dict[str, Any]:
    return {
        "answers_version": "0.1.0",
        "design_case_id": case_id,
        "answers": [
            {
                "question_id": question_id,
                "decision": decision,
                "value": value,
                "rationale": f"Reviewed {question_id}.",
            }
            for question_id, decision, value in answers
        ],
    }


def _pointer(document: dict[str, Any], path: str) -> Any:
    current: Any = document
    for part in path.split("/")[1:]:
        key = part.replace("~1", "/").replace("~0", "~")
        current = current[int(key)] if isinstance(current, list) else current[key]
    return current


def test_the_model_path_commits_intent_proposal_event_and_case_in_one_mutation(
    tmp_path: Path,
) -> None:
    adapter = BindingFakeModelInterpreter()
    service = _service(tmp_path / "ws", adapter)

    result = service.design(PROSE, _context("design-prose-model-0001", None, T0))

    assert result.interpreter == "model"
    assert result.case["status"] == "needs_confirmation"
    assert result.case["version"] == "0.1.1"
    assert result.intent is not None
    intent = result.intent
    REGISTRY.validate("system-intent.schema.json", intent)
    manifest = _manifest(tmp_path / "ws")
    assert manifest["version"] == 2
    assert len(manifest["audit_events"]) == 2
    assert _kinds(tmp_path / "ws") == sorted(
        [
            "brief_source",
            "source_record",
            "audit_event",
            "design_case",
            "audit_event",
            "design_case",
            "system_intent",
            "interpretation_proposal",
        ]
    )
    proposal_ref = ArtifactReference.from_document(intent["extensions"][PROPOSAL_REF])
    repository = FileWorkspaceRepository(tmp_path / "ws", REGISTRY)
    proposal = repository.read_json_artifact(proposal_ref)
    REGISTRY.validate("interpretation-proposal.schema.json", proposal)
    assert proposal["version"] == "0.1.0"
    assert proposal["source_ref"] == intent["extensions"]["oak.community/source_record"]
    assert proposal["proposed_claims"][0]["path"] == "/spec/decision/autonomy"
    # The adapter saw the brief bytes once and the record it was asked to bind to.
    assert adapter.calls == [
        {"source_id": "source.public-manual-qa-prose", "content_bytes": PROSE.stat().st_size}
    ]
    # Model values carry model provenance; the explicit brief text kept its own.
    assert intent["spec"]["decision"]["autonomy"] == "recommend_only"
    assert intent["provenance"]["/spec/decision/autonomy"]["source"] == "model_proposed"
    assert intent["provenance"]["/spec/decision/autonomy"]["evidence_refs"] == [proposal["id"]]
    assert intent["provenance"]["/spec/purpose/problem"]["source"] == "explicit"
    findings = intent["extensions"]["oak.community/findings"]
    assert [f["path"] for f in findings if f["code"] == "OAK-INT-PROPOSAL-REJECTED"] == [
        "/spec/purpose/problem"
    ]
    assert [f["path"] for f in findings if f["code"] == "OAK-INT-PROPOSAL-UNANSWERED"] == [
        "/spec/regulatory_nexus/eu_nexus"
    ]
    # The audit event names the interpreter without carrying prompt or response content.
    event = _events(tmp_path / "ws")[1]
    assert event["event_type"] == "brief_interpreted"
    assert event["extensions"] == {
        INTERPRETER: {
            "kind": "model",
            "family": "huggingface",
            "model_id": "openai/gpt-oss-120b",
            "provider_route": "fake",
            "proposal_digest": proposal_ref.digest,
        }
    }
    question_ids = [q["id"] for q in result.case["unresolved_questions"]]
    # Critical before high; within a materiality the deterministic questions (hint 0) come
    # first and model sections follow in ascending confidence (0.40 < 0.55; 0.62 < 0.70).
    assert question_ids == [
        "question.model-hardware",
        "question.production-use",
        "question.model.stakeholders",
        "question.model.data",
        "question.model.decision",
        "question.model.operational_contract",
    ]
    assert len(service.questions().questions) == 6
    model_assumptions = [a for a in result.case["assumptions"] if a["source"] == "model_proposed"]
    assert {a["path"] for a in model_assumptions} == {
        "/spec/decision/autonomy",
        "/spec/data/classifications/0",
        "/spec/stakeholders/accountable_owner",
        "/spec/operational_contract/latency_p95_ms",
    }
    REGISTRY.validate("design-case.schema.json", result.case)

    retry = service.design(PROSE, _context("design-prose-model-0001", None, T0))
    assert retry.duplicate is True
    assert retry.interpreter == "model"
    assert retry.case == result.case
    assert len(adapter.calls) == 1


def test_requesting_the_model_without_an_adapter_commits_nothing(tmp_path: Path) -> None:
    for label, service in (
        ("no-factory", _service(tmp_path / "a", None, with_factory=False)),
        ("factory-returns-none", _service(tmp_path / "b", None)),
    ):
        workspace = tmp_path / ("a" if label == "no-factory" else "b")
        with pytest.raises(OAKError) as refused:
            service.design(
                PROSE, _context("design-prose-model-0002", None, T0), interpreter="model"
            )
        assert refused.value.code == "OAK-MODEL-NOT-CONFIGURED", label
        assert "oak models select" in refused.value.message
        # The create step committed; the interpret step did not.
        assert service.current().case["status"] == "draft", label
        assert service.current().case["version"] == "0.1.0", label
        before = _manifest(workspace)
        with pytest.raises(OAKError) as again:
            service.interpret(_context("interpret-model-0002", "0.1.0", T1), interpreter="model")
        assert again.value.code == "OAK-MODEL-NOT-CONFIGURED", label
        assert _manifest(workspace) == before, label
        # auto falls back to the deterministic interpreter for the same case.
        result = service.interpret(_context("interpret-auto-0002", "0.1.0", T1))
        assert result.interpreter == "deterministic", label
        assert result.intent is not None
        assert PROPOSAL_REF not in result.intent["extensions"], label


def test_a_provider_failure_commits_nothing(tmp_path: Path) -> None:
    service = _service(tmp_path / "ws", BindingFakeModelInterpreter(unavailable=True))
    with pytest.raises(OAKError) as failed:
        service.design(PROSE, _context("design-prose-model-0003", None, T0))
    assert failed.value.code == "OAK-INTERPRETER-UNAVAILABLE"
    assert failed.value.retriable is True
    manifest = _manifest(tmp_path / "ws")
    assert manifest["version"] == 1
    assert len(manifest["audit_events"]) == 1
    assert "interpretation_proposal" not in _kinds(tmp_path / "ws")
    assert service.current().case["status"] == "draft"


def test_auto_uses_the_model_only_for_a_prose_brief(tmp_path: Path) -> None:
    adapter = BindingFakeModelInterpreter()
    structured = _service(tmp_path / "structured", adapter)
    result = structured.design(STRUCTURED, _context("design-structured-auto-0004", None, T0))
    assert result.interpreter == "deterministic"
    assert adapter.calls == []
    assert result.intent is not None
    assert PROPOSAL_REF not in result.intent["extensions"]

    prose = _service(tmp_path / "prose", adapter)
    assert prose.design(PROSE, _context("design-prose-auto-0004", None, T0)).interpreter == (
        "model"
    )
    assert len(adapter.calls) == 1

    explicit = _service(tmp_path / "explicit", adapter)
    forced = explicit.design(
        STRUCTURED, _context("design-structured-model-0004", None, T0), interpreter="model"
    )
    assert forced.interpreter == "model"
    assert len(adapter.calls) == 2
    assert forced.intent is not None
    # Every explicit brief value survived; only genuinely unstated fields were proposed.
    assert forced.intent["provenance"]["/spec/hardware/ram_gib"]["source"] == "explicit"
    assert forced.intent["provenance"]["/spec/stakeholders/accountable_owner"]["source"] == (
        "model_proposed"
    )


def test_the_deterministic_path_is_identical_with_or_without_a_configured_model(
    tmp_path: Path,
) -> None:
    adapter = BindingFakeModelInterpreter()
    with_model = _service(tmp_path / "with", adapter)
    without = _service(tmp_path / "without", None, with_factory=False)
    context = _context("design-prose-deterministic-0005", None, T0)

    left = with_model.design(PROSE, context, interpreter="deterministic")
    right = without.design(PROSE, context)

    assert adapter.calls == []
    assert left.interpreter == right.interpreter == "deterministic"
    assert left.intent == right.intent
    assert left.intent is not None
    assert set(left.intent["extensions"]) == {
        "oak.community/findings",
        "oak.community/source_record",
    }
    assert left.case["intent_ref"] == right.case["intent_ref"]
    assert left.case == right.case
    assert _events(tmp_path / "with") == _events(tmp_path / "without")
    assert all(event["extensions"] == {} for event in _events(tmp_path / "with"))
    assert _kinds(tmp_path / "with") == _kinds(tmp_path / "without")
    assert "interpretation_proposal" not in _kinds(tmp_path / "with")


def test_an_unknown_interpreter_mode_is_refused(tmp_path: Path) -> None:
    service = _service(tmp_path / "ws", BindingFakeModelInterpreter())
    with pytest.raises(OAKError) as refused:
        service.design(PROSE, _context("design-prose-mode-0006", None, T0), interpreter="fast")
    assert refused.value.code == "OAK-INTERPRETER-MODE"


def test_model_values_keep_the_case_in_confirmation_until_two_rounds_resolve_them(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "ws"
    service = _service(workspace, BindingFakeModelInterpreter())
    planning = CandidatePlanningService(
        FileWorkspaceRepository(workspace, REGISTRY),
        LocalCatalogue(ROOT / "catalogue", REGISTRY),
        LocalTargetProfile(REGISTRY),
        REGISTRY,
    )
    designed = service.design(PROSE, _context("design-prose-rounds-0007", None, T0))
    case_id = str(designed.case["id"])
    assert designed.intent is not None
    intent = designed.intent
    with pytest.raises(OAKError) as too_early:
        planning.candidates(_context("generate-rounds-0007", "0.1.1", T1))
    assert too_early.value.code == "OAK-CANDIDATES-STATE"

    # Round one: the five presented questions. Section questions are confirmed with the
    # section object the intent currently holds; the two deterministic gaps are corrected.
    # Answers apply in order, so the `data` section is confirmed before the production-data
    # correction adds a value inside it.
    first_round = _answers(
        case_id,
        [
            (
                "question.model-hardware",
                "correct",
                {"cpu_architectures": ["x86_64"], "ram_gib": 32, "storage_gib": 100},
            ),
            ("question.model.data", "confirm", _pointer(intent, "/spec/data")),
            ("question.production-use", "correct", False),
            ("question.model.stakeholders", "confirm", _pointer(intent, "/spec/stakeholders")),
            (
                "question.model.operational_contract",
                "correct",
                {"latency_p95_ms": 1500, "modes": ["interactive"]},
            ),
        ],
    )
    after_first = service.confirm(first_round, _context("confirm-rounds-0007-a", "0.1.1", T1))
    assert after_first.case["status"] == "needs_confirmation"
    assert after_first.case["version"] == "0.1.2"
    assert after_first.intent is not None
    assert after_first.intent["status"] == "draft"
    open_ids = [q["id"] for q in after_first.case["unresolved_questions"] if q["status"] == "open"]
    assert open_ids == ["question.model.decision"]
    provenance = after_first.intent["provenance"]
    assert provenance["/spec/data/classifications/0"]["confirmation_required"] is False
    assert provenance["/spec/data/classifications/0"]["confirmed_by"] == "local-user"
    assert provenance["/spec/operational_contract/latency_p95_ms"]["source"] == ("user_correction")
    assert provenance["/spec/operational_contract/modes/0"]["source"] == "user_correction"
    assert provenance["/spec/decision/autonomy"]["confirmation_required"] is True
    statuses = {a["path"]: a["status"] for a in after_first.case["assumptions"]}
    assert statuses["/spec/data/classifications/0"] == "confirmed"
    assert statuses["/spec/operational_contract/latency_p95_ms"] == "corrected"
    assert statuses["/spec/decision/autonomy"] == "proposed"
    with pytest.raises(OAKError) as still_early:
        planning.candidates(_context("generate-rounds-0007-b", "0.1.2", T2))
    assert still_early.value.code == "OAK-CANDIDATES-STATE"

    # Round two: the last model section, confirmed as proposed.
    second_round = _answers(
        case_id,
        [("question.model.decision", "confirm", _pointer(after_first.intent, "/spec/decision"))],
    )
    after_second = service.confirm(second_round, _context("confirm-rounds-0007-b", "0.1.2", T2))
    assert after_second.case["status"] == "ready_for_candidates"
    assert after_second.intent is not None
    assert after_second.intent["status"] == "clarified"
    assert not any(
        record["source"] == "model_proposed" and record["confirmation_required"]
        for record in after_second.intent["provenance"].values()
    )
    generated = planning.candidates(_context("generate-rounds-0007-c", "0.1.3", T3))
    assert generated.case["status"] == "candidates_ready"


def test_rejecting_a_section_question_drops_only_the_model_values(tmp_path: Path) -> None:
    service = _service(tmp_path / "ws", BindingFakeModelInterpreter())
    designed = service.design(PROSE, _context("design-prose-reject-0008", None, T0))
    case_id = str(designed.case["id"])
    assert designed.intent is not None
    before = copy.deepcopy(designed.intent)

    rejected = service.confirm(
        _answers(case_id, [("question.model.data", "reject", None)]),
        _context("confirm-reject-0008-a", "0.1.1", T1),
    )
    assert rejected.intent is not None
    intent = rejected.intent
    assert intent["spec"]["data"] == {}
    assert intent["spec"]["purpose"] == before["spec"]["purpose"]
    assert intent["spec"]["decision"] == before["spec"]["decision"]
    assert "/spec/data/classifications/0" not in intent["provenance"]
    assert (
        intent["provenance"]["/spec/purpose/problem"]
        == before["provenance"]["/spec/purpose/problem"]
    )
    assert intent["provenance"]["/spec/decision/autonomy"]["source"] == "model_proposed"
    REGISTRY.validate("system-intent.schema.json", intent)
    question = next(
        q for q in rejected.case["unresolved_questions"] if q["id"] == "question.model.data"
    )
    assert question["status"] == "open"
    assert rejected.case["status"] == "needs_confirmation"

    corrected = service.confirm(
        _answers(case_id, [("question.model.data", "correct", {"classifications": ["public"]})]),
        _context("confirm-reject-0008-b", "0.1.2", T2),
    )
    assert corrected.intent is not None
    assert corrected.intent["spec"]["data"] == {"classifications": ["public"]}
    assert corrected.intent["provenance"]["/spec/data/classifications/0"]["source"] == (
        "user_correction"
    )
    question = next(
        q for q in corrected.case["unresolved_questions"] if q["id"] == "question.model.data"
    )
    assert question["status"] == "resolved"


def test_rejecting_the_deterministic_hardware_question_empties_the_section_without_crashing(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "ws", None, with_factory=False)
    designed = service.design(STRUCTURED, _context("design-structured-reject-0009", None, T0))
    case_id = str(designed.case["id"])
    rejected = service.confirm(
        _answers(case_id, [("question.model-hardware", "reject", None)]),
        _context("confirm-structured-reject-0009", "0.1.1", T1),
    )
    assert rejected.intent is not None
    assert rejected.intent["spec"]["hardware"] == {}
    assert not any(path.startswith("/spec/hardware/") for path in rejected.intent["provenance"])
    REGISTRY.validate("system-intent.schema.json", rejected.intent)
    assert rejected.case["status"] == "needs_confirmation"
