# SPDX-License-Identifier: Apache-2.0
"""`oak architecture`: the chosen design as one document, and what an install still needs.

The document is a stopping point, so what it says about the two install approvals must
match what dispatch would decide: an expired or revoked approval is never "current".
"""

from __future__ import annotations

from typing import Any

import pytest

from oak.application.architecture import (
    architecture_document,
    architecture_human,
    select_candidate_reference,
)
from oak.domain import OAKError
from tests.container_support import parameters

NOW = "2026-09-29T12:00:00Z"


def _case(**overrides: Any) -> dict[str, Any]:
    case = {
        "id": "design-case.public-manual-qa",
        "version": "0.1.9",
        "status": "deployment_approved",
        "title": "Cited answers",
        "selected_candidate_ref": {"id": "candidate-03"},
        "candidate_refs": [{"id": "candidate-01"}, {"id": "candidate-03"}],
    }
    case.update(overrides)
    return case


CANDIDATE = {
    "id": "candidate-03",
    "extensions": {"oak.community/pattern_variant": "balanced"},
    "topology": {
        "nodes": [{"id": "node.retrieval", "role": "Retrieval", "component_ref": "c@1.0.0"}],
        "edges": [],
    },
    "objectives": [
        {"name": "latency_p95", "value": 1200, "lower": 900, "upper": 1500, "unit": "ms"}
    ],
}


def _plan(parameters_document: dict[str, Any]) -> dict[str, Any]:
    return {
        "target": {"id": "target.local-started-fixture"},
        "operations": [{"kind": "apply", "parameters": parameters_document}],
    }


def _approval(expires_at: str = "2026-09-30T12:00:00Z", *, revoked: bool = False) -> dict:
    return {"expires_at": expires_at, "revoked": revoked}


def _states(approvals: dict[str, dict]) -> dict[str, str]:
    document = architecture_document(
        case=_case(),
        candidate=CANDIDATE,
        decision={"owner": "local-user"},
        plan=_plan(parameters()),
        approvals=approvals,
        now=NOW,
    )
    installation = document["architecture"]["installation"]
    return {action: entry["state"] for action, entry in installation["approvals"].items()}


def test_approval_states_are_what_dispatch_would_decide() -> None:
    assert _states({}) == {"architecture": "absent", "apply": "absent"}
    assert _states({"architecture": _approval(), "apply": _approval()}) == {
        "architecture": "current",
        "apply": "current",
    }
    assert _states(
        {"architecture": _approval("2026-09-29T11:59:59Z"), "apply": _approval(revoked=True)}
    ) == {"architecture": "expired", "apply": "revoked"}


def test_a_plan_from_before_the_topology_installer_is_named_not_crashed_on() -> None:
    older = {
        "container_name": "oak-fixture-local-mutation-fixture",
        "image_reference": "postgres:17.6-alpine",
        "image_digest": "sha256:" + "e" * 64,
        "isolation": "network-none-never-started",
    }
    document = architecture_document(
        case=_case(),
        candidate=CANDIDATE,
        decision=None,
        plan=_plan(older),
        approvals={},
        now=NOW,
    )

    installation = document["architecture"]["installation"]
    assert installation["superseded"] is True
    assert "recompile" in architecture_human(document)


def test_a_candidate_other_than_the_selected_one_shows_no_installation_or_decision() -> None:
    document = architecture_document(
        case=_case(selected_candidate_ref={"id": "candidate-01"}),
        candidate=CANDIDATE,
        decision={"owner": "local-user"},
        plan=_plan(parameters()),
        approvals={},
        now=NOW,
    )

    architecture = document["architecture"]
    assert architecture["selected"] is False
    assert architecture["decision"] is None and architecture["installation"] is None


def test_asking_before_any_selection_names_a_candidate_to_ask_about() -> None:
    with pytest.raises(OAKError) as caught:
        select_candidate_reference(_case(selected_candidate_ref=None), None)
    assert caught.value.code == "OAK-ARCHITECTURE-UNSELECTED"
    with pytest.raises(OAKError) as unknown:
        select_candidate_reference(_case(), "candidate-99")
    assert unknown.value.code == "OAK-CANDIDATE-NOT-FOUND"
