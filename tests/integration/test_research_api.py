# SPDX-License-Identifier: Apache-2.0
"""OAK-S14-004: the research plan read, the consented run and the review over REST.

ADR-0018 and OAK-NFR-SEC-003. `:research` checks the capability token before the body,
then the consent against the recomputed plan, then the idempotency key and `If-Match` as
`:generate-candidates` does, then the status; a stale `If-Match`, a missing consent and an
idempotent retry send no request, which the fixture source's own log proves. From
`candidates_ready` on, research is a conflict. The run is submitted with one attempt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from oak.adapters.models import research_fixture
from oak.application import CommandContext
from oak.interfaces.api.app import PROBLEM_MEDIA_TYPE, create_app
from tests.mcp_support import NOW, build_file_control_plane, drain_operations

ROOT = Path(__file__).resolve().parents[2]
CASE = "design-case.public-manual-qa"
TOKEN = "research-model-token-0123456789"
HARNESS = "research.item.github.fixture-forge.fixturelm-serve"
pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def fetch_log(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every request the fixture source answered, across every instance."""

    seen: list[str] = []
    original = research_fixture.FixtureResearchSource.fetch

    def logged(self: Any, request: Any, *, deadline_seconds: float | None = None) -> Any:
        seen.append(request.url)
        return original(self, request, deadline_seconds=deadline_seconds)

    monkeypatch.setattr(research_fixture.FixtureResearchSource, "fetch", logged)
    return seen


def _context(key: str, version: str | None = None) -> CommandContext:
    return CommandContext(
        actor="local-user",
        tenant_id="local",
        idempotency_key=key,
        expected_version=version,
        correlation_id=f"correlation-{key}",
        interface_origin="api",
        occurred_at=NOW,
    )


def _headers(key: str, version: str, **extra: str) -> dict[str, str]:
    return {"Idempotency-Key": key, "If-Match": f'"{version}"', **extra}


class _Stack:
    def __init__(self, tmp_path: Path) -> None:
        self.plane, self.store = build_file_control_plane(tmp_path)
        self.app = create_app(control_plane=self.plane, clock=lambda: NOW, model_token=TOKEN)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://127.0.0.1"
        )

    def drain(self) -> int:
        return drain_operations(self.plane, self.store)


async def _ready(client: httpx.AsyncClient) -> None:
    brief = (ROOT / "examples/briefs/public-manual-qa.yaml").read_text(encoding="utf-8")
    created = await client.post(
        "/v1/design-cases",
        headers={"Idempotency-Key": "research-api-create-0001"},
        json={"original_name": "public-manual-qa.yaml", "content": brief},
    )
    assert created.status_code == 201, created.text
    interpreted = await client.post(
        f"/v1/design-cases/{CASE}:interpret", headers=_headers("research-api-interp-0001", "0.1.0")
    )
    assert interpreted.status_code == 200, interpreted.text
    from oak.contracts import load_yaml_document

    answers = load_yaml_document(
        (ROOT / "examples/briefs/public-manual-qa-answers.yaml").read_text(encoding="utf-8")
    )
    confirmed = await client.post(
        f"/v1/design-cases/{CASE}:confirm",
        headers=_headers("research-api-confirm-001", "0.1.1"),
        json={"answers": answers},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["case"]["status"] == "ready_for_candidates"


async def test_the_plan_is_a_read_that_needs_no_token(tmp_path: Path, fetch_log: list[str]) -> None:
    stack = _Stack(tmp_path)
    async with stack.client() as client:
        await _ready(client)
        plan = await client.get(f"/v1/design-cases/{CASE}/research-plan")
    assert plan.status_code == 200, plan.text
    body = plan.json()
    assert body["allowed"] is True and body["source_mode"] == "fixture" and body["hosts"] == []
    assert body["terms"]["sent"]["hub"]["pipeline_tags"] == ["text-generation"]
    assert body["terms_digest"].startswith("sha256:")
    assert fetch_log == []


async def test_the_token_is_checked_before_the_body_and_nothing_is_sent_without_it(
    tmp_path: Path, fetch_log: list[str]
) -> None:
    stack = _Stack(tmp_path)
    async with stack.client() as client:
        await _ready(client)
        refused = await client.post(
            f"/v1/design-cases/{CASE}:research",
            headers=_headers("research-api-run-000001", "0.1.2"),
            content=b"this is not even json",
        )
        assert refused.status_code == 403
        assert refused.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
        assert refused.json()["code"] == "OAK-MODEL-TOKEN-REQUIRED"
        wrong = await client.post(
            f"/v1/design-cases/{CASE}:research",
            headers=_headers("research-api-run-000001", "0.1.2", **{"X-OAK-Model-Token": "x" * 20}),
            json={"consent": {"hosts": [], "terms_digest": "sha256:" + "0" * 64}},
        )
        assert wrong.status_code == 403
    assert stack.drain() == 0
    assert fetch_log == []


async def test_consent_then_version_then_status_each_refuse_before_any_request(
    tmp_path: Path, fetch_log: list[str]
) -> None:
    stack = _Stack(tmp_path)
    token = {"X-OAK-Model-Token": TOKEN}
    async with stack.client() as client:
        await _ready(client)
        plan = (await client.get(f"/v1/design-cases/{CASE}/research-plan")).json()
        bad_consent = await client.post(
            f"/v1/design-cases/{CASE}:research",
            headers=_headers("research-api-consent-01", "0.1.2", **token),
            json={"consent": {"hosts": ["api.github.com"], "terms_digest": plan["terms_digest"]}},
        )
        assert bad_consent.status_code == 409
        assert bad_consent.json()["code"] == "OAK-RESEARCH-CONSENT"
        stale = await client.post(
            f"/v1/design-cases/{CASE}:research",
            headers=_headers("research-api-stale-0001", "0.1.1", **token),
            json={"consent": {"hosts": plan["hosts"], "terms_digest": plan["terms_digest"]}},
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "OAK-EXPECTED-VERSION"
        assert stack.drain() == 0
        assert fetch_log == []

        generated = await client.post(
            f"/v1/design-cases/{CASE}:generate-candidates",
            headers=_headers("research-api-generate-01", "0.1.2"),
        )
        assert generated.status_code == 202
        assert stack.drain() == 1
        late = await client.post(
            f"/v1/design-cases/{CASE}:research",
            headers=_headers("research-api-late-00001", "0.1.3", **token),
            json={"consent": {"hosts": plan["hosts"], "terms_digest": plan["terms_digest"]}},
        )
        assert late.status_code == 409
        assert late.json()["code"] == "OAK-RESEARCH-STATE"
        late_plan = (await client.get(f"/v1/design-cases/{CASE}/research-plan")).json()
        assert late_plan["allowed"] is False
    assert fetch_log == []


async def test_a_consented_run_is_one_attempt_an_idempotent_retry_sends_nothing_and_a_review_lands(
    tmp_path: Path, fetch_log: list[str]
) -> None:
    stack = _Stack(tmp_path)
    token = {"X-OAK-Model-Token": TOKEN}
    async with stack.client() as client:
        await _ready(client)
        plan = (await client.get(f"/v1/design-cases/{CASE}/research-plan")).json()
        consent = {"hosts": plan["hosts"], "terms_digest": plan["terms_digest"]}
        submitted = await client.post(
            f"/v1/design-cases/{CASE}:research",
            headers=_headers("research-api-run-000001", "0.1.2", **token),
            json={"consent": consent},
        )
        assert submitted.status_code == 202, submitted.text
        operation = submitted.json()
        assert operation["kind"] == "research_catalogue"
        assert operation["max_attempts"] == 1
        assert stack.drain() == 1
        finished = (await client.get(f"/v1/operations/{operation['operation_id']}")).json()
        assert finished["state"] == "succeeded", finished
        snapshot = finished["result"]["snapshot"]
        assert snapshot["summary"] == {"found": 2, "passed": 1, "needs_review": 1, "failed": 0}
        assert snapshot["source_mode"] == "fixture"
        assert len(fetch_log) == 12

        retried = await client.post(
            f"/v1/design-cases/{CASE}:research",
            headers=_headers("research-api-run-000001", "0.1.2", **token),
            json={"consent": consent},
        )
        assert retried.status_code == 202
        assert retried.json()["duplicate"] is True
        assert stack.drain() == 0
        assert len(fetch_log) == 12

        case = (await client.get(f"/v1/design-cases/{CASE}")).json()["case"]
        assert case["version"] == "0.1.3" and case["status"] == "ready_for_candidates"
        assert (
            case["extensions"]["oak.community/research_snapshot_ref"]["id"]
            == "research.public-manual-qa"
        )

        reviewed = await client.post(
            f"/v1/design-cases/{CASE}:review-research-item",
            headers=_headers("research-api-review-0001", "0.1.3"),
            json={"item_id": HARNESS, "decision": "accept", "rationale": "Read it by hand."},
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.headers["etag"] == '"0.1.4"'
        assert reviewed.json()["review"]["decision"] == "accept"
        wrong_item = await client.post(
            f"/v1/design-cases/{CASE}:review-research-item",
            headers=_headers("research-api-review-0002", "0.1.4"),
            json={"item_id": "research.item.nobody", "decision": "reject", "rationale": "x"},
        )
        assert wrong_item.status_code == 422
        assert wrong_item.json()["code"] == "OAK-RESEARCH-ITEM-UNKNOWN"

        generated = await client.post(
            f"/v1/design-cases/{CASE}:generate-candidates",
            headers=_headers("research-api-generate-01", "0.1.4"),
        )
        assert generated.status_code == 202
        assert stack.drain() == 1
        generation = (await client.get(f"/v1/operations/{generated.json()['operation_id']}")).json()
        assert generation["state"] == "succeeded", generation
        listed = (await client.get(f"/v1/design-cases/{CASE}/candidates")).json()["items"]
        ids = [item["id"] for item in listed]
        assert ids == [
            "candidate-00",
            "candidate-01",
            "candidate-03",
            "candidate-04",
            "candidate-05",
            "candidate-06",
        ]
        new = next(item for item in listed if item["id"] == "candidate-05")
        assert new["extensions"]["oak.community/research"]["harness_item_id"] == HARNESS
        assert new["status"] == "infeasible"
        selected = await client.post(
            f"/v1/design-cases/{CASE}:select-candidate",
            headers=_headers("research-api-select-0001", "0.1.5"),
            json={"candidate_id": "candidate-05", "rationale": "Trying the researched design."},
        )
        assert selected.status_code == 422
        assert selected.json()["code"] == "OAK-SELECT-INFEASIBLE"
    assert len(fetch_log) == 12
