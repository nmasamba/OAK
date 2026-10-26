# SPDX-License-Identifier: Apache-2.0
"""OAK-S12-005: the chosen architecture as one downloadable document over REST (K1).

The route reads only. It composes the document at request time from the artifacts the
case already holds, so it has no stable digest of its own, needs no idempotency key and no
`If-Match`, and leaves the artifact index exactly as it found it.
"""

import json
from pathlib import Path

import httpx
import pytest
import yaml

from oak.adapters.catalogue import LocalCatalogue
from oak.adapters.intake import LocalBriefIntake
from oak.adapters.persistence import FileWorkspaceRepository
from oak.adapters.targets import LocalTargetProfile
from oak.application import (
    CandidatePlanningService,
    CommandContext,
    CommunityControlPlane,
    DesignCaseService,
    OperationService,
)
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry, load_yaml_document
from oak.interfaces.api.app import PROBLEM_MEDIA_TYPE, create_app

ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-10-15T12:00:00Z"
WORKSPACE = "workspace.public-manual-qa"
CASE = "design-case.public-manual-qa"
ROUTE = f"/v1/design-cases/{CASE}/architecture"
pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _context(key: str, version: str | None = None) -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key=key,
        expected_version=version,
        correlation_id=f"correlation-{key}",
        interface_origin="cli",
        occurred_at=NOW,
    )


def _services(tmp_path: Path) -> tuple[DesignCaseService, CandidatePlanningService]:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    repository = FileWorkspaceRepository(tmp_path / WORKSPACE, registry)
    design = DesignCaseService(
        repository, LocalBriefIntake(), DeterministicBriefInterpreter(), registry
    )
    planning = CandidatePlanningService(
        repository,
        LocalCatalogue(ROOT / "catalogue", registry),
        LocalTargetProfile(registry),
        registry,
    )
    return design, planning


def _case_with_candidates(tmp_path: Path) -> CandidatePlanningService:
    design, planning = _services(tmp_path)
    design.initialize(workspace_id=WORKSPACE, tenant_id="local", created_at=NOW)
    design.design(
        ROOT / "examples/briefs/public-manual-qa.yaml", _context("architecture-design-0001")
    )
    answers = load_yaml_document(
        (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    )
    design.confirm(answers, _context("architecture-confirm-0001", "0.1.1"))
    planning.candidates(_context("architecture-generate-0001", "0.1.2"))
    return planning


def _selected_case(tmp_path: Path) -> None:
    planning = _case_with_candidates(tmp_path)
    planning.evaluate("candidate-03", _context("architecture-evaluate-0001", "0.1.3"))
    planning.select(
        "candidate-03",
        "The balanced fixture, read back as one architecture document.",
        _context("architecture-select-0001", "0.1.4"),
    )


def _client(tmp_path: Path) -> httpx.AsyncClient:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    plane = CommunityControlPlane(
        lambda workspace_id, tenant_id: FileWorkspaceRepository(tmp_path / workspace_id, registry),
        lambda tenant_id: OperationService.__new__(OperationService),
        LocalBriefIntake(),
        DeterministicBriefInterpreter(),
        LocalCatalogue(ROOT / "catalogue", registry),
        LocalTargetProfile(registry),
        registry,
    )
    transport = httpx.ASGITransport(app=create_app(control_plane=plane, clock=lambda: NOW))
    return httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1")


async def test_the_selected_architecture_downloads_as_yaml_and_json(tmp_path: Path) -> None:
    _selected_case(tmp_path)
    async with _client(tmp_path) as client:
        before = await client.get(f"/v1/design-cases/{CASE}/artifacts?limit=100")
        assert before.status_code == 200

        as_yaml = await client.get(ROUTE, params={"format": "yaml"})
        assert as_yaml.status_code == 200
        assert as_yaml.headers["content-type"].startswith("application/yaml")
        assert (
            as_yaml.headers["content-disposition"]
            == f'attachment; filename="{CASE}-architecture.yaml"'
        )
        assert as_yaml.headers["x-content-type-options"] == "nosniff"
        assert as_yaml.headers["cache-control"] == "no-store"
        document = yaml.safe_load(as_yaml.text)
        architecture = document["architecture"]
        assert architecture["case"]["id"] == CASE
        assert architecture["selected"] is True
        assert architecture["candidate"]["id"] == "candidate-03"
        assert architecture["decision"] is not None
        assert "installed nothing" in architecture["notice"]

        as_json = await client.get(ROUTE, params={"format": "json"})
        assert as_json.status_code == 200
        assert as_json.headers["content-type"].startswith("application/json")
        assert (
            as_json.headers["content-disposition"]
            == f'attachment; filename="{CASE}-architecture.json"'
        )
        assert json.loads(as_json.text) == document

        # JSON is the default layout, and the document is composed on every read.
        default = await client.get(ROUTE)
        assert default.status_code == 200
        assert default.headers["content-type"].startswith("application/json")
        assert json.loads(default.text) == document

        # Naming another candidate reads that one, unselected and without the decision.
        named = await client.get(ROUTE, params={"candidate_id": "candidate-00"})
        assert named.status_code == 200
        other = json.loads(named.text)["architecture"]
        assert other["candidate"]["id"] == "candidate-00"
        assert other["selected"] is False
        assert other["decision"] is None

        # Reading composed nothing into the case: the artifact index is as it was.
        after = await client.get(f"/v1/design-cases/{CASE}/artifacts?limit=100")
        assert after.json() == before.json()


async def test_unknown_case_candidate_and_format_are_structured_problems(tmp_path: Path) -> None:
    _selected_case(tmp_path)
    async with _client(tmp_path) as client:
        missing = await client.get("/v1/design-cases/design-case.missing/architecture")
        assert missing.status_code == 404
        assert missing.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
        assert missing.json()["code"] == "OAK-CASE-NOT-FOUND"

        unknown = await client.get(ROUTE, params={"candidate_id": "candidate-99"})
        assert unknown.status_code == 404
        assert unknown.json()["code"] == "OAK-CANDIDATE-NOT-FOUND"

        wrong = await client.get(ROUTE, params={"format": "toml"})
        assert wrong.status_code == 422
        assert wrong.json()["code"] == "OAK-REQUEST-INVALID"


async def test_an_unselected_case_needs_a_named_candidate(tmp_path: Path) -> None:
    _case_with_candidates(tmp_path)
    async with _client(tmp_path) as client:
        unselected = await client.get(ROUTE)
        assert unselected.status_code == 422
        assert unselected.json()["code"] == "OAK-ARCHITECTURE-UNSELECTED"

        named = await client.get(ROUTE, params={"candidate_id": "candidate-01"})
        assert named.status_code == 200
        assert json.loads(named.text)["architecture"]["candidate"]["id"] == "candidate-01"
