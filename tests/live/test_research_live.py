# SPDX-License-Identifier: Apache-2.0
"""OAK-S14-003: a hand-run research check against the real Hub, router and GitHub.

**This is real egress.** It sends the reference brief's derived terms, anonymously, to
`huggingface.co`, `router.huggingface.co` and `api.github.com`, within the 30-request
budget. No brief text, case id or credential leaves. It is skipped unless
`OAK_LIVE_RESEARCH_TESTS=1`, never collected by `make check`, and never run in CI:

```bash
OAK_LIVE_RESEARCH_TESTS=1 uv run pytest tests/live/test_research_live.py -m live -q
```

Record the hosts, the request count, the counts found, passed and unvetted, and any
refusal code in the ExecPlan. A live run is evidence, not a gate.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from oak.adapters.catalogue import LocalCatalogue, ResearchVocabularyLoader
from oak.adapters.models.huggingface_catalogue import TRUSTED_NAMESPACES
from oak.adapters.models.research_sources import (
    DEADLINE_SECONDS,
    MAXIMUM_REQUESTS,
    MAXIMUM_RESPONSE_BYTES,
    RESEARCH_HOSTS,
    ResearchRefusedError,
    run_research,
)
from oak.adapters.models.transport import ModelTransport
from oak.compiler import derive_research_terms, terms_digest
from oak.contracts import SchemaRegistry, load_yaml_document

pytestmark = pytest.mark.live

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    os.getenv("OAK_LIVE_RESEARCH_TESTS") != "1", reason="set OAK_LIVE_RESEARCH_TESTS=1"
)
def test_a_live_run_stays_inside_its_budget_and_validates() -> None:
    from datetime import UTC, datetime

    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    vocabulary = ResearchVocabularyLoader(ROOT / "catalogue").load()
    patterns = LocalCatalogue(ROOT / "catalogue", registry).load().patterns
    intent = load_yaml_document((ROOT / "examples/example-intent.yaml").read_text())
    terms = derive_research_terms(intent, vocabulary, patterns)
    transport = ModelTransport(
        allowed_hosts=RESEARCH_HOSTS,
        deadline_seconds=55.0,
        maximum_response_bytes=MAXIMUM_RESPONSE_BYTES,
    )
    occurred_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        run = run_research(
            transport.send,
            terms=terms,
            terms_digest=terms_digest(terms, source_mode="live", hosts=RESEARCH_HOSTS),
            vocabulary=vocabulary,
            trusted_namespaces=TRUSTED_NAMESPACES,
            intent_ref={
                "id": "intent.public-manual-qa",
                "version": "0.1.0",
                "digest": "sha256:" + "0" * 64,
            },
            case_id="design-case.live-research",
            snapshot_id="research.live-research",
            snapshot_version="0.1.0",
            occurred_at=occurred_at,
            source_mode="live",
        )
    except ResearchRefusedError as refused:
        pytest.fail(f"refused: {refused.code} (record this in the plan)")
    snapshot = run.snapshot
    registry.validate("research-snapshot.schema.json", snapshot)
    for artifact in run.manifests:
        import json

        registry.validate("component-manifest.schema.json", json.loads(artifact.content))
    hosts = {record["host"] for record in snapshot["requests"]}
    assert hosts <= RESEARCH_HOSTS
    assert snapshot["budget"]["requests_used"] <= MAXIMUM_REQUESTS
    assert snapshot["budget"]["elapsed_seconds"] <= DEADLINE_SECONDS
    print(
        "LIVE RESEARCH:",
        {
            "hosts": sorted(hosts),
            "requests": snapshot["budget"]["requests_used"],
            "elapsed_seconds": snapshot["budget"]["elapsed_seconds"],
            "summary": snapshot["summary"],
            "refusals": sorted(
                {r["refusal_code"] for r in snapshot["requests"] if r["refusal_code"]}
            ),
            "items": [
                (i["kind"], i["source_id"], i["tier"], i["verdict"]) for i in snapshot["items"]
            ],
            "pairings": snapshot["pairings"],
        },
    )
