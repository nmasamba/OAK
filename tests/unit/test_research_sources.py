# SPDX-License-Identifier: Apache-2.0
"""OAK-S14-003: the acceptance case on fixtures, and every refusal, with a fixed clock.

ADR-0018, OAK-FR-CAT-001 to 005, OAK-NFR-SEC-003. With the clock at 2026-10-20T12:00:00Z,
a model created on the Hub on 2026-10-19 and a harness released on 2026-10-13 whose notes
name the model's family surface together: found 2, passed 1, need review 1, paired with the
class of every claim the pairing rests on. The fixture source answers the same requests the
live readers build, so the parsers, gates and snapshot are the ones a live run uses.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from oak.adapters.catalogue import LocalCatalogue, ResearchVocabularyLoader
from oak.adapters.models.huggingface_catalogue import TRUSTED_NAMESPACES
from oak.adapters.models.research_fixture import FixtureResearchSource
from oak.adapters.models.research_sources import (
    MAXIMUM_REQUESTS,
    RESEARCH_HOSTS,
    ResearchCache,
    ResearchRefusedError,
    run_research,
)
from oak.adapters.models.transport import RedirectRefusedError, TransportRequest, TransportResponse
from oak.compiler import derive_research_terms, terms_digest
from oak.contracts import SchemaRegistry, load_yaml_document
from oak.domain import OAKError, canonical_json_bytes

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/research/live"
NOW = "2026-10-20T12:00:00Z"
REGISTRY = SchemaRegistry.from_directory(ROOT / "schemas")
INTENT_REF = {"id": "intent.public-manual-qa", "version": "0.1.1", "digest": "sha256:" + "d" * 64}
MODEL = "research.item.hub.HuggingFaceTB.Fixturelm-4B"
HARNESS = "research.item.github.fixture-forge.fixturelm-serve"


def _vocabulary():  # type: ignore[no-untyped-def]
    return ResearchVocabularyLoader(ROOT / "catalogue").load()


def _terms() -> tuple[dict[str, Any], str]:
    intent = load_yaml_document((ROOT / "examples/example-intent.yaml").read_text())
    patterns = LocalCatalogue(ROOT / "catalogue", REGISTRY).load().patterns
    terms = derive_research_terms(intent, _vocabulary(), patterns)
    return terms, terms_digest(terms, source_mode="fixture", hosts=())


class _Clock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _run(  # type: ignore[no-untyped-def]
    fetch: Any,
    *,
    reviews: dict[str, str] | None = None,
    cache: ResearchCache | None = None,
    source_mode: str = "fixture",
    clock: Any = None,
    trusted: frozenset[str] = TRUSTED_NAMESPACES,
    pipeline_tags: list[str] | None = None,
):
    terms, digest = _terms()
    if pipeline_tags is not None:
        terms = copy.deepcopy(terms)
        terms["sent"]["hub"]["pipeline_tags"] = pipeline_tags
        digest = terms_digest(terms, source_mode="fixture", hosts=())
    keywords: dict[str, Any] = {}
    if clock is not None:
        keywords["clock"] = clock
    return run_research(
        fetch,
        terms=terms,
        terms_digest=digest,
        vocabulary=_vocabulary(),
        trusted_namespaces=trusted,
        intent_ref=INTENT_REF,
        case_id="design-case.public-manual-qa",
        snapshot_id="research.public-manual-qa",
        snapshot_version="0.1.0",
        occurred_at=NOW,
        source_mode=source_mode,
        reviews=reviews,
        cache=cache,
        **keywords,
    )


class _Recorded:
    """A fetch over the fixture directory with one or more responses overridden, and a log."""

    def __init__(self, directory: Path = FIXTURES, **overrides: Any) -> None:
        self._source = FixtureResearchSource(directory, occurred_at=NOW)
        self._overrides = overrides
        self.log: list[str] = []

    def __call__(
        self, request: TransportRequest, *, deadline_seconds: float | None = None
    ) -> TransportResponse:
        self.log.append(request.url)
        for key, override in self._overrides.items():
            if key in request.url:
                if isinstance(override, Exception):
                    raise override
                return override
        return self._source.fetch(request, deadline_seconds=deadline_seconds)


def _mutated(mutate: Any, name: str = "hub-models.json", tmp_path: Path | None = None) -> Path:
    assert tmp_path is not None
    directory = tmp_path / "fixtures"
    directory.mkdir()
    for path in FIXTURES.glob("*.json"):
        (directory / path.name).write_text(path.read_text())
    document = json.loads((directory / name).read_text())
    mutate(document)
    (directory / name).write_text(json.dumps(document))
    return directory


# ----- the acceptance case ------------------------------------------------------------------


def test_the_acceptance_case_surfaces_the_model_and_the_harness_together() -> None:
    fetch = _Recorded()
    run = _run(fetch)
    snapshot = run.snapshot
    REGISTRY.validate("research-snapshot.schema.json", snapshot)

    assert snapshot["summary"] == {"found": 2, "passed": 1, "needs_review": 1, "failed": 0}
    assert snapshot["source_mode"] == "fixture" and snapshot["hosts"] == []
    assert snapshot["rule_sets"] == [
        "community-open-components-1.0.0",
        "community-research-gates-1.0.0",
    ]
    by_id = {item["id"]: item for item in snapshot["items"]}
    model, harness = by_id[MODEL], by_id[HARNESS]
    assert (model["tier"], model["verdict"], model["reasons"]) == ("trusted", "passed", [])
    assert (harness["tier"], harness["verdict"], harness["reasons"]) == (
        "unvetted",
        "needs_review",
        ["OAK-CAT-RESEARCH-UNVETTED"],
    )
    assert model["created_or_released_at"] == "2026-10-19T09:00:00Z"
    assert harness["created_or_released_at"] == "2026-10-13T08:30:00Z"
    assert model["family_token"] == "Fixturelm"
    assert snapshot["pairings"] == [
        {
            "model_item_id": MODEL,
            "harness_item_id": HARNESS,
            "family_token": "Fixturelm",
            "claim_classes": [
                "claimed_by_release_notes",
                "published_by_source",
                "published_release",
                "served_by_live_route",
            ],
        }
    ]
    assert all(claim["evidence_class"] for item in snapshot["items"] for claim in item["claims"])
    classes = {claim["field"]: claim["evidence_class"] for claim in model["claims"]}
    assert classes["licence"] == "claimed_by_model_card"
    assert classes["created_at"] == "published_by_source"
    assert classes["live_route"] == "served_by_live_route"
    assert classes["price_input"] == "published_by_source"
    assert classes["throughput"] == "measured_by_source"
    assert classes["weight_floor"] == "published_by_source"
    harness_classes = {claim["field"]: claim["evidence_class"] for claim in harness["claims"]}
    assert harness_classes["release_digest"] == "published_release"
    assert harness_classes["names_family"] == "claimed_by_release_notes"
    assert harness_classes["licence"] == "published_by_source"
    # Both have honest manifests; the harness's waits for a review before it is used.
    assert {artifact.id for artifact in run.manifests} == {
        "component.research.hub.huggingfacetb.fixturelm-4b.run-1",
        "component.research.github.fixture-forge.fixturelm-serve.run-1",
    }
    for artifact in run.manifests:
        document = json.loads(artifact.content)
        REGISTRY.validate("component-manifest.schema.json", document)
        assert document["status"] == "quarantined"
    assert model["review_items"] == [
        "OAK-CAT-AVAILABILITY-BLOCKED",
        "OAK-CAT-MODEL-LICENCE-UNREVIEWED",
        "OAK-CAT-STATUS-NOT-ELIGIBLE",
        "OAK-CAT-TRANSITIVE-LICENCE-UNRESOLVED",
    ]
    # The budget: hub, router, nine searches, one release listing; no commit read, since the
    # release carries an asset digest.
    assert snapshot["budget"]["requests_used"] == 12 == len(snapshot["requests"])
    assert all(record["host"] == "fixture" for record in snapshot["requests"])
    assert not any("notes" in item for item in snapshot["items"])


def test_the_same_inputs_give_the_same_snapshot_bytes() -> None:
    first = _run(_Recorded(), clock=lambda: 0.0).snapshot
    second = _run(_Recorded(), clock=lambda: 0.0).snapshot
    assert canonical_json_bytes(first) == canonical_json_bytes(second)


def test_a_recorded_accept_lifts_the_harness_and_a_reject_fails_it() -> None:
    accepted = _run(_Recorded(), reviews={HARNESS: "accept"}).snapshot
    assert accepted["summary"] == {"found": 2, "passed": 2, "needs_review": 0, "failed": 0}
    rejected = _run(_Recorded(), reviews={HARNESS: "reject"}).snapshot
    harness = next(item for item in rejected["items"] if item["id"] == HARNESS)
    assert harness["verdict"] == "failed" and harness["reasons"] == ["OAK-CAT-RESEARCH-REJECTED"]
    assert rejected["pairings"] == []


def test_the_manifest_and_the_snapshot_quote_no_source_text_and_no_real_host() -> None:
    run = _run(_Recorded())
    serialised = canonical_json_bytes(run.snapshot).decode("utf-8")
    for artifact in run.manifests:
        serialised += artifact.content.decode("utf-8")
    assert "batching regression" not in serialised  # release-note text never reaches a record
    assert "Synthetic serving runtime fixture" not in serialised  # nor a repository description
    assert "api.github.com" not in run.snapshot["hosts"]


# ----- the gates through the run ------------------------------------------------------------


def test_a_model_outside_the_trusted_namespaces_needs_a_review(tmp_path: Path) -> None:
    def rename(document: list[dict[str, Any]]) -> None:
        document[0]["id"] = document[0]["modelId"] = "someone-else/Fixturelm-4B"

    snapshot = _run(_Recorded(_mutated(rename, tmp_path=tmp_path))).snapshot
    model = next(item for item in snapshot["items"] if item["kind"] == "model")
    assert (model["tier"], model["verdict"]) == ("unvetted", "needs_review")


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda d: d[0].update(createdAt="2026-03-01T00:00:00.000Z"), "OAK-CAT-RESEARCH-STALE"),
        (lambda d: d[0].update(createdAt="2026-10-21T00:00:00.000Z"), "OAK-CAT-RESEARCH-FUTURE"),
        (lambda d: d[0].update(gated=True), "OAK-CAT-RESEARCH-GATED"),
        (lambda d: d[0].update(gated="auto"), "OAK-CAT-RESEARCH-GATED"),
        (lambda d: d[0].pop("sha"), "OAK-CAT-RESEARCH-UNDIGESTED"),
        (lambda d: d[0].update(pipeline_tag="image-classification"), "OAK-CAT-RESEARCH-CAPABILITY"),
        (lambda d: d[0]["cardData"].update(license="other"), "OAK-CAT-RESEARCH-LICENCE-UNLISTED"),
        (
            lambda d: d[0]["cardData"].update(license=["apache-2.0", "llama3"]),
            "OAK-CAT-RESEARCH-LICENCE-UNLISTED",
        ),
        (lambda d: d[0]["cardData"].update(license="mit"), "OAK-CAT-RESEARCH-LICENCE-UNLISTED"),
        (lambda d: d[0].update(library_name="enterprise-grade"), "OAK-CAT-RESEARCH-FORBIDDEN-WORD"),
    ],
)
def test_a_model_that_fails_a_gate_is_listed_with_its_reason_and_gets_no_manifest(
    tmp_path: Path, mutate: Any, reason: str
) -> None:
    run = _run(_Recorded(_mutated(mutate, tmp_path=tmp_path)))
    model = next(item for item in run.snapshot["items"] if item["kind"] == "model")
    assert model["verdict"] == "failed"
    assert reason in model["reasons"]
    assert model["manifest_ref"] is None
    assert run.snapshot["pairings"] == []
    assert not any(artifact.id.startswith("component.research.hub.") for artifact in run.manifests)


def test_a_mismatched_licence_tag_reads_as_other(tmp_path: Path) -> None:
    """The card says apache-2.0 while the tag says mit: never resolved in the model's favour."""

    def contradict(document: list[dict[str, Any]]) -> None:
        document[0]["tags"] = ["text-generation", "license:mit"]

    snapshot = _run(_Recorded(_mutated(contradict, tmp_path=tmp_path))).snapshot
    model = next(item for item in snapshot["items"] if item["kind"] == "model")
    licence = next(claim for claim in model["claims"] if claim["field"] == "licence")
    assert licence["value"] == "other"
    assert "OAK-CAT-RESEARCH-LICENCE-UNLISTED" in model["reasons"]


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda d: d["items"][0].update(archived=True), "OAK-CAT-RESEARCH-ARCHIVED"),
        (lambda d: d["items"][0].update(disabled=True), "OAK-CAT-RESEARCH-DISABLED"),
        (
            lambda d: d["items"][0]["license"].update(spdx_id="NOASSERTION"),
            "OAK-CAT-RESEARCH-LICENCE-UNLISTED",
        ),
        (lambda d: d["items"][0].update(license=None), "OAK-CAT-RESEARCH-LICENCE-UNLISTED"),
    ],
)
def test_a_harness_that_fails_a_gate_is_listed_with_its_reason(
    tmp_path: Path, mutate: Any, reason: str
) -> None:
    directory = _mutated(mutate, name="github-search--llm-serving.json", tmp_path=tmp_path)
    snapshot = _run(_Recorded(directory)).snapshot
    harness = next(item for item in snapshot["items"] if item["id"] == HARNESS)
    assert harness["verdict"] == "failed" and reason in harness["reasons"]


def test_a_stale_release_fails_and_a_source_only_release_reads_the_tag_commit(
    tmp_path: Path,
) -> None:
    def stale(document: list[dict[str, Any]]) -> None:
        document[0]["published_at"] = "2026-01-01T00:00:00Z"

    stale_dir = _mutated(
        stale, name="github-releases--fixture-forge--fixturelm-serve.json", tmp_path=tmp_path
    )
    harness = next(
        item for item in _run(_Recorded(stale_dir)).snapshot["items"] if item["id"] == HARNESS
    )
    assert "OAK-CAT-RESEARCH-STALE" in harness["reasons"]

    def source_only(document: list[dict[str, Any]]) -> None:
        document[0]["assets"] = []

    directory = tmp_path / "source-only"
    directory.mkdir()
    for path in FIXTURES.glob("*.json"):
        (directory / path.name).write_text(path.read_text())
    releases = directory / "github-releases--fixture-forge--fixturelm-serve.json"
    document = json.loads(releases.read_text())
    source_only(document)
    releases.write_text(json.dumps(document))
    (directory / "github-commit--fixture-forge--fixturelm-serve.json").write_text(
        json.dumps({"sha": "89abcdef0123456789abcdef0123456789abcdef"})
    )
    fetch = _Recorded(directory)
    run = _run(fetch)
    harness = next(item for item in run.snapshot["items"] if item["id"] == HARNESS)
    assert harness["verdict"] == "needs_review"
    commit = next(claim for claim in harness["claims"] if claim["field"] == "commit_id")
    assert commit["value"] == "89abcdef0123456789abcdef0123456789abcdef"
    assert commit["evidence_class"] == "published_release"
    assert any("/commits/v0.9.0" in url for url in fetch.log)
    manifest = next(json.loads(a.content) for a in run.manifests if "fixturelm-serve" in a.id)
    research = manifest["extensions"]["oak.community/research"]
    assert research["commit_id"] == "89abcdef0123456789abcdef0123456789abcdef"
    assert research["digest_covers"] == "the source's release listing, not the code"
    assert not manifest["artifact"]["digest"].endswith(research["commit_id"])


def test_a_release_without_a_digest_or_a_readable_commit_is_undigested(tmp_path: Path) -> None:
    def source_only(document: list[dict[str, Any]]) -> None:
        document[0]["assets"] = []

    directory = _mutated(
        source_only, name="github-releases--fixture-forge--fixturelm-serve.json", tmp_path=tmp_path
    )
    harness = next(
        item for item in _run(_Recorded(directory)).snapshot["items"] if item["id"] == HARNESS
    )
    assert "OAK-CAT-RESEARCH-UNDIGESTED" in harness["reasons"]


# ----- poisoned and lookalike metadata --------------------------------------------------------


@pytest.mark.parametrize(
    "identifier",
    [
        "ＨuggingFaceTB/Fixturelm-4B",  # noqa: RUF001 - a fullwidth lookalike namespace
        "HuggingFaceTB/Fixture​lm-4B",  # zero-width space inside the name
        "HuggingFaceTB/‮B4-mlerutxiF",  # right-to-left override
        "HuggingFaceTB/../../etc/passwd",
        "https://evil.invalid/HuggingFaceTB/Fixturelm-4B",
        "",
    ],
)
def test_a_lookalike_or_hostile_model_id_is_refused_as_malformed(
    tmp_path: Path, identifier: str
) -> None:
    def poison(document: list[dict[str, Any]]) -> None:
        document[0]["id"] = document[0]["modelId"] = identifier

    snapshot = _run(_Recorded(_mutated(poison, tmp_path=tmp_path))).snapshot
    model = next(item for item in snapshot["items"] if item["kind"] == "model")
    assert model["verdict"] == "failed"
    assert "OAK-CAT-RESEARCH-MALFORMED" in model["reasons"]
    # Listed by digest with its reason: no claim and no id a reader could see.
    assert model["source_id"] == "refused/by-digest"
    assert model["id"].startswith("research.item.refused.")
    assert model["claims"] == [] and model["family_token"] is None
    assert identifier not in canonical_json_bytes(snapshot).decode("utf-8") or identifier == ""


def test_a_hostile_hub_listing_yields_no_item_and_no_exception(tmp_path: Path) -> None:
    hostile = json.loads((ROOT / "tests/fixtures/providers/hostile/models.json").read_text())

    def poison(document: list[dict[str, Any]]) -> None:
        document[:] = hostile["data"] + [42, "text", None]

    snapshot = _run(_Recorded(_mutated(poison, tmp_path=tmp_path))).snapshot
    models = [item for item in snapshot["items"] if item["kind"] == "model"]
    assert all(item["verdict"] == "failed" for item in models)
    REGISTRY.validate("research-snapshot.schema.json", snapshot)


def test_release_notes_with_a_hidden_character_never_pair(tmp_path: Path) -> None:
    def hide(document: list[dict[str, Any]]) -> None:
        document[0]["body"] = "Adds Fixture​lm support"

    directory = _mutated(
        hide, name="github-releases--fixture-forge--fixturelm-serve.json", tmp_path=tmp_path
    )
    snapshot = _run(_Recorded(directory)).snapshot
    assert snapshot["pairings"] == []


# ----- refusals, budget, deadline and the cache ---------------------------------------------


def _stale_body() -> TransportResponse:
    return TransportResponse(200, {}, b"x" * 300_000)  # over the Hub's 256 KiB cap


@pytest.mark.parametrize(
    ("override", "code"),
    [
        (
            RedirectRefusedError("OAK-INTERPRETER-UNAVAILABLE", "redirect", status=307),
            "OAK-RESEARCH-REDIRECTED",
        ),
        (OAKError("OAK-INTERPRETER-OUTPUT-LIMIT", "too big"), "OAK-RESEARCH-OVERSIZED"),
        (_stale_body(), "OAK-RESEARCH-OVERSIZED"),
        (TransportResponse(429, {}, b"{}"), "OAK-RESEARCH-RATE-LIMITED"),
        (
            TransportResponse(403, {"x-ratelimit-remaining": "0"}, b"{}"),
            "OAK-RESEARCH-RATE-LIMITED",
        ),
        (
            OAKError("OAK-INTERPRETER-UNAVAILABLE", "down", retriable=True),
            "OAK-RESEARCH-UNREACHABLE",
        ),
    ],
)
def test_a_refused_hub_request_fails_the_run_with_a_stable_non_retriable_code(
    override: Any, code: str
) -> None:
    fetch = _Recorded(**{"huggingface.co/api/models": override})
    with pytest.raises(ResearchRefusedError) as refused:
        _run(fetch)
    assert refused.value.code == code
    assert refused.value.retriable is False
    assert len(fetch.log) == 1  # nothing else was sent, and nothing was retried


def test_a_redirect_carries_its_status_as_a_typed_field() -> None:
    error = RedirectRefusedError("OAK-INTERPRETER-UNAVAILABLE", "redirect", status=301)
    assert isinstance(error, OAKError)
    assert (error.code, error.status, error.retriable) == (
        "OAK-INTERPRETER-UNAVAILABLE",
        301,
        False,
    )


@pytest.mark.parametrize(
    "answer",
    [
        OAKError("OAK-INTERPRETER-UNAVAILABLE", "down", retriable=True),
        TransportResponse(503, {}, b"{}"),
        TransportResponse(200, {}, b"<html>not json</html>"),
    ],
    ids=["unreachable", "error-status", "unreadable"],
)
def test_a_router_outage_refuses_the_run_never_reads_as_no_live_route(answer: Any) -> None:
    fetch = _Recorded(**{"router.huggingface.co": answer})
    with pytest.raises(ResearchRefusedError) as refused:
        _run(fetch)
    # The router is read second and its refusal is a refusal: an outage is shown as an
    # outage, never as models that happen to have no live route.
    assert refused.value.code == "OAK-RESEARCH-UNREACHABLE"


def test_a_failed_release_read_marks_that_harness_unreachable_not_the_run() -> None:
    fetch = _Recorded(**{"/releases": TransportResponse(500, {}, b"{}")})
    snapshot = _run(fetch).snapshot
    harness = next(item for item in snapshot["items"] if item["id"] == HARNESS)
    assert harness["verdict"] == "failed" and "OAK-CAT-RESEARCH-UNREACHABLE" in harness["reasons"]
    record = next(r for r in snapshot["requests"] if r["path"].endswith("/releases?per_page=1"))
    assert (record["status"], record["refusal_code"]) == (500, "OAK-RESEARCH-UNREACHABLE")


def test_the_deadline_stops_the_run_before_the_next_request() -> None:
    ticks = iter([0.0, 0.0, 0.0, 0.0, 61.0, 61.0, 61.0, 61.0, 61.0, 61.0])
    fetch = _Recorded()
    with pytest.raises(ResearchRefusedError) as refused:
        _run(fetch, clock=lambda: next(ticks, 61.0))
    assert refused.value.code == "OAK-RESEARCH-UNREACHABLE"
    assert len(fetch.log) < MAXIMUM_REQUESTS


def test_the_plan_never_exceeds_the_budget_and_the_cap_refuses_the_thirty_first() -> None:
    """Three searches a kind, three hits each, a release and a commit per hit: 29 at most.

    With one pipeline tag the worst case is 2 + 9 + 9 + 9 = 29 requests, inside the budget
    by construction. A third Hub tag would make it 31, and the thirty-first is refused.
    """

    many: dict[str, Any] = {"total_count": 3, "incomplete_results": False, "items": []}
    base = json.loads((FIXTURES / "github-search--llm-serving.json").read_text())["items"][0]
    for index in range(3):
        many["items"].append(
            {
                **base,
                "full_name": f"fixture-forge/serve-{index}",
                "pushed_at": f"2026-10-1{index}T00:00:00Z",
            }
        )
    source_only = json.loads(
        (FIXTURES / "github-releases--fixture-forge--fixturelm-serve.json").read_text()
    )
    source_only[0]["assets"] = []
    overrides = {
        "/search/repositories": TransportResponse(200, {}, json.dumps(many).encode()),
        "/releases": TransportResponse(200, {}, json.dumps(source_only).encode()),
        "/commits/": TransportResponse(200, {}, b"89abcdef0123456789abcdef0123456789abcdef"),
    }
    fetch = _Recorded(**overrides)
    snapshot = _run(fetch).snapshot
    assert len(fetch.log) == 29 == snapshot["budget"]["requests_used"]

    fetch = _Recorded(**overrides)
    with pytest.raises(ResearchRefusedError) as refused:
        _run(fetch, pipeline_tags=["text-generation", "text2text-generation", "image-text-to-text"])
    assert refused.value.code == "OAK-RESEARCH-BUDGET"
    assert len(fetch.log) == MAXIMUM_REQUESTS


def test_the_cache_reuses_a_response_within_a_day_with_its_own_checked_at() -> None:
    cache = ResearchCache(seconds=86_400)
    clock = _Clock(0.0)
    first_fetch = _Recorded()
    first = _run(first_fetch, cache=cache, clock=clock).snapshot
    clock.now = 3_600.0
    second_fetch = _Recorded()
    second = _run(second_fetch, cache=cache, clock=clock).snapshot

    assert second_fetch.log == []  # every request was a cache hit
    assert all(record["cached"] for record in second["requests"])
    assert second["budget"]["requests_used"] == 0
    assert all(record["checked_at"] == NOW for record in second["requests"])
    assert first["summary"] == second["summary"]


def test_an_expired_cache_entry_is_never_used() -> None:
    cache = ResearchCache(seconds=10.0)
    clock = _Clock(0.0)
    _run(_Recorded(), cache=cache, clock=clock)
    clock.now = 100.0
    later = _Recorded()
    _run(later, cache=cache, clock=clock)
    assert len(later.log) == 12


def test_a_refusal_is_never_cached() -> None:
    cache = ResearchCache()
    fetch = _Recorded(**{"router.huggingface.co": TransportResponse(429, {}, b"{}")})
    with pytest.raises(ResearchRefusedError):
        _run(fetch, cache=cache)
    assert cache.get(_terms()[1], "https://router.huggingface.co/v1/models", 0.0) is None


# ----- the fixture source ---------------------------------------------------------------------


def test_the_fixture_source_resolves_offset_dates_against_the_run_and_lists_no_host() -> None:
    source = FixtureResearchSource(
        ROOT / "tests/fixtures/research/e2e", occurred_at="2027-03-10T12:00:00Z"
    )
    assert source.hosts == frozenset()
    listing = json.loads(
        source.fetch(TransportRequest("GET", "https://huggingface.co/api/models?x=1")).body
    )
    assert listing[0]["createdAt"] == "2027-03-09T12:00:00Z"
    releases = json.loads(
        source.fetch(
            TransportRequest(
                "GET",
                "https://api.github.com/repos/fixture-forge/fixturelm-serve/releases?per_page=2",
            )
        ).body
    )
    assert releases[0]["published_at"] == "2027-03-03T12:00:00Z"
    unknown = source.fetch(
        TransportRequest("GET", "https://api.github.com/repos/nobody/nothing/releases")
    )
    assert unknown.status == 404


def test_the_live_hosts_are_exactly_the_three_the_decision_record_names() -> None:
    assert (
        frozenset({"huggingface.co", "router.huggingface.co", "api.github.com"}) == RESEARCH_HOSTS
    )


def test_an_item_with_a_forbidden_word_is_listed_by_digest_with_no_claim(tmp_path: Path) -> None:
    def brand(document: list[dict[str, Any]]) -> None:
        document[0]["library_name"] = "enterprise-grade"

    snapshot = _run(_Recorded(_mutated(brand, tmp_path=tmp_path))).snapshot
    refused = next(item for item in snapshot["items"] if item["verdict"] == "failed")
    assert refused["reasons"] == ["OAK-CAT-RESEARCH-FORBIDDEN-WORD"]
    assert refused["claims"] == []
    assert refused["source_id"] == "refused/by-digest"
    assert refused["response_digest"].startswith("sha256:")
    assert "enterprise" not in canonical_json_bytes(snapshot).decode("utf-8")
    REGISTRY.validate("research-snapshot.schema.json", snapshot)


# ----- the closing review's fixes (OAK-S14-007) ---------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        OAKError("OAK-INTERPRETER-UNAVAILABLE", "timed out", retriable=True),
        RedirectRefusedError("OAK-INTERPRETER-UNAVAILABLE", "moved", status=301),
        TransportResponse(200, {}, b"x" * 600_000),  # over the releases' 512 KiB cap
        TransportResponse(429, {}, b"{}"),
    ],
)
def test_a_refused_release_read_fails_that_harness_alone_and_the_run_goes_on(
    override: Any,
) -> None:
    """E-1: one repository's redirect, oversized page, outage or rate limit never hides the
    rest; its request record carries the refusal and the harness is unreachable."""

    fetch = _Recorded(**{"/releases": override})
    snapshot = _run(fetch).snapshot
    harness = next(item for item in snapshot["items"] if item["id"] == HARNESS)
    assert harness["verdict"] == "failed" and "OAK-CAT-RESEARCH-UNREACHABLE" in harness["reasons"]
    model = next(item for item in snapshot["items"] if item["id"] == MODEL)
    assert model["verdict"] == "passed"
    record = next(r for r in snapshot["requests"] if r["path"].endswith("/releases?per_page=1"))
    assert record["refusal_code"] in {
        "OAK-RESEARCH-UNREACHABLE",
        "OAK-RESEARCH-REDIRECTED",
        "OAK-RESEARCH-OVERSIZED",
        "OAK-RESEARCH-RATE-LIMITED",
    }
    assert len(fetch.log) == 12  # the twelve planned requests, nothing retried
    REGISTRY.validate("research-snapshot.schema.json", snapshot)


def test_a_fact_built_from_a_cached_answer_keeps_the_time_that_answer_was_fetched() -> None:
    """E-2: a day-old listing never reads as checked today, in the items, their claims, the
    manifests' evidence and the router's measurement."""

    cache = ResearchCache(seconds=86_400)
    clock = _Clock(0.0)
    first = _run(_Recorded(), cache=cache, clock=clock)
    clock.now = 3_600.0
    later = "2026-10-21T12:00:00Z"
    second = run_research(
        _Recorded(),
        terms=first.snapshot["terms"],
        terms_digest=first.snapshot["terms_digest"],
        vocabulary=_vocabulary(),
        trusted_namespaces=TRUSTED_NAMESPACES,
        intent_ref=INTENT_REF,
        case_id="design-case.public-manual-qa",
        snapshot_id="research.public-manual-qa",
        snapshot_version="0.2.0",
        occurred_at=later,
        source_mode="fixture",
        cache=cache,
        clock=clock,
    )
    assert second.snapshot["occurred_at"] == later
    by_path = {record["path"]: record for record in second.snapshot["requests"]}
    # The Hub listing, the router and the release page are the same requests: cache hits
    # that keep the first fetch's time. A search names its own date, so it is fetched afresh.
    hub = next(record for path, record in by_path.items() if path.startswith("/api/models"))
    assert hub["cached"] is True and hub["checked_at"] == NOW
    search = next(record for path, record in by_path.items() if path.startswith("/search/"))
    assert search["cached"] is False and search["checked_at"] == later
    model = next(item for item in second.snapshot["items"] if item["id"] == MODEL)
    assert model["cached"] is True and model["checked_at"] == NOW
    assert {claim["checked_at"] for claim in model["claims"]} == {NOW}
    harness = next(item for item in second.snapshot["items"] if item["id"] == HARNESS)
    assert harness["cached"] is True and harness["checked_at"] == later
    stamps = {claim["evidence_class"]: claim["checked_at"] for claim in harness["claims"]}
    # The pairing claim rests on the release notes, so it keeps the release page's time.
    assert stamps == {
        "published_by_source": later,
        "published_release": NOW,
        "claimed_by_release_notes": NOW,
    }
    for artifact in second.manifests:
        manifest = json.loads(artifact.content)
        for evidence in manifest["evidence"]:
            evidence_class = evidence["id"].rsplit(".", 1)[-1]
            # The Hub's facts and the release page were cached; a GitHub search was fresh.
            expected = (
                later
                if "github" in artifact.id and evidence_class == "published_by_source"
                else NOW
            )
            assert evidence["checked_at"] == expected, (artifact.id, evidence["id"])
        assert {m["measured_at"] for m in manifest["measurements"]} <= {NOW}


def test_two_source_ids_that_fold_to_one_manifest_id_give_one_manifest(tmp_path: Path) -> None:
    """U-5: `forge/llm_serve` beside `forge/llm-serve` is the lookalike signal; the later
    item is listed by digest as malformed and the run never holds two manifests with one id."""

    def twin(document: dict[str, Any]) -> None:
        original = document["items"][0]
        copy_ = json.loads(json.dumps(original))
        copy_["full_name"] = original["full_name"].replace("-serve", "_serve")
        copy_["id"] = original["id"] + 1
        document["items"].append(copy_)

    directory = _mutated(twin, "github-search--llm-serving.json", tmp_path)
    fetch = _Recorded(
        directory,
        **{
            "fixturelm_serve/releases": TransportResponse(
                200,
                {},
                (directory / "github-releases--fixture-forge--fixturelm-serve.json").read_bytes(),
            )
        },
    )
    run = _run(fetch)
    ids = [str(artifact.id) for artifact in run.manifests]
    assert len(ids) == len(set(ids))
    refused = [
        item for item in run.snapshot["items"] if "OAK-CAT-RESEARCH-MALFORMED" in item["reasons"]
    ]
    assert len(refused) == 1 and refused[0]["source_id"] == "refused/by-digest"
    assert refused[0]["manifest_ref"] is None and refused[0]["claims"] == []
    REGISTRY.validate("research-snapshot.schema.json", run.snapshot)


def test_a_fixture_run_names_no_real_host_anywhere_it_writes() -> None:
    """U-6: the manifests and their evidence point at the reserved fixture host, never at a
    destination anyone could register."""

    run = _run(_Recorded())
    assert run.snapshot["hosts"] == []
    for artifact in run.manifests:
        text = artifact.content.decode("utf-8")
        assert "huggingface.co" not in text and "github.com" not in text
        manifest = json.loads(text)
        assert manifest["project_url"].startswith("https://fixture.invalid/")
        assert all(e["uri"].startswith("https://fixture.invalid/") for e in manifest["evidence"])


def test_a_live_run_names_the_source_pages() -> None:
    run = _run(_Recorded(), source_mode="live")
    pages = {json.loads(a.content)["project_url"] for a in run.manifests}
    assert pages == {
        "https://huggingface.co/HuggingFaceTB/Fixturelm-4B",
        "https://github.com/fixture-forge/fixturelm-serve",
    }


def test_a_huge_parameter_count_leaves_the_floor_unknown_and_never_crashes(
    tmp_path: Path,
) -> None:
    """U-4: a count beyond the supported range is not a figure OAK adds up."""

    def huge(document: list[dict[str, Any]]) -> None:
        document[0]["safetensors"] = {"parameters": {"BF16": 10**400}, "total": 10**400}

    run = _run(_Recorded(_mutated(huge, tmp_path=tmp_path)))
    REGISTRY.validate("research-snapshot.schema.json", run.snapshot)
    model = next(item for item in run.snapshot["items"] if item["id"] == MODEL)
    fields = {claim["field"] for claim in model["claims"]}
    assert "weight_floor" not in fields and "parameters" not in fields
    manifest = json.loads(next(a for a in run.manifests if "hub" in a.id).content)
    research = manifest["extensions"]["oak.community/research"]
    assert research["weight_floor_gib"] is None
    assert research["weight_floor_reason"] == "A parameter count is outside the supported range."


def test_a_confusable_letter_never_reaches_a_claim(tmp_path: Path) -> None:
    """U-1: a Cyrillic letter in place of a Latin one is outside the displayable class, so
    the forbidden-word check cannot be slipped past and nothing of it is shown."""

    def confusable(document: list[dict[str, Any]]) -> None:
        document[0]["library_name"] = "еnterprise-grade"  # noqa: RUF001 - a Cyrillic ie, deliberately

    run = _run(_Recorded(_mutated(confusable, tmp_path=tmp_path)))
    text = json.dumps(run.snapshot) + "".join(a.content.decode("utf-8") for a in run.manifests)
    assert "nterprise" not in text
