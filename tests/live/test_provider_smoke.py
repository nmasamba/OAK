# SPDX-License-Identifier: Apache-2.0
"""OAK-S9-005: a hand-run smoke test against whatever providers this machine is set up for.

**These tests spend real money and send a synthetic brief to a real provider.** They are
skipped unless `OAK_LIVE_MODEL_TESTS=1`, they are never collected by `make check` (which
names `tests/unit`, `tests/contract`, `tests/integration` and `tests/e2e`), and they are
never run in CI. They exist so that a person can verify, before a release, that the request
shapes and the status mapping still match what the providers actually do — recorded
fixtures cannot tell you that a provider changed its API.

Run them deliberately, from a machine where `oak models set-key` has already stored the keys
you want to exercise:

```bash
OAK_LIVE_MODEL_TESTS=1 uv run pytest tests/live -v
```

A family with no stored key is skipped, not failed. Record the outcome in the ExecPlan.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from oak.bootstrap import create_model_configuration_service, model_discoverer
from oak.contracts import SchemaRegistry
from oak.domain import OAKError
from oak.domain.model_families import FAMILY_IDS
from oak.ports.interpreter import ProposalLimits

pytestmark = pytest.mark.live

ROOT = Path(__file__).resolve().parents[2]
BRIEF = (
    b"We run a support desk for a public documentation site. Today two people read the "
    b"manuals and write answers by hand. We would like drafted answers that cite the "
    b"manual passage they came from, with a reviewer approving every answer before it is "
    b"sent. Nothing production-sensitive is involved; the manuals are public."
)
SOURCE_REF = {
    "id": "source.live-smoke",
    "version": "0.1.0",
    "digest": "sha256:" + "0" * 64,
    "uri": None,
    "media_type": "application/vnd.oak.source-record+json",
}
SOURCE_RECORD: dict[str, Any] = {
    "id": "source.live-smoke",
    "original_name": "live-smoke.md",
    "format": "markdown",
    "extensions": {"oak.community/artifact_ref": SOURCE_REF},
}


@pytest.fixture(scope="module", autouse=True)
def _require_opt_in() -> None:
    if os.environ.get("OAK_LIVE_MODEL_TESTS") != "1":
        pytest.skip("set OAK_LIVE_MODEL_TESTS=1 to spend real provider credit")


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.from_directory(ROOT / "schemas")


def _configured(family: str) -> bool:
    service = create_model_configuration_service()
    if family == "local":
        return os.environ.get("OAK_MODEL_ENDPOINT_LOCAL") is not None
    return service.credential_status(family).configured


@pytest.mark.parametrize("family", FAMILY_IDS)
def test_the_stored_key_can_list_that_family_s_models(family: str) -> None:
    if not _configured(family):
        pytest.skip(f"no key is stored for {family}")

    snapshot = model_discoverer(family, None)

    assert snapshot["models"], f"{family} listed no usable chat model"
    assert snapshot["source"] in {"live", "pinned"}
    print(f"\n{family}: {len(snapshot['models'])} models, recommended {snapshot['recommended']}")


@pytest.mark.parametrize("family", FAMILY_IDS)
def test_the_recommended_model_returns_a_valid_proposal_for_a_real_brief(
    family: str, registry: SchemaRegistry
) -> None:
    if not _configured(family):
        pytest.skip(f"no key is stored for {family}")
    from oak.adapters.models.hosted_interpreter import HostedModelInterpreter, build_path_hints
    from oak.adapters.models.providers import profile_for, recommended_route
    from oak.bootstrap import _model_transport

    snapshot = model_discoverer(family, None)
    model_id = snapshot["recommended"]
    if model_id is None:
        pytest.skip(f"{family} recommended no model")
    listed = next((model for model in snapshot["models"] if model["id"] == model_id), None)
    service = create_model_configuration_service()
    profile = profile_for(family, local_endpoint=os.environ.get("OAK_MODEL_ENDPOINT_LOCAL"))
    adapter = HostedModelInterpreter(
        profile,
        model_id,
        provider_route=recommended_route(listed, "cheapest") if family == "huggingface" else None,
        credential_provider=lambda: service.credential_for(family),
        transport=_model_transport(profile),
        path_hints=build_path_hints(registry.schema("system-intent.schema.json")),
    )

    proposal = adapter.propose(SOURCE_RECORD, BRIEF, ProposalLimits())

    registry.validate("interpretation-proposal.schema.json", proposal)
    assert proposal["source_ref"] == SOURCE_REF
    claims = proposal["proposed_claims"]
    assert claims, f"{family}/{model_id} proposed nothing for a brief that states plenty"
    assert all(claim["path"].startswith("/spec/") for claim in claims)
    details = proposal["extensions"]["oak.community/model"]
    print(
        f"\n{family}/{model_id} via {details['provider_route']}: {len(claims)} claims, "
        f"{details['dropped_claims']} dropped, usage {details['usage']}"
    )
    for claim in claims:
        print(f"  {claim['path']} = {claim['value']!r} ({claim['confidence']})")


@pytest.mark.parametrize("family", [family for family in FAMILY_IDS if family != "local"])
def test_a_wrong_key_is_refused_with_the_stable_code(family: str) -> None:
    if not _configured(family):
        pytest.skip(f"no key is stored for {family}")
    from oak.adapters.models.providers import error_for_status, models_request, profile_for
    from oak.bootstrap import _model_transport

    profile = profile_for(family)
    transport = _model_transport(profile)
    response = transport.send(models_request(profile, "oak-test-key-definitely-not-valid-00"))

    if response.status == 200:
        pytest.skip(f"{family} does not authenticate its model list")
    error = error_for_status(profile, response)
    assert error.code in {"OAK-MODEL-KEY-REJECTED", "OAK-MODEL-KEY-SCOPE"}, (
        family,
        response.status,
        error.code,
    )


def test_a_host_outside_the_profile_allowlist_is_still_refused_live() -> None:
    from oak.adapters.models.providers import profile_for
    from oak.adapters.models.transport import TransportRequest
    from oak.bootstrap import _model_transport

    transport = _model_transport(profile_for("openai"))
    with pytest.raises(OAKError) as refused:
        transport.send(TransportRequest(method="GET", url="https://example.com/"))
    assert refused.value.code == "OAK-MODEL-EGRESS-DENIED"
