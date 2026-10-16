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

from oak.adapters.persistence import FileWorkspaceRepository
from oak.application.report import report_document
from oak.application.report.records import gather_records
from oak.bootstrap import create_candidate_planning_service, create_design_case_service
from oak.contracts import SchemaRegistry, load_yaml_document
from tests.runner_support import ROOT, _context, _stamp, build_compiled_case

GOLDEN_REPORT = ROOT / "tests" / "fixtures" / "report" / "public-manual-qa.report.json"
STOPS = ("candidate_selected", "assurance_planned", "bundle_compiled")
# A fixed renderer identity, so a composer golden does not move when a library upgrades.
FIXED_RENDERER: dict[str, Any] = {
    "name": "oak-report-renderer",
    "version": "1.0.0",
    "libraries": {"python-pptx": "fixed-for-tests", "reportlab": "fixed-for-tests"},
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
