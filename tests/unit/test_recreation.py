# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-025: each replayed answer is read back from the intent and checked by its digest."""

from __future__ import annotations

from typing import Any

import pytest

from oak.application.recreation import _recover, _value_digest
from oak.domain import OAKError

PATHS = {"question.data": "/spec/data/classification"}
BEFORE = {"spec": {"data": {"classification": "internal"}}}
AFTER = {"spec": {"data": {"classification": "public"}}}


def _record(decision: str, value: Any) -> dict[str, Any]:
    return {
        "question_id": "question.data",
        "decision": decision,
        "value_digest": _value_digest(value),
        "rationale": "because",
    }


@pytest.mark.parametrize("decision", ["confirm", "correct", "accept_risk"])
def test_a_kept_or_corrected_value_is_read_from_the_intent_the_answer_produced(
    decision: str,
) -> None:
    recovered = _recover(_record(decision, "public"), PATHS, BEFORE, AFTER)

    assert recovered == {
        "question_id": "question.data",
        "decision": decision,
        "value": "public",
        "rationale": "because",
    }


@pytest.mark.parametrize("sent", [None, "internal"])
def test_a_rejection_is_recovered_with_either_value_a_client_sends(sent: Any) -> None:
    removed = {"spec": {"data": {}}}

    assert _recover(_record("reject", sent), PATHS, BEFORE, removed)["value"] == sent


@pytest.mark.parametrize(
    ("record", "paths"),
    [
        (_record("confirm", "secret"), PATHS),
        (_record("reject", "something else"), PATHS),
        (_record("confirm", "public"), {}),
    ],
)
def test_an_answer_that_cannot_be_recovered_exactly_is_refused(
    record: dict[str, Any], paths: dict[str, str]
) -> None:
    with pytest.raises(OAKError) as refused:
        _recover(record, paths, BEFORE, AFTER)
    assert refused.value.code == "OAK-IMPORT-REPLAY"
