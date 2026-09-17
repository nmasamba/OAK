# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for the optional model path.

``BindingFakeModelInterpreter`` behaves like a configured provider adapter without a
network: it binds its proposal to whatever source record it is handed (the service passes
the record augmented with its own artifact reference under
``extensions["oak.community/artifact_ref"]``) and returns one fixed set of claims, so the
file, REST and MCP legs of the conformance suite see identical model output.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from oak.domain import OAKError
from oak.ports.interpreter import ModelInterpreterPort, ProposalLimits

SOURCE_ARTIFACT_REF_EXTENSION = "oak.community/artifact_ref"
MODEL_EXTENSION = "oak.community/model"

# Four admissible claims across four sections plus one claim on a path every brief states
# explicitly (``/spec/purpose/problem``), which the merge must refuse and record.
FIXED_CLAIMS: tuple[dict[str, Any], ...] = (
    {
        "path": "/spec/decision/autonomy",
        "value": "recommend_only",
        "confidence": 0.62,
        "rationale": "The brief describes drafted answers that a human reviewer approves.",
    },
    {
        "path": "/spec/data/classifications",
        "value": ["internal"],
        "confidence": 0.55,
        "rationale": "Public manuals with internal review notes.",
    },
    {
        "path": "/spec/stakeholders/accountable_owner",
        "value": "Head of Support Operations",
        "confidence": 0.4,
        "rationale": "Named as the sponsor of the pilot.",
    },
    {
        "path": "/spec/operational_contract/latency_p95_ms",
        "value": 2000,
        "confidence": 0.7,
        "rationale": "Interactive review use implies a two-second answer budget.",
    },
    {
        "path": "/spec/purpose/problem",
        "value": "A model must never overwrite what the brief says.",
        "confidence": 0.9,
        "rationale": "Explicit brief values win; this claim is expected to be refused.",
    },
)
FIXED_UNANSWERED: tuple[str, ...] = ("/spec/hardware", "/spec/regulatory_nexus/eu_nexus")
FIXED_MODEL_EXTENSION: dict[str, Any] = {
    "family": "huggingface",
    "model_id": "openai/gpt-oss-120b",
    "provider_route": "fake",
}


class BindingFakeModelInterpreter:
    """A deterministic adapter that binds its proposal to the offered source record."""

    def __init__(
        self,
        claims: tuple[dict[str, Any], ...] = FIXED_CLAIMS,
        *,
        unanswered: tuple[str, ...] = FIXED_UNANSWERED,
        extensions: dict[str, Any] | None = None,
        unavailable: bool = False,
    ) -> None:
        self._claims = claims
        self._unanswered = unanswered
        self._extensions = (
            {MODEL_EXTENSION: dict(FIXED_MODEL_EXTENSION)} if extensions is None else extensions
        )
        self._unavailable = unavailable
        self.calls: list[dict[str, Any]] = []

    def propose(
        self,
        source_record: dict[str, Any],
        source_content: bytes,
        limits: ProposalLimits,
    ) -> dict[str, Any]:
        self.calls.append({"source_id": source_record["id"], "content_bytes": len(source_content)})
        if len(source_content) > limits.maximum_input_bytes:
            raise OAKError("OAK-INTERPRETER-INPUT-LIMIT", "proposal input exceeds its limit")
        if self._unavailable:
            raise OAKError(
                "OAK-INTERPRETER-UNAVAILABLE",
                "optional interpretation provider is unavailable",
                retriable=True,
            )
        source_ref = source_record.get("extensions", {}).get(SOURCE_ARTIFACT_REF_EXTENSION)
        if not isinstance(source_ref, dict):
            raise OAKError("OAK-INTERPRETER-SOURCE", "source record carries no artifact ref")
        return {
            "schema_version": "0.4.0",
            "id": f"proposal.{str(source_record['id']).removeprefix('source.')}.fixed",
            "version": "0.1.0",
            "source_ref": copy.deepcopy(source_ref),
            "proposed_claims": [copy.deepcopy(claim) for claim in self._claims],
            "unanswered_paths": list(self._unanswered),
            "extensions": copy.deepcopy(self._extensions),
        }


def model_factory(
    adapter: ModelInterpreterPort | None,
) -> Callable[[], ModelInterpreterPort | None]:
    """A factory in the shape ``DesignCaseService`` accepts."""

    return lambda: adapter
