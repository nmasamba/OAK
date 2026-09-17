# SPDX-License-Identifier: Apache-2.0
"""OAK-S9-001: the deterministic journey's canonical bytes are pinned, not remembered.

Every sprint since Sprint 6 has re-verified four reference digests by hand and quoted them
in `CHANGELOG.md`. Sprint 9 adds an optional model path beside the deterministic one, and
the promise is that a workspace with no model configured produces exactly the bytes it
produced before. A promise about bytes needs a test that reads them: this module compiles
the reference case with the fixed clock and fixed idempotency keys from
`tests/runner_support.py` and compares the digests the workspace records against the
values `CHANGELOG.md` states for `0.7.1`, and it pins the canonical bytes of the
deterministic intent for the structured brief and for the prose brief so that a change to
the interpreter's no-proposal path cannot pass unnoticed.

If one of these values changes deliberately, `docs/compatibility.md` rule 4 applies: the
change is digest-shifting, the changelog must say so, and this file is updated in the same
commit with the before and after values.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from oak.adapters.intake import LocalBriefIntake
from oak.compiler import DeterministicBriefInterpreter
from oak.domain import canonical_json_bytes
from tests.runner_support import ROOT, build_compiled_case

pytestmark = pytest.mark.integration

FIXED_CLOCK = "2026-08-18T12:00:00Z"

# Recorded at 0.7.1 (`CHANGELOG.md`, "Versioning"; case `design-case.public-manual-qa@0.1.7`).
REFERENCE_DIGESTS = {
    ("deployment_bundle", "bundle.candidate-03.target.local-fixture"): (
        "sha256:570abb66ee53eb6433588b865fb4a77dc4d5d7133bc1275fbe433a9a37936596"
    ),
    ("runner_plan", "runner-plan.bundle.candidate-03.target.local-fixture"): (
        "sha256:fad309590f1d09da0019f52dce9bd3d31da5b6285f5246d899657a8f161e18c4"
    ),
    ("architecture_candidate", "candidate-03"): (
        "sha256:576b0ca62835a521439e44b280ffdfca79438323d45ae79e70521a27d14118b3"
    ),
    ("review_artifact", "semantic.candidate-03.target.local-fixture"): (
        "sha256:2ef34758128e13038d26b82847589b2b0ec2c5f25ba6ba56982a520a92a34d63"
    ),
}
REFERENCE_INTENT_ARTIFACTS = {
    "0.1.0": "sha256:54ff2c625088bd0686df568aeb71f5f3dfbb83085cd3526781b63659ab822d2c",
    "0.1.1": "sha256:d296166aef0f7df81a2e7b65fc99f8bd33a3582c948f0bc692566e65b0480f9f",
}
REFERENCE_CASE_DIGEST = "sha256:f54f34195899bee3d891ea791fb9825fa67eebae5e8748a0a3eb07b298d73fb7"

# sha256 of `canonical_json_bytes(intent_document)` from
# `DeterministicBriefInterpreter.interpret(brief, created_at=FIXED_CLOCK)` with no proposal.
GOLDEN_INTENT_BYTES = {
    "public-manual-qa.yaml": "9770d3fc6c8eef67aa85ad9e3303ef187f887853ff1af99f67df39504e6a634e",
    "public-manual-qa-prose.md": "19f05e7cdc467a7a62f83402d3a3cd8d33282d896497551d309f95740a62ea35",
}
GOLDEN_QUESTION_IDS = {
    "public-manual-qa.yaml": [
        "question.model-hardware",
        "question.production-use",
        "question.action-autonomy",
        "question.data-classification",
        "question.data-volume",
    ],
    "public-manual-qa-prose.md": [
        "question.accountable-owner",
        "question.model-hardware",
        "question.production-use",
        "question.action-autonomy",
        "question.data-classification",
    ],
}


def test_the_reference_case_reproduces_the_recorded_digests(tmp_path: Path) -> None:
    harness = build_compiled_case(tmp_path)
    manifest = json.loads(
        (harness.workspace / ".oak" / "manifest.json").read_text(encoding="utf-8")
    )

    by_identity = {
        (item["kind"], item["id"], item["version"]): item["digest"]
        for item in manifest["artifact_index"]
    }
    observed = {
        (kind, identifier): by_identity[(kind, identifier, "0.1.0")]
        for (kind, identifier) in REFERENCE_DIGESTS
    }
    assert observed == REFERENCE_DIGESTS
    assert {
        version: by_identity[("system_intent", "intent.public-manual-qa", version)]
        for version in REFERENCE_INTENT_ARTIFACTS
    } == REFERENCE_INTENT_ARTIFACTS
    assert manifest["current_case_ref"]["version"] == "0.1.7"
    assert manifest["current_case_ref"]["digest"] == REFERENCE_CASE_DIGEST


@pytest.mark.parametrize("brief_name", sorted(GOLDEN_INTENT_BYTES))
def test_the_deterministic_intent_bytes_are_unchanged(brief_name: str) -> None:
    brief = LocalBriefIntake().read(ROOT / "examples" / "briefs" / brief_name)
    result = DeterministicBriefInterpreter().interpret(brief, created_at=FIXED_CLOCK)

    digest = hashlib.sha256(canonical_json_bytes(result.intent_document)).hexdigest()
    assert digest == GOLDEN_INTENT_BYTES[brief_name]
    assert [question.id for question in result.questions] == GOLDEN_QUESTION_IDS[brief_name]
    assert all(question.status == "open" for question in result.questions)
