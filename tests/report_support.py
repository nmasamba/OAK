# SPDX-License-Identifier: Apache-2.0
"""The reference case at the steps a report can be recorded from, and its composed report.

The reference journey (`examples/briefs/public-manual-qa.yaml`, selecting `candidate-03`)
is driven with the fixed clock and idempotency keys of `tests/runner_support.py`, so the
case at `bundle_compiled` is byte-for-byte the one the reference digests pin. Stopping
earlier gives the same case at `candidate_selected` or `assurance_planned`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from oak.adapters.catalogue import LocalCatalogue, ResearchVocabularyLoader
from oak.adapters.intake import LocalBriefIntake
from oak.adapters.persistence import FileWorkspaceRepository
from oak.adapters.targets import LocalTargetProfile
from oak.application import CandidatePlanningService, DesignCaseService, ResearchService
from oak.application.report import report_document
from oak.application.report.records import gather_records
from oak.bootstrap import create_candidate_planning_service, create_design_case_service
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry, load_yaml_document
from tests.runner_support import ROOT, _context, _stamp, build_compiled_case

GOLDEN_REPORT = ROOT / "tests" / "fixtures" / "report" / "public-manual-qa.report.json"
# The acceptance case of ADR-0018: the same brief, researched on the fixture source with the
# unvetted harness accepted, so the report holds six options and appendix G.
GOLDEN_RESEARCH_REPORT = (
    ROOT / "tests" / "fixtures" / "report" / "public-manual-qa-research.report.json"
)
STOPS = ("candidate_selected", "assurance_planned", "bundle_compiled")
RESEARCH_STOPS = ("candidate_selected", "assurance_planned")
RESEARCH_FIXTURES = ROOT / "tests" / "fixtures" / "research" / "e2e"
RESEARCH_HARNESS = "research.item.github.fixture-forge.fixturelm-serve"
# A fixed renderer identity, so a composer golden does not move when a library upgrades.
# It names only the library the renderer uses (Sprint 13 refused python-pptx).
FIXED_RENDERER: dict[str, Any] = {
    "name": "oak-report-renderer",
    "version": "1.0.0",
    "libraries": {"reportlab": "fixed-for-tests"},
}
FIXED_CLOCK = _stamp(0)


def build_reference_case(tmp_path: Path, stop: str = "bundle_compiled") -> Path:
    """The reference workspace driven to ``stop``; returns the workspace directory."""

    if stop not in STOPS:
        raise ValueError(f"a report starts at candidate_selected, not {stop}")
    if stop == "bundle_compiled":
        return build_compiled_case(tmp_path).workspace
    stamp = FIXED_CLOCK
    workspace = tmp_path / "workspace"
    design = create_design_case_service(workspace)
    design.initialize(workspace_id="workspace.fixture", tenant_id="local", created_at=stamp)
    design.design(
        ROOT / "examples/briefs/public-manual-qa.yaml",
        _context(stamp, "harness-design-000001", None),
    )
    answers = load_yaml_document(
        (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    )
    design.confirm(answers, _context(stamp, "harness-confirm-000001", "0.1.1"))
    planning = create_candidate_planning_service(workspace)
    planning.candidates(_context(stamp, "harness-candidates-000001", "0.1.2"))
    planning.evaluate("candidate-03", _context(stamp, "harness-evaluate-000001", "0.1.3"))
    planning.select("candidate-03", "balanced", _context(stamp, "harness-select-000001", "0.1.4"))
    if stop == "assurance_planned":
        planning.assure("candidate-03", _context(stamp, "harness-assure-000001", "0.1.5"))
    return workspace


def build_researched_case(tmp_path: Path, stop: str = "candidate_selected") -> Path:
    """The acceptance case: researched on the fixture source, the harness accepted, driven
    to ``stop``; returns the workspace directory.

    Every stamp is the fixed clock, the fixture source answers with offset dates and
    measures no time, so two workspaces give the same bytes (the research golden).
    """

    # Imported here, not at module level: a deterministic report or generation in a fresh
    # interpreter imports this module too, and must load no research reader.
    from oak.adapters.models.research_fixture import FixtureResearchSource
    from oak.adapters.models.research_sources import run_research

    if stop not in RESEARCH_STOPS:
        raise ValueError(f"the researched case stops at {RESEARCH_STOPS}, not {stop}")
    stamp = FIXED_CLOCK
    workspace = tmp_path / "workspace"
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    repository = FileWorkspaceRepository(workspace, registry)
    catalogue = LocalCatalogue(ROOT / "catalogue", registry)
    vocabulary = ResearchVocabularyLoader(ROOT / "catalogue")
    design = DesignCaseService(
        repository, LocalBriefIntake(), DeterministicBriefInterpreter(), registry
    )
    design.initialize(workspace_id="workspace.fixture", tenant_id="local", created_at=stamp)
    design.design(
        ROOT / "examples/briefs/public-manual-qa.yaml",
        _context(stamp, "harness-design-000001", None),
    )
    answers = load_yaml_document(
        (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    )
    design.confirm(answers, _context(stamp, "harness-confirm-000001", "0.1.1"))

    def factory(occurred_at: str) -> tuple[Any, str, frozenset[str]]:
        source = FixtureResearchSource(RESEARCH_FIXTURES, occurred_at=occurred_at)
        return source.fetch, "fixture", frozenset()

    research = ResearchService(
        repository,
        registry,
        catalogue,
        vocabulary,
        source_factory=factory,
        source_mode=lambda: ("fixture", frozenset()),
        runner=run_research,
    )
    plan = research.plan()
    research.run(
        _context(stamp, "harness-research-000001", "0.1.2"),
        consent={"hosts": list(plan.hosts), "terms_digest": plan.terms_digest},
    )
    research.review(
        _context(stamp, "harness-review-000001", "0.1.3"),
        item_id=RESEARCH_HARNESS,
        decision="accept",
        rationale="Reviewed the release notes and the licence by hand; accepted for comparison.",
    )
    planning = CandidatePlanningService(
        repository,
        catalogue,
        LocalTargetProfile(registry),
        registry,
        research_vocabulary=vocabulary,
    )
    planning.candidates(_context(stamp, "harness-candidates-000001", "0.1.4"))
    planning.evaluate("candidate-03", _context(stamp, "harness-evaluate-000001", "0.1.5"))
    planning.select("candidate-03", "balanced", _context(stamp, "harness-select-000001", "0.1.6"))
    if stop == "assurance_planned":
        planning.assure("candidate-03", _context(stamp, "harness-assure-000001", "0.1.7"))
    return workspace


def build_case_with_candidates(tmp_path: Path) -> Path:
    """The reference case at `candidates_ready`: one step too early for a report."""

    stamp = FIXED_CLOCK
    workspace = tmp_path / "workspace"
    design = create_design_case_service(workspace)
    design.initialize(workspace_id="workspace.fixture", tenant_id="local", created_at=stamp)
    design.design(
        ROOT / "examples/briefs/public-manual-qa.yaml",
        _context(stamp, "harness-design-000001", None),
    )
    answers = load_yaml_document(
        (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    )
    design.confirm(answers, _context(stamp, "harness-confirm-000001", "0.1.1"))
    planning = create_candidate_planning_service(workspace)
    planning.candidates(_context(stamp, "harness-candidates-000001", "0.1.2"))
    return workspace


def compose_reference(workspace: Path, **overrides: Any) -> dict[str, Any]:
    """The report the composer makes from the workspace's current case."""

    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    records = gather_records(FileWorkspaceRepository(workspace, registry))
    version = str(records.case["version"])
    arguments: dict[str, Any] = {
        "report_id": f"report.public-manual-qa.from-{version}",
        "generated_at": FIXED_CLOCK,
        "generated_by": "local-user",
        "oak_version": "0.9.0",
        "renderer": FIXED_RENDERER,
    }
    arguments.update(overrides)
    return report_document(records, **arguments)
