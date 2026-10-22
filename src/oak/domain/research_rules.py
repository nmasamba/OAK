# SPDX-License-Identifier: Apache-2.0
"""Research at the point of design: the rules that turn hostile metadata into typed claims.

Sprint 14, ADR-0018. Everything here is pure. Hub, router and GitHub text is
author-controlled, so a value is kept only by allowlist: NFKC-normalised, refused if it
holds a Unicode category C character, refused if normalisation changed an identifier
(full-width lookalikes), bounded below the report's caps, and checked for forbidden words.
A gap is never filled. The research gates, `community-research-gates-1.0.0`, decide what
reaches comparison; nothing here approves anything.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from oak.domain.catalogue_rules import catalogue_timestamp
from oak.domain.research import (
    EVIDENCE_SOURCE_TYPES,
    EVIDENCE_WORDS,
    RESEARCH_EXTENSION,
    RESEARCH_GATES_VERSION,
)
from oak.domain.vocabulary import forbidden_words

COLUMN_LIMIT = 80
LABEL_LIMIT = 120
IDENTIFIER_LIMIT = 160
NOTES_LIMIT = 20_000
TEXT_PUNCTUATION = frozenset(" -_./:+")
SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}/[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
COMMIT_ID = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SPDX_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]{0,63}$")
SIZE_SUFFIX = re.compile(r"-[0-9]+(?:\.[0-9]+)?[BbMm]$")
NOT_PUBLISHED = "Not published by the source."

# Bytes per stored element, by safetensors dtype. A dtype outside this table makes the
# estimate unknown; `safetensors.total` counts stored elements and is never used.
DTYPE_BYTES: dict[str, int] = {
    "U8": 1,
    "I8": 1,
    "BOOL": 1,
    "F8_E4M3": 1,
    "F8_E5M2": 1,
    "F8_E8M0": 1,
    "BF16": 2,
    "F16": 2,
    "I16": 2,
    "U16": 2,
    "F32": 4,
    "I32": 4,
    "U32": 4,
    "F64": 8,
    "I64": 8,
    "U64": 8,
}
WEIGHT_FLOOR_ESTIMATOR = "research-weight-floor-1.0.0"
# The largest parameter count a source may publish and OAK will add up: a thousand
# trillion. A larger one is not a model a person would run and would overflow the floor.
MAXIMUM_PARAMETER_COUNT = 10**15

REASON_LICENCE_UNLISTED = "OAK-CAT-RESEARCH-LICENCE-UNLISTED"
REASON_LICENCE_BLOCKED = "OAK-CAT-RESEARCH-LICENCE-BLOCKED"
REASON_GATED = "OAK-CAT-RESEARCH-GATED"
REASON_ARCHIVED = "OAK-CAT-RESEARCH-ARCHIVED"
REASON_DISABLED = "OAK-CAT-RESEARCH-DISABLED"
REASON_UNDATED = "OAK-CAT-RESEARCH-UNDATED"
REASON_STALE = "OAK-CAT-RESEARCH-STALE"
REASON_FUTURE = "OAK-CAT-RESEARCH-FUTURE"
REASON_UNDIGESTED = "OAK-CAT-RESEARCH-UNDIGESTED"
REASON_CAPABILITY = "OAK-CAT-RESEARCH-CAPABILITY"
REASON_UNVETTED = "OAK-CAT-RESEARCH-UNVETTED"
REASON_REJECTED = "OAK-CAT-RESEARCH-REJECTED"
REASON_FORBIDDEN_WORD = "OAK-CAT-RESEARCH-FORBIDDEN-WORD"
REASON_MALFORMED = "OAK-CAT-RESEARCH-MALFORMED"
REASON_UNREACHABLE = "OAK-CAT-RESEARCH-UNREACHABLE"
BLOCKED_LICENCE_CLASSES = frozenset({"restricted", "source_available", "proprietary", "unknown"})


# ----- normalisation by allowlist ---------------------------------------------------------


def _has_control(value: str) -> bool:
    return any(unicodedata.category(character).startswith("C") for character in value)


def normalise_text(value: Any, limit: int = COLUMN_LIMIT) -> str | None:
    """A displayable string, or ``None``: NFKC, no category C, a fixed ASCII class, bounded.

    The class is ASCII letters and digits plus a few marks, like the identifier class: a
    confusable letter from another script (a Cyrillic ie in place of the Latin e of a
    forbidden word) would otherwise pass the forbidden-word check, which matches Latin
    words, and reach a screen.
    """

    if not isinstance(value, str):
        return None
    text = unicodedata.normalize("NFKC", value).strip()
    if not text or len(text) > limit or _has_control(text):
        return None
    if not all(
        (character.isascii() and character.isalnum()) or character in TEXT_PUNCTUATION
        for character in text
    ):
        return None
    return text


def normalise_identifier(value: Any, pattern: re.Pattern[str] = SOURCE_ID) -> str | None:
    """An identifier kept only when it matches an ASCII pattern and NFKC leaves it unchanged."""

    if not isinstance(value, str) or len(value) > IDENTIFIER_LIMIT:
        return None
    if unicodedata.normalize("NFKC", value) != value or _has_control(value):
        return None
    return value if pattern.match(value) else None


def normalise_notes(value: Any, limit: int = NOTES_LIMIT) -> str | None:
    """Release-note text for the family-token match only: never displayed, never quoted.

    Line breaks and tabs are ordinary in notes and become spaces; any other category C
    character (a zero-width joiner, a direction override) refuses the text, because it is
    exactly how a word is split or disguised.
    """

    if not isinstance(value, str) or len(value) > limit:
        return None
    text = unicodedata.normalize("NFKC", value).replace("\r", " ").replace("\n", " ")
    text = text.replace("\t", " ")
    if _has_control(text):
        return None
    return text


def family_token(model_id: str) -> str:
    """The name part of the id, with one trailing size segment removed.

    `Fixturelm-4B` gives `Fixturelm`; an id without a size segment keeps its whole name.
    """

    name = model_id.rsplit("/", 1)[-1]
    stripped = SIZE_SUFFIX.sub("", name, count=1)
    return stripped or name


def claim_names_family(notes: str, token: str) -> bool:
    """A whole-token, case-insensitive identifier match; `Qwen3` never matches `Qwen3.5`."""

    if not token:
        return False
    pattern = re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])(?![.-][A-Za-z0-9])",
        re.IGNORECASE,
    )
    return pattern.search(notes) is not None


def weight_floor_gib(parameters: Any) -> tuple[float | None, str]:
    """Bytes of stored weights from `safetensors.parameters`, as GiB; a floor, not a need."""

    if not isinstance(parameters, dict) or not parameters:
        return None, "The source publishes no safetensors parameter counts."
    total = 0
    for dtype, count in parameters.items():
        width = DTYPE_BYTES.get(str(dtype))
        if width is None:
            return (
                None,
                f"The dtype {normalise_text(dtype, 20) or 'given'} has no known byte width.",
            )
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            return None, "A parameter count is not a whole number."
        if count > MAXIMUM_PARAMETER_COUNT:
            return None, "A parameter count is outside the supported range."
        total += width * count
    return round(total / 1024**3, 3), WEIGHT_FLOOR_ESTIMATOR


# ----- the research gates ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GateFacts:
    """What the gates read about one item; every field is already normalised or typed."""

    kind: str
    source_id: str | None
    namespace: str | None
    licence_id: str | None
    gated: bool | None
    archived: bool | None
    disabled: bool | None
    dated_at: str | None
    has_digest_or_commit: bool
    capability_known: bool
    displayed_strings: tuple[str, ...]
    malformed: bool = False
    unreachable: bool = False


def licence_entry_for(licence_id: str | None, licences: dict[str, Any]) -> dict[str, Any] | None:
    """The licence-list entry for an SPDX id, a GitHub keyword or a Hub tag, or ``None``."""

    if not isinstance(licence_id, str):
        return None
    wanted = licence_id.strip().casefold()
    if not wanted:
        return None
    for entry in licences.get("licences", []):
        candidates = {
            str(entry["spdx_id"]).casefold(),
            str(entry["github_keyword"]).casefold(),
            str(entry["hub_tag"]).casefold(),
        }
        if wanted in candidates:
            return dict(entry)
    return None


def research_gates(
    facts: GateFacts,
    *,
    licences: dict[str, Any],
    trusted_namespaces: frozenset[str],
    reviewed_harnesses: frozenset[str],
    review: str | None,
    occurred_at: str,
    freshness_window_days: int,
) -> tuple[str, str, tuple[str, ...]]:
    """`(tier, verdict, reasons)` under `community-research-gates-1.0.0`.

    A failure is a stable reason code. The unvetted tier alone makes the verdict
    `needs_review`; a recorded accept lifts it, a recorded reject fails it. Nothing here
    writes `eligible` or `approved_for_context`.
    """

    reasons: list[str] = []
    if facts.malformed or facts.source_id is None:
        reasons.append(REASON_MALFORMED)
    if facts.unreachable:
        reasons.append(REASON_UNREACHABLE)
    entry = licence_entry_for(facts.licence_id, licences)
    if entry is None:
        reasons.append(REASON_LICENCE_UNLISTED)
    elif str(entry["classification"]) in BLOCKED_LICENCE_CLASSES:
        reasons.append(REASON_LICENCE_BLOCKED)
    if facts.gated:
        reasons.append(REASON_GATED)
    if facts.archived:
        reasons.append(REASON_ARCHIVED)
    if facts.disabled:
        reasons.append(REASON_DISABLED)
    if facts.dated_at is None:
        reasons.append(REASON_UNDATED)
    else:
        now = catalogue_timestamp(occurred_at)
        dated = catalogue_timestamp(facts.dated_at)
        if dated > now:
            reasons.append(REASON_FUTURE)
        elif now - dated > timedelta(days=freshness_window_days):
            reasons.append(REASON_STALE)
    if not facts.has_digest_or_commit:
        reasons.append(REASON_UNDIGESTED)
    if not facts.capability_known:
        reasons.append(REASON_CAPABILITY)
    if any(forbidden_words(text) for text in facts.displayed_strings):
        reasons.append(REASON_FORBIDDEN_WORD)
    if facts.kind == "model":
        trusted = facts.namespace is not None and facts.namespace in trusted_namespaces
    else:
        trusted = facts.source_id is not None and facts.source_id.casefold() in reviewed_harnesses
    tier = "trusted" if trusted else "unvetted"
    if review == "reject":
        reasons.append(REASON_REJECTED)
    elif not trusted and review != "accept":
        reasons.append(REASON_UNVETTED)
    ordered = tuple(sorted(set(reasons)))
    if not ordered:
        verdict = "passed"
    elif ordered == (REASON_UNVETTED,):
        verdict = "needs_review"
    else:
        verdict = "failed"
    return tier, verdict, ordered


# ----- the honest manifest ----------------------------------------------------------------


def evidence_reference(
    identifier: str,
    evidence_class: str,
    *,
    uri: str | None,
    version: str | None,
    checked_at: str,
    content_digest: str,
    source_word: str,
) -> dict[str, Any]:
    """An `evidenceRef` for one evidence class, never reading as if OAK checked it."""

    source_type, confidence = EVIDENCE_SOURCE_TYPES[evidence_class]
    return {
        "id": identifier,
        "title": f"{EVIDENCE_WORDS[evidence_class]} ({source_word})",
        "uri": uri,
        "version": version,
        "source_type": source_type,
        "checked_at": checked_at,
        "confidence": confidence,
        "content_digest": content_digest,
    }


def research_manifest(
    *,
    manifest_id: str,
    name: str,
    category: str,
    kind: str,
    owner: str,
    project_url: str,
    repository_url: str | None,
    release_version: str,
    released_at: str | None,
    artifact_reference: str,
    artifact_digest: str,
    digest_covers: str,
    commit_id: str | None,
    licence: dict[str, Any] | None,
    licence_domain: str,
    capabilities: list[str],
    evidence: list[dict[str, Any]],
    measurements: list[dict[str, Any]],
    occurred_at: str,
    freshness_window_days: int,
    research: dict[str, Any],
) -> dict[str, Any]:
    """A `component-manifest` for a researched item: what was read, and honest gaps.

    Every field nobody published takes the schema's honest value; a required free-text
    field says that the source did not publish it. Research never writes `eligible` or
    `approved_for_context`, and a commit id never enters a sha256 field.
    """

    pending = {
        "spdx_expression": None,
        "terms_url": None,
        "classification": "unknown",
        "review_status": "pending",
    }
    not_applicable = {
        "spdx_expression": None,
        "terms_url": None,
        "classification": "not_applicable",
        "review_status": "not_applicable",
    }
    licensed = dict(pending)
    if licence is not None:
        licensed = {
            "spdx_expression": str(licence["spdx_id"]),
            "terms_url": str(licence["source"]),
            "classification": str(licence["classification"]),
            "review_status": "pending",
        }
    licensing = {
        "software": licensed if licence_domain == "software" else not_applicable,
        "model": licensed if licence_domain == "model" else not_applicable,
        "data": not_applicable,
        "transitive_review": "pending",
        "redistribution_constraints": [],
    }
    next_review = catalogue_timestamp(occurred_at) + timedelta(days=freshness_window_days)
    return {
        "schema_version": "0.3.0",
        "id": manifest_id,
        "name": name,
        "category": category,
        "description": (
            f"Researched {kind.replace('_', ' ')}; compared, never approved. "
            "See the research snapshot."
        ),
        "owner": owner,
        "project_url": project_url,
        "repository_url": repository_url,
        "release": {
            "version": release_version,
            "released_at": released_at[:10] if released_at else None,
            "support_until": None,
            "update_policy": NOT_PUBLISHED,
        },
        "artifact": {
            "reference": artifact_reference,
            "digest": artifact_digest,
            "media_type": "application/json",
            "signature_status": "unknown",
            "provenance_status": "unknown",
            "sbom_status": "unknown",
        },
        "licensing": licensing,
        "availability_class": "unknown",
        "maturity": {
            "governance": NOT_PUBLISHED,
            "lifecycle_stage": "unknown",
            "maintainers": None,
            "release_cadence": NOT_PUBLISHED,
            "adoption_evidence": [],
            "commercial_support": [],
            "confidence": 0.0,
        },
        "targets": {
            "operating_systems": [],
            "cpu_architectures": [],
            "accelerators": [],
            "drivers": [],
            "minimum_resources": {},
        },
        "interfaces": [
            {"name": "unknown", "kind": "other", "version": None, "direction": "provides"}
        ],
        "deployment": {
            "modes": [],
            "offline_behavior": NOT_PUBLISHED,
            "external_calls": [],
            "telemetry_default": NOT_PUBLISHED,
            "air_gap_suitability": "unknown",
        },
        "security": {
            "identity": NOT_PUBLISHED,
            "tenancy": NOT_PUBLISHED,
            "encryption": NOT_PUBLISHED,
            "secrets": NOT_PUBLISHED,
            "network": NOT_PUBLISHED,
            "audit": NOT_PUBLISHED,
            "known_vulnerabilities": [],
            "security_advisory_url": None,
        },
        "data_handling": {
            "data_types": [],
            "retention": NOT_PUBLISHED,
            "deletion": NOT_PUBLISHED,
            "residency": NOT_PUBLISHED,
            "privacy_implications": [],
        },
        "operations": {
            "observability": NOT_PUBLISHED,
            "backup": NOT_PUBLISHED,
            "restore": NOT_PUBLISHED,
            "upgrade": NOT_PUBLISHED,
            "downgrade": NOT_PUBLISHED,
            "rollback": NOT_PUBLISHED,
            "disaster_recovery": NOT_PUBLISHED,
            "operational_burden": "unknown",
        },
        "measurements": measurements,
        "limitations": [
            "A researched entry: it reaches comparison only, under "
            f"{RESEARCH_GATES_VERSION}, and is never approved for a context by research."
        ],
        "substitutes": [],
        "evidence": evidence,
        "status": "quarantined",
        "next_review_at": next_review.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "extensions": {
            RESEARCH_EXTENSION: {
                **research,
                "commit_id": commit_id,
                "digest_covers": digest_covers,
            },
            "oak.community/capabilities": sorted(capabilities),
        },
    }


def manifest_slug(source_id: str) -> str:
    """`HuggingFaceTB/Fixturelm-4B` → `huggingfacetb.fixturelm-4b`, inside the identifier shape."""

    lowered = source_id.casefold().replace("/", ".")
    return re.sub(r"[^a-z0-9.-]", "-", lowered)


def as_timestamp(value: Any) -> str | None:
    """An ISO 8601 UTC timestamp from the source's date, or ``None`` when it is not one."""

    if not isinstance(value, str) or len(value) > 40:
        return None
    text = value.strip()
    if len(text) == 10:
        text = f"{text}T00:00:00Z"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
