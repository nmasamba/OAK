# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-039: a scan's proposal enters a case only when the user confirms it."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from oak.adapters.catalogue import ResearchVocabularyLoader
from oak.application import CommandContext
from oak.application.design_case import HARDWARE_PROPOSAL_EXTENSION, HARDWARE_SCAN_EXTENSION
from oak.bootstrap import (
    canonical_catalogue_directory,
    create_candidate_planning_service,
    create_design_case_service,
)
from oak.compiler.research_terms import classify_hardware
from oak.contracts import ContractValidationError, load_yaml_document
from oak.domain import ArtifactReference, OAKError

ROOT = Path(__file__).resolve().parents[2]
STAMP = "2026-11-02T12:00:00Z"


def _context(key: str, version: str | None, minute: int = 0) -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key=f"hardware-case-{key}-0001",
        expected_version=version,
        correlation_id=f"correlation-{key}",
        interface_origin="cli",
        occurred_at=f"2026-11-02T12:{minute:02d}:00Z",
    )


def _scan(accelerators: list[dict[str, Any]] | None) -> dict[str, Any]:
    """A Linux x86_64 scan with 32 GiB, so only the accelerators differ from the brief."""

    return {
        "platform": {"operating_system": "linux", "architecture": "x86_64"},
        "cpu": {
            "model": "AMD EPYC 7763 64-Core Processor",
            "physical_cores": 8,
            "logical_cores": 16,
        },
        "memory": {"ram_gib": 32.0, "unified": False},
        "storage_gib": 500.0,
        "accelerators": accelerators,
        "prerequisites": [
            {"name": "docker", "state": "present"},
            {"name": "uv", "state": "present"},
        ],
        "unknown": [],
        "tools": [
            {"name": "lscpu", "status": "ran"},
            {"name": "nvidia-smi", "status": "ran"},
            {"name": "rocm-smi", "status": "ran"},
        ],
    }


RTX_4090 = {
    "vendor": "nvidia",
    "model": "NVIDIA GeForce RTX 4090",
    "memory_gib": 24.0,
    "unified_memory": False,
    "runtime": "cuda",
    "driver_version": "550.54.15",
}


def _case(tmp_path: Path, *, ready: bool) -> Any:
    design = create_design_case_service(tmp_path / "workspace")
    design.initialize(workspace_id="workspace.hardware", tenant_id="local", created_at=STAMP)
    design.design(ROOT / "examples/briefs/public-manual-qa.yaml", _context("design", None))
    if ready:
        answers = load_yaml_document(
            (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
        )
        design.confirm(answers, _context("confirm", "0.1.1", 1))
    return design


def _events(design: Any) -> list[str]:
    repository = design._repository
    return [
        repository.read_json_artifact(ArtifactReference.from_document(reference))["event_type"]
        for reference in repository.manifest()["audit_events"]
    ]


def test_a_proposal_changes_no_intent_value_until_it_is_confirmed(tmp_path: Path) -> None:
    design = _case(tmp_path, ready=True)
    before = design.current()

    proposed = design.propose_hardware(_scan([RTX_4090]), _context("propose", "0.1.2", 2))

    assert proposed.case["status"] == "ready_for_candidates"
    reference = proposed.case["extensions"][HARDWARE_PROPOSAL_EXTENSION]
    assert reference["id"].startswith("hardware-proposal.public-manual-qa.")
    assert proposed.intent == before.intent, "a proposal alone changes nothing the compiler reads"
    assert _events(design)[-1] == "hardware_proposed"

    confirmed = design.confirm_hardware(reference["id"], _context("accept", "0.1.3", 3))

    hardware = confirmed.intent["spec"]["hardware"]
    assert hardware["accelerators"] == ["nvidia-cuda"]
    assert hardware["vram_gib"] == 24.0
    assert hardware["drivers"] == ["nvidia-driver-550.54.15"]
    assert hardware["cpu_architectures"] == ["x86_64"]
    record = confirmed.intent["provenance"]["/spec/hardware/accelerators/0"]
    assert record["source"] == "measured"
    assert record["evidence_refs"] == [reference["id"]]
    assert (record["confirmed_by"], record["confirmation_required"]) == ("local-user", False)
    assert confirmed.intent["extensions"][HARDWARE_SCAN_EXTENSION]["proposal_ref"] == reference
    assert confirmed.case["status"] == "ready_for_candidates"
    assert _events(design)[-1] == "hardware_confirmed"


def test_confirming_answers_the_hardware_question_and_no_other(tmp_path: Path) -> None:
    design = _case(tmp_path, ready=False)
    before = {
        question["path"]: question["status"]
        for question in design.current().case["unresolved_questions"]
    }
    assert before["/spec/hardware"] == "open"

    proposed = design.propose_hardware(_scan([]), _context("propose", "0.1.1", 2))
    reference = proposed.case["extensions"][HARDWARE_PROPOSAL_EXTENSION]
    confirmed = design.confirm_hardware(reference["id"], _context("accept", "0.1.2", 3))

    after = {
        question["path"]: question["status"] for question in confirmed.case["unresolved_questions"]
    }
    assert after["/spec/hardware"] == "resolved", "every hardware value was measured"
    assert {path: status for path, status in after.items() if path != "/spec/hardware"} == {
        path: status for path, status in before.items() if path != "/spec/hardware"
    }, "the scan answers nothing but the hardware"
    assert confirmed.case["status"] == "needs_confirmation", "the other questions stay open"
    assert confirmed.intent["spec"]["hardware"]["accelerators"] == []
    unresolved = {item["path"]: item["status"] for item in confirmed.intent["unresolved"]}
    assert unresolved["/spec/hardware"] == "resolved"


def test_a_value_the_scan_did_not_measure_keeps_the_section_open(tmp_path: Path) -> None:
    design = _case(tmp_path, ready=False)
    unmeasured = _scan(None)
    unmeasured["storage_gib"] = None
    proposed = design.propose_hardware(unmeasured, _context("propose", "0.1.1", 2))
    reference = proposed.case["extensions"][HARDWARE_PROPOSAL_EXTENSION]
    confirmed = design.confirm_hardware(reference["id"], _context("accept", "0.1.2", 3))

    statuses = {
        question["path"]: question["status"] for question in confirmed.case["unresolved_questions"]
    }
    assert statuses["/spec/hardware"] == "open", "the brief's storage still needs the user"
    assert confirmed.intent["spec"]["hardware"]["storage_gib"] == 100, "the brief's value stays"
    assert confirmed.intent["provenance"]["/spec/hardware/storage_gib"]["source"] != "measured"


@pytest.mark.parametrize(
    ("accelerators", "hardware_class", "gpu_result"),
    [
        ([], "cpu-medium", "fail"),
        ([RTX_4090], "accelerator-medium", "fail"),
    ],
)
def test_a_confirmed_profile_reaches_the_constraints_and_the_hardware_class(
    tmp_path: Path,
    accelerators: list[dict[str, Any]],
    hardware_class: str,
    gpu_result: str,
) -> None:
    """The rules already define these: a component that needs `fixture-gpu` is unknown while
    the brief declares no accelerator, and fails once a confirmed scan says which ones
    exist; research's class follows the confirmed values."""

    workspace = tmp_path / "workspace"
    design = _case(tmp_path, ready=True)
    planning = create_candidate_planning_service(workspace)
    vocabulary = ResearchVocabularyLoader(canonical_catalogue_directory()).load()
    assert classify_hardware(design.current().intent, vocabulary) == "unknown"
    before = _hardware_results(planning, workspace, "before", "0.1.2", copy_to=tmp_path / "copy")

    proposed = design.propose_hardware(_scan(accelerators), _context("propose", "0.1.2", 2))
    reference = proposed.case["extensions"][HARDWARE_PROPOSAL_EXTENSION]
    confirmed = design.confirm_hardware(reference["id"], _context("accept", "0.1.3", 3))
    assert classify_hardware(confirmed.intent, vocabulary) == hardware_class
    after = _hardware_results(planning, workspace, "after", "0.1.4")

    assert set(before.values()) == {"pass", "unknown"}
    assert set(after.values()) == {"pass", gpu_result}
    assert {result for result in before.values() if result != "pass"} == {"unknown"}
    assert {candidate for candidate, result in after.items() if result == gpu_result} == {
        candidate for candidate, result in before.items() if result == "unknown"
    }


def _hardware_results(
    planning: Any, workspace: Path, key: str, version: str, copy_to: Path | None = None
) -> dict[str, str]:
    import shutil

    if copy_to is not None:
        shutil.copytree(workspace, copy_to)
        planning = create_candidate_planning_service(copy_to)
    planning.candidates(_context(f"candidates-{key}", version, 4))
    return {
        str(candidate["id"]): next(
            str(item["result"])
            for item in candidate["hard_constraints"]
            if item["id"] == "constraint.hardware"
        )
        for candidate in planning.list_candidates()
    }


def test_only_the_pending_proposal_can_be_confirmed_and_only_once(tmp_path: Path) -> None:
    design = _case(tmp_path, ready=True)
    first = design.propose_hardware(_scan([]), _context("first", "0.1.2", 2))
    first_id = first.case["extensions"][HARDWARE_PROPOSAL_EXTENSION]["id"]
    second = design.propose_hardware(_scan([RTX_4090]), _context("second", "0.1.3", 3))
    second_id = second.case["extensions"][HARDWARE_PROPOSAL_EXTENSION]["id"]
    assert first_id != second_id

    with pytest.raises(OAKError) as replaced:
        design.confirm_hardware(first_id, _context("stale", "0.1.4", 4))
    assert replaced.value.code == "OAK-HARDWARE-PROPOSAL"

    design.confirm_hardware(second_id, _context("accept", "0.1.4", 5))
    again = design.confirm_hardware(second_id, _context("accept", "0.1.4", 5))
    assert again.duplicate is True, "the same request is a retry"
    with pytest.raises(OAKError) as twice:
        design.confirm_hardware(second_id, _context("twice", "0.1.5", 6))
    assert twice.value.code == "OAK-HARDWARE-PROPOSAL"


def test_a_scan_cannot_carry_an_identifier_or_an_extra_field(tmp_path: Path) -> None:
    design = _case(tmp_path, ready=True)

    with_serial = _scan([RTX_4090])
    with_serial["cpu"]["serial_number"] = "C02SERIAL0001"
    with pytest.raises(ContractValidationError):
        design.propose_hardware(with_serial, _context("serial", "0.1.2", 2))

    gpu = dict(RTX_4090, uuid="GPU-00000000-0000-0000-0000-000000000000")
    with pytest.raises(ContractValidationError):
        design.propose_hardware(_scan([gpu]), _context("uuid", "0.1.2", 3))

    extra = {**_scan([]), "hostname": "laptop.local"}
    with pytest.raises(OAKError) as caught:
        design.propose_hardware(extra, _context("host", "0.1.2", 4))
    assert caught.value.code == "OAK-HARDWARE-PROPOSAL"
    assert _events(design)[-1] == "claims_confirmed", "nothing was recorded"


def test_a_proposal_after_candidates_is_refused(tmp_path: Path) -> None:
    design = _case(tmp_path, ready=True)
    planning = create_candidate_planning_service(tmp_path / "workspace")
    planning.candidates(_context("candidates", "0.1.2", 2))

    with pytest.raises(OAKError) as caught:
        design.propose_hardware(_scan([]), _context("late", "0.1.3", 3))
    assert caught.value.code == "OAK-HARDWARE-STATE"


def test_a_scan_that_knows_nothing_cannot_be_confirmed(tmp_path: Path) -> None:
    design = _case(tmp_path, ready=True)
    empty = copy.deepcopy(_scan(None))
    empty["platform"] = {"operating_system": None, "architecture": None}
    empty["memory"] = {"ram_gib": None, "unified": False}
    empty["storage_gib"] = None
    empty["unknown"] = [{"field": "platform", "reason": "Windows is not a scanned platform"}]
    empty["tools"] = []
    proposed = design.propose_hardware(empty, _context("empty", "0.1.2", 2))

    with pytest.raises(OAKError) as caught:
        design.confirm_hardware(
            proposed.case["extensions"][HARDWARE_PROPOSAL_EXTENSION]["id"],
            _context("accept", "0.1.3", 3),
        )
    assert caught.value.code == "OAK-HARDWARE-EMPTY"
