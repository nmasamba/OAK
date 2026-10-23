# SPDX-License-Identifier: Apache-2.0
"""Research at the point of design: the three source readers, on one budget (ADR-0018).

Sprint 14. One run reads JSON metadata from the Hugging Face Hub, its router and GitHub's
REST API through the one transport (``fetch`` is ``ModelTransport.send`` or the fixture
source), anonymously, within at most ``MAXIMUM_REQUESTS`` requests and one deadline.
Every byte that comes back is hostile: the parsers keep values only by allowlist
(`oak.domain.research_rules`), bound every response, record a digest of every body and
never the body, and turn each item into claims with evidence classes, a verdict under
``community-research-gates-1.0.0`` and, when it may reach comparison, an honest manifest.
Nothing here imports a network module, and nothing here approves anything.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from oak.adapters.models.transport import (
    RedirectRefusedError,
    TransportRequest,
    TransportResponse,
)
from oak.domain import (
    CURATED_RULES_VERSION,
    RESEARCH_GATES_VERSION,
    RESEARCH_HOSTS,
    Artifact,
    OAKError,
    ResearchVocabulary,
    json_artifact,
)
from oak.domain.catalogue_rules import catalogue_timestamp, eligibility_reasons
from oak.domain.research_rules import (
    COMMIT_ID,
    MAXIMUM_PARAMETER_COUNT,
    REASON_FORBIDDEN_WORD,
    REASON_MALFORMED,
    REASON_UNREACHABLE,
    SEGMENT,
    SHA256,
    TAG,
    GateFacts,
    as_timestamp,
    claim_names_family,
    evidence_reference,
    family_token,
    licence_entry_for,
    manifest_slug,
    normalise_identifier,
    normalise_notes,
    normalise_text,
    research_gates,
    research_manifest,
    weight_floor_gib,
)

Fetch = Callable[..., TransportResponse]

HUB_HOST = "huggingface.co"
ROUTER_HOST = "router.huggingface.co"
GITHUB_HOST = "api.github.com"
MAXIMUM_REQUESTS = 30
DEADLINE_SECONDS = 60.0
CACHE_SECONDS = 86_400
# Caps per response kind, sized from measured responses (router about 90 KB, Hub lists
# 140-200 KB, a GitHub release page about 60 KB); the transport's own cap is the largest.
RESPONSE_LIMITS = {
    "hub": 262_144,
    "router": 131_072,
    "search": 262_144,
    # One release, not two: a single set of notes for a large runtime runs past 150 KB,
    # which the first live run met as a refusal; the newest published release is all that
    # is read, and a draft is invisible to an anonymous reader anyway.
    "releases": 524_288,
    "commit": 4_096,
}
MAXIMUM_RESPONSE_BYTES = max(RESPONSE_LIMITS.values())
HUB_LIST_LIMIT = 50
MAXIMUM_MODELS = 8
SEARCH_PER_PAGE = 3
MAXIMUM_HITS_PER_KIND = 3
MANIFEST_MEDIA_TYPE = "application/vnd.oak.component-manifest+json"
GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
COMMIT_HEADERS = {"Accept": "application/vnd.github.sha", "X-GitHub-Api-Version": "2022-11-28"}


class ResearchRefusedError(OAKError):
    """A run-level refusal: redirected, oversized, rate-limited, unreachable or over budget."""


@dataclass(slots=True)
class CachedResponse:
    checked_at: str
    fetched_monotonic: float
    status: int
    digest: str
    document: Any


class ResearchCache:
    """Parsed responses kept in the worker's memory for a day, keyed by the terms digest.

    Never a raw body, never a refusal, never an expired entry: an outage is shown as an
    outage, and a cached fact keeps the time it was fetched as its `checked_at`.
    """

    def __init__(self, *, seconds: float = CACHE_SECONDS) -> None:
        self._seconds = float(seconds)
        self._entries: dict[tuple[str, str], CachedResponse] = {}

    def get(self, terms_digest: str, url: str, now: float) -> CachedResponse | None:
        entry = self._entries.get((terms_digest, url))
        if entry is None:
            return None
        if now - entry.fetched_monotonic > self._seconds:
            del self._entries[(terms_digest, url)]
            return None
        return entry

    def put(self, terms_digest: str, url: str, entry: CachedResponse) -> None:
        self._entries[(terms_digest, url)] = entry


@dataclass(frozen=True, slots=True)
class ResearchRun:
    snapshot: dict[str, Any]
    manifests: tuple[Artifact, ...]


@dataclass(slots=True)
class _Requester:
    fetch: Fetch
    terms_digest: str
    occurred_at: str
    source_mode: str
    cache: ResearchCache | None
    clock: Callable[[], float]
    started: float
    deadline_seconds: float = DEADLINE_SECONDS
    records: list[dict[str, Any]] = field(default_factory=list)
    fresh: int = 0

    def read(
        self,
        kind: str,
        url: str,
        headers: dict[str, str] | None = None,
        *,
        per_item: bool = False,
    ) -> Any:
        """The parsed JSON (or text for a commit) of one bounded request, or a refusal.

        A refusal of a run-level read (the Hub listing, the router, a search) ends the run.
        A per-item read (one repository's releases or tag commit) records its refusal code
        and returns ``None``, so one repository's redirect, oversized page, outage or rate
        limit fails that harness alone and the run goes on; the budget and the deadline are
        checked before anything is sent and stay run-level.
        """

        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        if len(self.records) >= MAXIMUM_REQUESTS:
            raise ResearchRefusedError(
                "OAK-RESEARCH-BUDGET", "the research run reached its request budget"
            )
        now = self.clock()
        cached = self.cache.get(self.terms_digest, url, now) if self.cache is not None else None
        recorded_host = "fixture" if self.source_mode == "fixture" else host
        if cached is not None:
            self.records.append(
                {
                    "sequence": len(self.records) + 1,
                    "host": recorded_host,
                    "path": path,
                    "status": cached.status,
                    "response_digest": cached.digest,
                    "checked_at": cached.checked_at,
                    "refusal_code": None,
                    "cached": True,
                }
            )
            return cached.document
        remaining = self.deadline_seconds - (now - self.started)
        if remaining <= 0.05:
            raise ResearchRefusedError(
                "OAK-RESEARCH-UNREACHABLE", "the research run reached its deadline"
            )
        record = {
            "sequence": len(self.records) + 1,
            "host": recorded_host,
            "path": path,
            "status": None,
            "response_digest": None,
            "checked_at": self.occurred_at,
            "refusal_code": None,
            "cached": False,
        }
        self.records.append(record)
        self.fresh += 1
        request = TransportRequest(method="GET", url=url, headers=dict(headers or {}))
        refusal: tuple[str, str] | None = None
        cause: BaseException | None = None
        response = None
        try:
            response = self.fetch(request, deadline_seconds=min(remaining, 55.0))
        except RedirectRefusedError as error:
            record["status"] = int(error.status)
            refusal = ("OAK-RESEARCH-REDIRECTED", f"the {kind} source answered with a redirect")
            cause = error
        except OAKError as error:
            if error.code == "OAK-MODEL-EGRESS-DENIED":
                raise
            if error.code == "OAK-INTERPRETER-OUTPUT-LIMIT":
                refusal = (
                    "OAK-RESEARCH-OVERSIZED",
                    f"the {kind} source's answer exceeded its size cap",
                )
            else:
                refusal = ("OAK-RESEARCH-UNREACHABLE", f"the {kind} source could not be reached")
            cause = error
        if response is not None:
            record["status"] = int(response.status)
            digest = "sha256:" + hashlib.sha256(response.body).hexdigest()
            record["response_digest"] = digest
            if response.status == 429 or (
                response.status == 403 and response.header("x-ratelimit-remaining") == "0"
            ):
                refusal = (
                    "OAK-RESEARCH-RATE-LIMITED",
                    f"the {kind} source's anonymous rate limit is spent",
                )
            elif len(response.body) > RESPONSE_LIMITS[kind]:
                refusal = (
                    "OAK-RESEARCH-OVERSIZED",
                    f"the {kind} source's answer exceeded its size cap",
                )
        if refusal is not None:
            record["refusal_code"] = refusal[0]
            if per_item:
                return None
            raise ResearchRefusedError(*refusal) from cause
        assert response is not None
        if response.status != 200:
            record["refusal_code"] = "OAK-RESEARCH-UNREACHABLE"
            return None
        document = _parse(response.body, kind)
        if self.cache is not None and document is not None:
            self.cache.put(
                self.terms_digest,
                url,
                CachedResponse(self.occurred_at, now, int(response.status), digest, document),
            )
        return document

    def last_digest(self) -> str:
        return str(self.records[-1]["response_digest"] or "sha256:" + "0" * 64)

    def last_stamp(self) -> dict[str, Any]:
        """When the last answer was fetched and whether it came from the cache.

        A fact built from a cached answer keeps the time that answer was fetched, so a
        day-old listing never reads as checked today (ADR-0018, `RR-050`).
        """

        record = self.records[-1]
        return {"checked_at": str(record["checked_at"]), "cached": bool(record["cached"])}


def _parse(body: bytes, kind: str) -> Any:
    if kind == "commit":
        text = body.decode("ascii", errors="replace").strip()
        return text if COMMIT_ID.match(text) else None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None


# ----- the request plan ---------------------------------------------------------------------


def hub_url(terms: dict[str, Any], pipeline_tag: str) -> str:
    hub = terms["sent"]["hub"]
    query = [
        ("inference_provider", hub["inference_provider"]),
        ("pipeline_tag", pipeline_tag),
        *[("filter", item) for item in hub["filters"]],
        ("sort", hub["sort"]),
        ("direction", "-1"),
        ("limit", str(HUB_LIST_LIMIT)),
        *[
            ("expand[]", item)
            for item in (
                "cardData",
                "gated",
                "pipeline_tag",
                "library_name",
                "tags",
                "sha",
                "createdAt",
                "lastModified",
                "safetensors",
                "inferenceProviderMapping",
            )
        ],
    ]
    return f"https://{HUB_HOST}/api/models?" + urllib.parse.urlencode(query, safe="[]")


def router_url() -> str:
    return f"https://{ROUTER_HOST}/v1/models"


def search_url(topic: str, pushed_since: str) -> str:
    query = f"topic:{topic} pushed:>={pushed_since} archived:false"
    return f"https://{GITHUB_HOST}/search/repositories?" + urllib.parse.urlencode(
        [("q", query), ("sort", "updated"), ("order", "desc"), ("per_page", str(SEARCH_PER_PAGE))]
    )


def releases_url(repository: str) -> str:
    return f"https://{GITHUB_HOST}/repos/{repository}/releases?per_page=1"


def commit_url(repository: str, tag: str) -> str:
    return f"https://{GITHUB_HOST}/repos/{repository}/commits/{urllib.parse.quote(tag, safe='')}"


def plan_hosts(source_mode: str) -> list[str]:
    return [] if source_mode == "fixture" else sorted(RESEARCH_HOSTS)


# ----- the run ------------------------------------------------------------------------------


def run_research(
    fetch: Fetch,
    *,
    terms: dict[str, Any],
    terms_digest: str,
    vocabulary: ResearchVocabulary,
    trusted_namespaces: frozenset[str],
    intent_ref: dict[str, Any],
    case_id: str,
    snapshot_id: str,
    snapshot_version: str,
    occurred_at: str,
    source_mode: str = "live",
    reviews: dict[str, str] | None = None,
    cache: ResearchCache | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> ResearchRun:
    """One research run: the snapshot document and the manifests it names."""

    started = clock()
    requester = _Requester(
        fetch=fetch,
        terms_digest=terms_digest,
        occurred_at=occurred_at,
        source_mode=source_mode,
        cache=cache,
        clock=clock,
        started=started,
    )
    freshness = int(terms["local"]["freshness_window_days"])
    moment = catalogue_timestamp(occurred_at)
    pushed_since = (moment - timedelta(days=freshness)).strftime("%Y-%m-%d")
    reviews = reviews or {}
    harness_list = vocabulary.harness_repositories
    reviewed = frozenset(
        str(entry["repository"]).casefold()
        for entry in harness_list.get("repositories", [])
        if harness_list.get("reviewed_at") is not None
    )
    kinds = vocabulary.capabilities["harness_kinds"]
    licences = vocabulary.licences
    context = _GateContext(
        licences=licences,
        trusted_namespaces=trusted_namespaces,
        reviewed=reviewed,
        reviews=reviews,
        occurred_at=occurred_at,
        freshness=freshness,
        run=_run_number(snapshot_version),
        source_mode=source_mode,
    )

    # 1. The Hub, one list per pipeline tag, then the router for live routes.
    raw_models: list[dict[str, Any]] = []
    for tag in terms["sent"]["hub"]["pipeline_tags"][:3]:
        listing = requester.read("hub", hub_url(terms, tag))
        if listing is None:
            raise ResearchRefusedError(
                "OAK-RESEARCH-UNREACHABLE", "the Hub listing was not readable"
            )
        raw_models.extend(
            _hub_models(listing, requester.last_digest(), terms, requester.last_stamp())
        )
    router = requester.read("router", router_url())
    if router is None:
        raise ResearchRefusedError(
            "OAK-RESEARCH-UNREACHABLE", "the router's model list was not readable"
        )
    routes = _router_routes(router, requester.last_digest(), requester.last_stamp())

    # 2. GitHub: a bounded search per kind and topic, then each hit's releases.
    raw_harnesses: list[dict[str, Any]] = []
    for kind in sorted(kinds):
        hits: dict[str, dict[str, Any]] = {}
        for topic in terms["sent"]["github"]["topics"].get(kind, []):
            found = requester.read("search", search_url(topic, pushed_since), GITHUB_HEADERS)
            if found is None:
                raise ResearchRefusedError(
                    "OAK-RESEARCH-UNREACHABLE", "a GitHub search was not readable"
                )
            for hit in _search_hits(found, requester.last_digest(), kind, requester.last_stamp()):
                hits.setdefault(hit["source_id"], hit)
        ordered = sorted(hits.values(), key=lambda hit: (hit["pushed_at"] or "", hit["source_id"]))
        for hit in list(reversed(ordered))[:MAXIMUM_HITS_PER_KIND]:
            raw_harnesses.append(_with_release(hit, requester))

    # 3. Items, claims, verdicts, manifests and pairings.
    items: list[dict[str, Any]] = []
    manifests: list[Artifact] = []
    models = sorted(raw_models, key=lambda raw: (raw["created_at"] or "", raw["source_id"]))
    models = list(reversed(models))[:MAXIMUM_MODELS]
    model_items = [
        _model_item(raw, routes.get(raw["source_id"].casefold()), terms, context) for raw in models
    ]
    harness_items = [_harness_item(raw, kinds, context) for raw in raw_harnesses]
    model_items, harness_items = _one_manifest_per_id(model_items, harness_items)
    for item, manifest in [*model_items, *harness_items]:
        items.append(item)
        if manifest is not None:
            # A manifest's artifact version is its release version, as the curated loader
            # and the workspace's identity check read it.
            artifact = json_artifact(
                artifact_id=str(manifest["id"]),
                version=str(manifest["release"]["version"]),
                kind="component_manifest",
                media_type=MANIFEST_MEDIA_TYPE,
                document=manifest,
            )
            item["manifest_ref"] = _reference(artifact)
            manifests.append(artifact)
    pairings = _pairings(model_items, harness_items)
    elapsed = max(0.0, clock() - started)
    counts = {"passed": 0, "needs_review": 0, "failed": 0}
    for item in items:
        counts[str(item["verdict"])] += 1
    snapshot = {
        "schema_version": "0.1.0",
        "id": snapshot_id,
        "version": snapshot_version,
        "case_id": case_id,
        "intent_ref": intent_ref,
        "occurred_at": occurred_at,
        "source_mode": source_mode,
        "terms": terms,
        "terms_digest": terms_digest,
        "hosts": plan_hosts(source_mode),
        "budget": {
            "requests_max": MAXIMUM_REQUESTS,
            "requests_used": requester.fresh,
            "deadline_seconds": DEADLINE_SECONDS,
            "elapsed_seconds": round(elapsed, 3),
        },
        "freshness_window_days": freshness,
        "rule_sets": [CURATED_RULES_VERSION, RESEARCH_GATES_VERSION],
        "requests": requester.records,
        "items": items,
        "pairings": pairings,
        "summary": {"found": len(items), **counts},
        "extensions": {},
    }
    return ResearchRun(snapshot=snapshot, manifests=tuple(manifests))


@dataclass(frozen=True, slots=True)
class _GateContext:
    licences: dict[str, Any]
    trusted_namespaces: frozenset[str]
    reviewed: frozenset[str]
    reviews: dict[str, str]
    occurred_at: str
    freshness: int
    run: int = 1
    source_mode: str = "live"


# The reserved host a fixture run names instead of a real address (RFC 2606): nothing a
# fixture produces may point at a destination anyone could register (ADR-0018, `RR-052`).
FIXTURE_HOST = "fixture.invalid"


def _page(context: _GateContext, host: str, source_id: str) -> str:
    return f"https://{FIXTURE_HOST if context.source_mode == 'fixture' else host}/{source_id}"


Built = tuple[dict[str, Any], dict[str, Any] | None]


def _one_manifest_per_id(
    models: list[Built], harnesses: list[Built]
) -> tuple[list[Built], list[Built]]:
    """Two source ids that fold to one manifest id (`forge/llm-serve`, `forge/llm_serve`) are
    the lookalike signal ADR-0018 names: the later item is listed by digest as malformed
    and gets no manifest, so a run never holds two manifests with one id."""

    seen: set[str] = set()
    kept: list[Built] = []
    for item, manifest in [*models, *harnesses]:
        if manifest is not None:
            identity = str(manifest["id"])
            if identity in seen:
                reasons = tuple(sorted({*item["reasons"], REASON_MALFORMED}))
                item["verdict"] = "failed"
                item["reasons"] = list(reasons)
                item["review_items"] = []
                item.pop("notes", None)
                _list_by_digest(item, reasons)
                manifest = None
            else:
                seen.add(identity)
        kept.append((item, manifest))
    return kept[: len(models)], kept[len(models) :]


def _run_number(snapshot_version: str) -> int:
    """The run's ordinal from its snapshot version (`0.2.0` is the second run)."""

    parts = snapshot_version.split(".")
    try:
        return max(1, int(parts[1])) if len(parts) == 3 else 1
    except ValueError:
        return 1


def _reference(artifact: Artifact) -> dict[str, Any]:
    return {
        "id": artifact.reference.id,
        "version": artifact.reference.version,
        "digest": artifact.reference.digest,
        "media_type": artifact.reference.media_type,
    }


# ----- parsing: the Hub -------------------------------------------------------------------


def _hub_models(
    listing: Any, digest: str, terms: dict[str, Any], stamp: dict[str, Any]
) -> list[dict[str, Any]]:
    if not isinstance(listing, list):
        return []
    wanted_tags = set(terms["sent"]["hub"]["pipeline_tags"])
    models: list[dict[str, Any]] = []
    for index, raw in enumerate(listing[:HUB_LIST_LIMIT]):
        if not isinstance(raw, dict):
            continue
        identifier = normalise_identifier(raw.get("id") or raw.get("modelId"))
        card = _mapping(raw.get("cardData"))
        safetensors = _mapping(raw.get("safetensors"))
        pipeline_tag = normalise_text(raw.get("pipeline_tag"), 40)
        models.append(
            {
                "pointer": f"/{index}",
                "response_digest": digest,
                "source_id": identifier or "",
                "malformed": identifier is None,
                "namespace": identifier.split("/", 1)[0] if identifier else None,
                "created_at": as_timestamp(raw.get("createdAt")),
                "revision": normalise_identifier(raw.get("sha"), COMMIT_ID),
                "gated": raw.get("gated") not in (False, None, "false"),
                "pipeline_tag": pipeline_tag,
                "capability_known": pipeline_tag in wanted_tags,
                "library_name": normalise_text(raw.get("library_name"), 40),
                "licence": _hub_licence(card, raw.get("tags")),
                "parameters": safetensors.get("parameters"),
                **stamp,
            }
        )
    return models


def _hub_licence(card: dict[str, Any], tags: Any) -> str | None:
    """The card's licence, cross-checked with the `license:<id>` tag; a list is cumulative."""

    value = card.get("license")
    values: list[str] = []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = [item for item in value if isinstance(item, str)]
    normalised = [normalise_text(item, 40) for item in values]
    if not normalised or any(item is None for item in normalised):
        return None
    if len({item.casefold() for item in normalised if item}) != 1:
        # Several licences are cumulative; a mixed list never reads as its most generous member.
        return "other"
    licence = str(normalised[0])
    if isinstance(tags, list):
        tagged = [
            str(tag)[len("license:") :]
            for tag in tags
            if isinstance(tag, str) and tag.startswith("license:")
        ]
        if tagged and licence.casefold() not in {tag.casefold() for tag in tagged}:
            return "other"
    return licence


def _router_routes(
    document: Any, digest: str, stamp: dict[str, Any]
) -> dict[str, tuple[dict[str, Any], str]]:
    routes: dict[str, tuple[dict[str, Any], str]] = {}
    entries = document.get("data") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        return routes
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            continue
        identifier = normalise_identifier(raw.get("id"))
        providers = raw.get("providers")
        if identifier is None or not isinstance(providers, list):
            continue
        for position, provider in enumerate(providers):
            if not isinstance(provider, dict) or provider.get("status") != "live":
                continue
            name = normalise_text(provider.get("provider"), 40)
            if name is None:
                continue
            pricing = _mapping(provider.get("pricing"))
            route = {
                "provider": name,
                "price_input": _number(pricing.get("input")),
                "price_output": _number(pricing.get("output")),
                "throughput": _number(provider.get("throughput")),
                "first_token_latency_ms": _number(provider.get("first_token_latency_ms")),
                "pointer": f"/data/{index}/providers/{position}",
                **stamp,
            }
            routes.setdefault(identifier.casefold(), (route, digest))
            break
    return routes


def _mapping(value: Any) -> dict[str, Any]:
    return {str(key): item for key, item in value.items()} if isinstance(value, dict) else {}


def _sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0 or value > 1e12:
        return None
    return float(value)


# ----- parsing: GitHub -------------------------------------------------------------------


def _search_hits(
    document: Any, digest: str, kind: str, stamp: dict[str, Any]
) -> list[dict[str, Any]]:
    items = document.get("items") if isinstance(document, dict) else None
    if not isinstance(items, list):
        return []
    hits: list[dict[str, Any]] = []
    for index, raw in enumerate(items[:SEARCH_PER_PAGE]):
        if not isinstance(raw, dict):
            continue
        source_id = normalise_identifier(raw.get("full_name"))
        if source_id is None:
            continue
        licence = _mapping(raw.get("license"))
        hits.append(
            {
                "pointer": f"/items/{index}",
                "search_digest": digest,
                "source_id": source_id,
                "kind": kind,
                "archived": raw.get("archived") is True,
                "disabled": raw.get("disabled") is True,
                "licence": normalise_identifier(licence.get("spdx_id"), SEGMENT),
                "pushed_at": as_timestamp(raw.get("pushed_at")),
                "created_at": as_timestamp(raw.get("created_at")),
                **stamp,
            }
        )
    return hits


def _with_release(hit: dict[str, Any], requester: _Requester) -> dict[str, Any]:
    """The hit's newest published release, with its notes, digest or tag commit id."""

    enriched = {
        **hit,
        "release_tag": None,
        "released_at": None,
        "prerelease": None,
        "notes": None,
        "asset_digest": None,
        "commit_id": None,
        "release_digest": None,
        "unreachable": False,
        "release_checked_at": hit["checked_at"],
        "release_cached": hit["cached"],
    }
    releases = requester.read(
        "releases", releases_url(hit["source_id"]), GITHUB_HEADERS, per_item=True
    )
    stamp = requester.last_stamp()
    enriched["release_checked_at"] = stamp["checked_at"]
    enriched["release_cached"] = stamp["cached"]
    if releases is None:
        enriched["unreachable"] = True
        return enriched
    enriched["release_digest"] = requester.last_digest()
    if not isinstance(releases, list):
        return enriched
    for index, raw in enumerate(releases[:1]):
        if not isinstance(raw, dict) or raw.get("draft") is True:
            continue
        tag = normalise_identifier(raw.get("tag_name"), TAG)
        if tag is None:
            continue
        enriched["release_pointer"] = f"/{index}"
        enriched["release_tag"] = tag
        enriched["released_at"] = as_timestamp(raw.get("published_at"))
        enriched["prerelease"] = raw.get("prerelease") is True
        enriched["notes"] = normalise_notes(raw.get("body"))
        assets = _sequence(raw.get("assets"))
        for position, asset in enumerate(assets):
            if not isinstance(asset, dict) or asset.get("state") not in (None, "uploaded"):
                continue
            digest = asset.get("digest")
            if isinstance(digest, str) and SHA256.match(digest):
                enriched["asset_digest"] = digest
                enriched["asset_pointer"] = f"/{index}/assets/{position}/digest"
                break
        if enriched["asset_digest"] is None:
            commit = requester.read(
                "commit", commit_url(hit["source_id"], tag), COMMIT_HEADERS, per_item=True
            )
            stamp = requester.last_stamp()
            enriched["release_checked_at"] = max(
                enriched["release_checked_at"], stamp["checked_at"]
            )
            enriched["release_cached"] = enriched["release_cached"] or stamp["cached"]
            if isinstance(commit, str):
                enriched["commit_id"] = commit
        break
    return enriched


# ----- items ---------------------------------------------------------------------------------


def _claim(
    field_name: str,
    value: Any,
    evidence_class: str,
    pointer: str,
    checked_at: str,
    unit: str | None = None,
) -> dict[str, Any]:
    return {
        "field": field_name,
        "value": value,
        "unit": unit,
        "evidence_class": evidence_class,
        "checked_at": checked_at,
        "source_pointer": pointer,
    }


def _model_item(
    raw: dict[str, Any],
    route: tuple[dict[str, Any], str] | None,
    terms: dict[str, Any],
    context: _GateContext,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    # Every claim keeps the time its answer was fetched: the Hub's for the listing, the
    # router's for a route; a cached answer keeps its own time (E-2).
    checked_at = str(raw["checked_at"])
    route_checked_at = str(route[0]["checked_at"]) if route is not None else checked_at
    cached = bool(raw["cached"]) or (route is not None and bool(route[0]["cached"]))
    source_id = raw["source_id"]
    item_id = (
        f"research.item.hub.{source_id.replace('/', '.')}"
        if source_id
        else "research.item.hub.malformed"
    )
    claims: list[dict[str, Any]] = []
    pointer = raw["pointer"]
    if raw["created_at"]:
        claims.append(
            _claim(
                "created_at",
                raw["created_at"],
                "published_by_source",
                f"{pointer}/createdAt",
                checked_at,
            )
        )
    if raw["licence"] is not None:
        claims.append(
            _claim(
                "licence",
                raw["licence"],
                "claimed_by_model_card",
                f"{pointer}/cardData/license",
                checked_at,
            )
        )
    claims.append(
        _claim("gated", bool(raw["gated"]), "published_by_source", f"{pointer}/gated", checked_at)
    )
    if raw["revision"]:
        claims.append(
            _claim("revision", raw["revision"], "published_by_source", f"{pointer}/sha", checked_at)
        )
    if raw["pipeline_tag"]:
        claims.append(
            _claim(
                "pipeline_tag",
                raw["pipeline_tag"],
                "published_by_source",
                f"{pointer}/pipeline_tag",
                checked_at,
            )
        )
    if raw["library_name"]:
        claims.append(
            _claim(
                "library_name",
                raw["library_name"],
                "published_by_source",
                f"{pointer}/library_name",
                checked_at,
            )
        )
    floor, estimator = weight_floor_gib(raw["parameters"])
    counts = [
        count
        for count in (raw["parameters"].values() if isinstance(raw["parameters"], dict) else ())
        if isinstance(count, int) and not isinstance(count, bool)
    ]
    if counts and all(0 <= count <= MAXIMUM_PARAMETER_COUNT for count in counts):
        total = sum(counts)
        claims.append(
            _claim(
                "parameters",
                total,
                "published_by_source",
                f"{pointer}/safetensors/parameters",
                checked_at,
                "parameters",
            )
        )
    if floor is not None:
        claims.append(
            _claim(
                "weight_floor",
                floor,
                "published_by_source",
                f"{pointer}/safetensors/parameters",
                checked_at,
                "GiB estimated",
            )
        )
    measurements: list[dict[str, Any]] = []
    if route is not None:
        details, router_digest = route
        claims.append(
            _claim(
                "live_route",
                details["provider"],
                "served_by_live_route",
                f"{details['pointer']}/status",
                route_checked_at,
            )
        )
        if details["price_input"] is not None:
            claims.append(
                _claim(
                    "price_input",
                    details["price_input"],
                    "published_by_source",
                    f"{details['pointer']}/pricing/input",
                    route_checked_at,
                    "USD per million tokens",
                )
            )
        if details["price_output"] is not None:
            claims.append(
                _claim(
                    "price_output",
                    details["price_output"],
                    "published_by_source",
                    f"{details['pointer']}/pricing/output",
                    route_checked_at,
                    "USD per million tokens",
                )
            )
        if details["throughput"] is not None:
            claims.append(
                _claim(
                    "throughput",
                    details["throughput"],
                    "measured_by_source",
                    f"{details['pointer']}/throughput",
                    route_checked_at,
                    "tokens per second",
                )
            )
            measurements.append(
                {
                    "metric": "throughput_tokens_per_second",
                    "value": details["throughput"],
                    "unit": "tokens per second",
                    "workload": "One validation probe by the router; not a benchmark",
                    "hardware": "Not published by the source.",
                    "measured_at": route_checked_at,
                    "evidence_ref": (
                        f"evidence.research.{manifest_slug(source_id)}.measured_by_source"
                    ),
                }
            )
        if details["first_token_latency_ms"] is not None:
            claims.append(
                _claim(
                    "first_token_latency",
                    details["first_token_latency_ms"],
                    "measured_by_source",
                    f"{details['pointer']}/first_token_latency_ms",
                    route_checked_at,
                    "milliseconds to first token",
                )
            )
        del router_digest
    facts = GateFacts(
        kind="model",
        source_id=source_id or None,
        namespace=raw["namespace"],
        licence_id=raw["licence"],
        gated=bool(raw["gated"]),
        archived=None,
        disabled=None,
        dated_at=raw["created_at"],
        has_digest_or_commit=raw["revision"] is not None,
        capability_known=bool(raw["capability_known"]),
        displayed_strings=(
            *(str(claim["value"]) for claim in claims if isinstance(claim["value"], str)),
            *((source_id,) if source_id else ()),
        ),
        malformed=bool(raw["malformed"]),
    )
    tier, verdict, reasons = research_gates(
        facts,
        licences=context.licences,
        trusted_namespaces=context.trusted_namespaces,
        reviewed_harnesses=context.reviewed,
        review=context.reviews.get(item_id),
        occurred_at=context.occurred_at,
        freshness_window_days=context.freshness,
    )
    item = {
        "id": item_id,
        "kind": "model",
        "source": "huggingface_hub",
        "source_id": source_id or REFUSED_SOURCE_ID,
        "tier": tier,
        "created_or_released_at": raw["created_at"],
        "family_token": family_token(source_id) if source_id else None,
        "claims": claims,
        "manifest_ref": None,
        "verdict": verdict,
        "reasons": list(reasons),
        "review_items": [],
        "response_digest": raw["response_digest"],
        "checked_at": max(checked_at, route_checked_at),
        "cached": cached,
    }
    if verdict == "failed":
        _list_by_digest(item, reasons)
        return item, None
    licence = licence_entry_for(raw["licence"], context.licences)
    slug = manifest_slug(source_id)
    classes = sorted({str(claim["evidence_class"]) for claim in claims})
    page = _page(context, "huggingface.co", source_id)
    evidence = [
        evidence_reference(
            f"evidence.research.{slug}.{evidence_class}",
            evidence_class,
            uri=page,
            version=raw["revision"],
            checked_at=(
                route_checked_at
                if evidence_class in {"served_by_live_route", "measured_by_source"}
                else checked_at
            ),
            content_digest=raw["response_digest"],
            source_word="Hugging Face Hub"
            if evidence_class != "served_by_live_route" and evidence_class != "measured_by_source"
            else "Hugging Face router",
        )
        for evidence_class in classes
    ]
    manifest = research_manifest(
        # Each run's manifests carry the run's ordinal: a later run observes the same
        # source again at a later time, and an immutable artifact never changes content.
        manifest_id=f"component.research.hub.{slug}.run-{context.run}",
        name=source_id,
        category="model",
        kind="model",
        owner=str(raw["namespace"]),
        project_url=page,
        repository_url=page,
        release_version=str(raw["revision"])[:12],
        released_at=raw["created_at"],
        artifact_reference=f"{page.removeprefix('https://')}@{raw['revision']}",
        artifact_digest=raw["response_digest"],
        digest_covers="the Hub's listing of this model, not its weights",
        commit_id=raw["revision"],
        licence=licence,
        licence_domain="model",
        capabilities=list(terms["local"]["capabilities"]),
        evidence=evidence,
        measurements=measurements,
        occurred_at=context.occurred_at,
        freshness_window_days=context.freshness,
        research={
            "source": "huggingface_hub",
            "source_id": source_id,
            "kind": "model",
            "tier": tier,
            "created_or_released_at": raw["created_at"],
            "family_token": family_token(source_id),
            "weight_floor_gib": floor,
            "weight_floor_estimator": estimator if floor is not None else None,
            "weight_floor_reason": None if floor is not None else estimator,
            "item_id": item_id,
            "evidence_classes": classes,
        },
    )
    item["review_items"] = list(
        eligibility_reasons(manifest, catalogue_timestamp(context.occurred_at))
    )
    return item, manifest


def _harness_item(
    raw: dict[str, Any], kinds: dict[str, Any], context: _GateContext
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    # The search's fetch time stamps what the search published; the release read's stamps
    # the release facts; a cached answer keeps its own time (E-2).
    checked_at = str(raw["checked_at"])
    release_checked_at = str(raw.get("release_checked_at") or checked_at)
    cached = bool(raw["cached"]) or bool(raw.get("release_cached"))
    source_id = raw["source_id"]
    kind = raw["kind"]
    item_id = f"research.item.github.{source_id.replace('/', '.')}"
    pointer = raw["pointer"]
    claims: list[dict[str, Any]] = []
    if raw["licence"] is not None:
        claims.append(
            _claim(
                "licence",
                raw["licence"],
                "published_by_source",
                f"{pointer}/license/spdx_id",
                checked_at,
            )
        )
    claims.append(
        _claim(
            "archived",
            bool(raw["archived"]),
            "published_by_source",
            f"{pointer}/archived",
            checked_at,
        )
    )
    if raw["pushed_at"]:
        claims.append(
            _claim(
                "pushed_at",
                raw["pushed_at"],
                "published_by_source",
                f"{pointer}/pushed_at",
                checked_at,
            )
        )
    release_pointer = raw.get("release_pointer", "/0")
    if raw["release_tag"]:
        claims.append(
            _claim(
                "release_tag",
                raw["release_tag"],
                "published_release",
                f"{release_pointer}/tag_name",
                release_checked_at,
            )
        )
    if raw["released_at"]:
        claims.append(
            _claim(
                "release_published_at",
                raw["released_at"],
                "published_release",
                f"{release_pointer}/published_at",
                release_checked_at,
            )
        )
    if raw["asset_digest"]:
        claims.append(
            _claim(
                "release_digest",
                raw["asset_digest"],
                "published_release",
                raw.get("asset_pointer", f"{release_pointer}/assets/0/digest"),
                release_checked_at,
            )
        )
    elif raw["commit_id"]:
        claims.append(
            _claim("commit_id", raw["commit_id"], "published_release", "/sha", release_checked_at)
        )
    facts = GateFacts(
        kind=kind,
        source_id=source_id,
        namespace=source_id.split("/", 1)[0],
        licence_id=raw["licence"],
        gated=None,
        archived=bool(raw["archived"]),
        disabled=bool(raw["disabled"]),
        dated_at=raw["released_at"],
        has_digest_or_commit=bool(raw["asset_digest"] or raw["commit_id"]),
        capability_known=kind in kinds,
        displayed_strings=(
            *(str(claim["value"]) for claim in claims if isinstance(claim["value"], str)),
            source_id,
        ),
        unreachable=bool(raw["unreachable"]),
    )
    tier, verdict, reasons = research_gates(
        facts,
        licences=context.licences,
        trusted_namespaces=context.trusted_namespaces,
        reviewed_harnesses=context.reviewed,
        review=context.reviews.get(item_id),
        occurred_at=context.occurred_at,
        freshness_window_days=context.freshness,
    )
    if raw["unreachable"]:
        reasons = tuple(sorted({*reasons, REASON_UNREACHABLE}))
        verdict = "failed"
    item = {
        "id": item_id,
        "kind": kind,
        "source": "github",
        "source_id": source_id,
        "tier": tier,
        "created_or_released_at": raw["released_at"],
        "family_token": None,
        "claims": claims,
        "manifest_ref": None,
        "verdict": verdict,
        "reasons": list(reasons),
        "review_items": [],
        "response_digest": raw["release_digest"] or raw["search_digest"],
        "checked_at": max(checked_at, release_checked_at),
        "cached": cached,
        "notes": raw["notes"],
    }
    if verdict == "failed":
        del item["notes"]
        _list_by_digest(item, reasons)
        return item, None
    licence = licence_entry_for(raw["licence"], context.licences)
    slug = manifest_slug(source_id)
    classes = sorted({str(claim["evidence_class"]) for claim in claims})
    digest = raw["asset_digest"] or raw["release_digest"] or raw["search_digest"]
    page = _page(context, "github.com", source_id)
    evidence = [
        evidence_reference(
            f"evidence.research.{slug}.{evidence_class}",
            evidence_class,
            uri=page,
            version=raw["release_tag"],
            checked_at=release_checked_at if evidence_class == "published_release" else checked_at,
            content_digest=raw["release_digest"] or raw["search_digest"],
            source_word="GitHub",
        )
        for evidence_class in classes
    ]
    manifest = research_manifest(
        manifest_id=f"component.research.github.{slug}.run-{context.run}",
        name=source_id,
        category="software",
        kind=kind,
        owner=source_id.split("/", 1)[0],
        project_url=page,
        repository_url=page,
        release_version=str(raw["release_tag"]),
        released_at=raw["released_at"],
        artifact_reference=f"{page.removeprefix('https://')}@{raw['release_tag']}",
        artifact_digest=digest,
        digest_covers=(
            "the release asset the source published"
            if raw["asset_digest"]
            else "the source's release listing, not the code"
        ),
        commit_id=raw["commit_id"],
        licence=licence,
        licence_domain="software",
        capabilities=["model_serving"] if kinds[kind]["role"] == "serving" else [],
        evidence=evidence,
        measurements=[],
        occurred_at=context.occurred_at,
        freshness_window_days=context.freshness,
        research={
            "source": "github",
            "source_id": source_id,
            "kind": kind,
            "tier": tier,
            "created_or_released_at": raw["released_at"],
            "release_tag": raw["release_tag"],
            "prerelease": raw["prerelease"],
            "item_id": item_id,
            "evidence_classes": classes,
        },
    )
    item["review_items"] = list(
        eligibility_reasons(manifest, catalogue_timestamp(context.occurred_at))
    )
    return item, manifest


REFUSED_SOURCE_ID = "refused/by-digest"


def _list_by_digest(item: dict[str, Any], reasons: tuple[str, ...]) -> None:
    """A refused item that held a forbidden word or a malformed id is listed by digest only.

    Its claims and its id are what the refusal is about, so none of them is kept where a
    reader could see it; the response digest and the stable reason are the record.
    """

    if REASON_FORBIDDEN_WORD in reasons or REASON_MALFORMED in reasons:
        item["id"] = f"research.item.refused.{item['response_digest'][7:23]}"
        item["source_id"] = REFUSED_SOURCE_ID
        item["claims"] = []
        item["family_token"] = None


def _release_stamp(harness: dict[str, Any]) -> str:
    """When the release page a pairing rests on was fetched (the notes come from it)."""

    for claim in harness["claims"]:
        if claim["evidence_class"] == "published_release":
            return str(claim["checked_at"])
    return str(harness["checked_at"])


def _pairings(
    model_items: list[tuple[dict[str, Any], dict[str, Any] | None]],
    harness_items: list[tuple[dict[str, Any], dict[str, Any] | None]],
) -> list[dict[str, Any]]:
    """A pairing exists only when a harness's release notes name a model's family token."""

    pairings: list[dict[str, Any]] = []
    for harness, _manifest in harness_items:
        notes = harness.pop("notes", None)
        if not notes or harness["verdict"] == "failed":
            continue
        for model, _model_manifest in model_items:
            token = model.get("family_token")
            if not token or model["verdict"] == "failed":
                continue
            if not claim_names_family(notes, str(token)):
                continue
            harness["claims"].append(
                _claim(
                    "names_family",
                    token,
                    "claimed_by_release_notes",
                    f"{harness.get('release_pointer', '/0')}/body",
                    _release_stamp(harness),
                )
            )
            classes = {
                str(claim["evidence_class"]) for claim in [*model["claims"], *harness["claims"]]
            }
            classes &= {
                "served_by_live_route",
                "published_release",
                "published_by_source",
                "claimed_by_release_notes",
            }
            pairings.append(
                {
                    "model_item_id": model["id"],
                    "harness_item_id": harness["id"],
                    "family_token": str(token),
                    "claim_classes": sorted(classes),
                }
            )
    for harness, _manifest in harness_items:
        harness.pop("notes", None)
    return pairings


__all__ = [
    "DEADLINE_SECONDS",
    "MAXIMUM_REQUESTS",
    "MAXIMUM_RESPONSE_BYTES",
    "RESEARCH_HOSTS",
    "ResearchCache",
    "ResearchRefusedError",
    "ResearchRun",
    "run_research",
]
