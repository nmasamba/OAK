# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-034 (RR-041): a case may record at most a configured number of billable model
requests a day, counted from its own history, before anything is sent to a provider."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from oak.adapters.intake import LocalBriefIntake
from oak.adapters.models.fake_narrator import FakeReportNarrator
from oak.adapters.persistence import FileWorkspaceRepository
from oak.adapters.report import PdfReportRenderer
from oak.application import (
    DEFAULT_MODEL_REQUESTS_PER_CASE_PER_DAY,
    CommandContext,
    DesignCaseService,
    ReportService,
    billable_requests_on,
    check_model_budget,
)
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry
from oak.domain import OAKError
from tests.model_support import BindingFakeModelInterpreter, model_factory
from tests.report_support import build_reference_case

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
REGISTRY = SchemaRegistry.from_directory(ROOT / "schemas")
PROSE = ROOT / "examples/briefs/public-manual-qa-prose.md"
TODAY = "2026-10-29T13:00:00Z"
TOMORROW = "2026-10-30T00:00:01Z"
GOOD_NOTE = {"section": "7", "text": "The owner chose Balanced over three alternatives."}


def _context(key: str, version: str | None, occurred_at: str = TODAY) -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key=key,
        expected_version=version,
        correlation_id=f"correlation-{key}",
        interface_origin="cli",
        occurred_at=occurred_at,
    )


def _reports(workspace: Path, narrator: Any, maximum: int) -> ReportService:
    return ReportService(
        FileWorkspaceRepository(workspace, REGISTRY),
        REGISTRY,
        PdfReportRenderer(),
        oak_version="0.9.0",
        narrator_factory=lambda mode: narrator,
        model_requests_per_day=maximum,
    )


def test_narrations_count_against_the_case_s_day_and_the_next_one_is_refused(
    tmp_path: Path,
) -> None:
    workspace = build_reference_case(tmp_path, "bundle_compiled")
    repository = FileWorkspaceRepository(workspace, REGISTRY)
    service = _reports(workspace, FakeReportNarrator([GOOD_NOTE]), maximum=2)
    assert billable_requests_on(repository, TODAY[:10]) == 0
    service.record(_context("budget-record-000001", "0.1.7"), narrative="online")
    service.record(_context("budget-record-000002", "0.1.8"), narrative="online")
    assert billable_requests_on(repository, TODAY[:10]) == 2
    before = repository.manifest()
    with pytest.raises(OAKError) as refusal:
        service.record(_context("budget-record-000003", "0.1.9"), narrative="online")
    assert refusal.value.code == "OAK-MODEL-BUDGET"
    assert refusal.value.retriable is True
    assert "2 billable model request(s)" in refusal.value.message
    assert repository.manifest() == before, "a refused request recorded something"
    # The deterministic mode asks no provider and is not counted.
    deterministic = service.record(_context("budget-record-000004", "0.1.9"))
    assert deterministic.report["narrative_mode"] == "deterministic"
    assert billable_requests_on(repository, TODAY[:10]) == 2
    # The next UTC day starts a new count.
    tomorrow = service.record(
        _context("budget-record-000005", "0.1.10", TOMORROW), narrative="online"
    )
    assert tomorrow.report["narrative_mode"] == "online"
    assert billable_requests_on(repository, TOMORROW[:10]) == 1


def test_the_budget_is_checked_before_the_provider_is_asked(tmp_path: Path) -> None:
    class _Counting:
        calls = 0

        def propose(self, *_arguments: object, **_keywords: object) -> object:
            _Counting.calls += 1
            raise AssertionError("the model must not be asked anything")

    workspace = build_reference_case(tmp_path, "bundle_compiled")
    _reports(workspace, FakeReportNarrator([GOOD_NOTE]), maximum=1).record(
        _context("budget-first-0000001", "0.1.7"), narrative="online"
    )
    with pytest.raises(OAKError) as refusal:
        _reports(workspace, _Counting(), maximum=1).record(
            _context("budget-second-000001", "0.1.8"), narrative="online"
        )
    assert refusal.value.code == "OAK-MODEL-BUDGET"
    assert _Counting.calls == 0


def test_a_request_the_provider_failed_records_nothing_and_is_not_counted(
    tmp_path: Path,
) -> None:
    class _Failing:
        def propose(self, *_arguments: object, **_keywords: object) -> object:
            raise OAKError("OAK-MODEL-PROVIDER", "the provider is down")

    workspace = build_reference_case(tmp_path, "bundle_compiled")
    repository = FileWorkspaceRepository(workspace, REGISTRY)
    with pytest.raises(OAKError) as failed:
        _reports(workspace, _Failing(), maximum=1).record(
            _context("budget-failed-000001", "0.1.7"), narrative="online"
        )
    assert failed.value.code == "OAK-MODEL-PROVIDER"
    assert billable_requests_on(repository, TODAY[:10]) == 0
    recorded = _reports(workspace, FakeReportNarrator([GOOD_NOTE]), maximum=1).record(
        _context("budget-after-0000001", "0.1.7"), narrative="online"
    )
    assert recorded.report["narrative_mode"] == "online"


def test_zero_switches_the_budget_off(tmp_path: Path) -> None:
    workspace = build_reference_case(tmp_path, "bundle_compiled")
    service = _reports(workspace, FakeReportNarrator([GOOD_NOTE]), maximum=0)
    version = 7
    for index in range(3):
        service.record(_context(f"budget-open-{index:07d}", f"0.1.{version}"), narrative="online")
        version += 1
    assert DEFAULT_MODEL_REQUESTS_PER_CASE_PER_DAY >= 100, "generous by default"


def test_a_model_interpretation_counts_and_a_deterministic_one_does_not(tmp_path: Path) -> None:
    def service(workspace: Path, maximum: int) -> DesignCaseService:
        built = DesignCaseService(
            FileWorkspaceRepository(workspace, REGISTRY),
            LocalBriefIntake(),
            DeterministicBriefInterpreter(),
            REGISTRY,
            model_interpreter_factory=model_factory(BindingFakeModelInterpreter()),
            model_requests_per_day=maximum,
        )
        built.initialize(workspace_id="workspace.budget", tenant_id="local", created_at=TODAY)
        return built

    online = tmp_path / "online"
    service(online, maximum=1).design(
        PROSE, _context("budget-design-0000001", None), interpreter="online"
    )
    repository = FileWorkspaceRepository(online, REGISTRY)
    assert billable_requests_on(repository, TODAY[:10]) == 1
    with pytest.raises(OAKError) as refusal:
        check_model_budget(repository, occurred_at=TODAY, maximum=1)
    assert refusal.value.code == "OAK-MODEL-BUDGET"
    check_model_budget(repository, occurred_at=TOMORROW, maximum=1)
    check_model_budget(repository, occurred_at=TODAY, maximum=2)

    deterministic = tmp_path / "deterministic"
    service(deterministic, maximum=1).design(PROSE, _context("budget-design-0000002", None))
    assert billable_requests_on(FileWorkspaceRepository(deterministic, REGISTRY), TODAY[:10]) == 0
