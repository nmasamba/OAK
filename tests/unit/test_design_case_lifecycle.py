# SPDX-License-Identifier: Apache-2.0
"""OAK-S1-002 immutable DesignCase lifecycle tests."""

from itertools import product
from pathlib import Path

import pytest

from oak.contracts import load_yaml_document
from oak.domain import (
    ALLOWED_TRANSITIONS,
    ArtifactReference,
    DesignCase,
    DesignCaseStatus,
    OAKError,
)

ROOT = Path(__file__).resolve().parents[2]


def _case(status: DesignCaseStatus) -> DesignCase:
    return DesignCase(
        id="design-case.lifecycle-test",
        version="0.1.0",
        status=status,
        title="Lifecycle test",
        tenant_id="local",
        created_at="2026-08-17T10:00:00Z",
        updated_at="2026-08-17T10:00:00Z",
        interface_origin="cli",
        brief_refs=(
            ArtifactReference(
                id="brief.lifecycle-test",
                version="0.1.0",
                digest=f"sha256:{'a' * 64}",
                media_type="text/plain",
            ),
        ),
    )


@pytest.mark.parametrize("current,target", list(product(DesignCaseStatus, repeat=2)))
def test_complete_transition_matrix(current: DesignCaseStatus, target: DesignCaseStatus) -> None:
    case = _case(current)
    allowed = target == current or target in ALLOWED_TRANSITIONS[current]

    if allowed:
        successor = case.revise(status=target, updated_at="2026-08-17T10:01:00Z")
        assert successor.status == target
        assert successor.version == "0.1.1"
        assert case.version == "0.1.0"
    else:
        with pytest.raises(OAKError) as captured:
            case.revise(status=target, updated_at="2026-08-17T10:01:00Z")
        assert captured.value.code == "OAK-CASE-TRANSITION-DENIED"


def test_full_schema_artifact_index_round_trips_without_reference_loss() -> None:
    document = load_yaml_document(
        (ROOT / "examples/example-design-case.yaml").read_text(encoding="utf-8")
    )

    assert DesignCase.from_document(document).to_document() == document
