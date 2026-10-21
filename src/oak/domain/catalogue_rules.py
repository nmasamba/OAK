# SPDX-License-Identifier: Apache-2.0
"""The curated catalogue's eligibility rules, `community-open-components-1.0.0`.

Moved here from the compiler in Sprint 14 so that research can list, on each item, the
curated reasons that would still apply to its manifest (ADR-0018: kept as visible review
items, never dropped). The function is pure and its output is byte-identical to what the
compiler produced before the move; the compiler imports it from here.
"""

from datetime import datetime
from typing import Any

from oak.domain.errors import OAKError

ALLOWED_AVAILABILITY = frozenset({"osi_open_source_software", "osi_open_source_ai"})
DISALLOWED_LICENCE_CLASSES = frozenset({"restricted", "source_available", "proprietary", "unknown"})


def catalogue_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OAKError("OAK-CATALOGUE-TIME", "catalogue timestamp is invalid") from error


def eligibility_reasons(document: dict[str, Any], valid_at: datetime) -> tuple[str, ...]:
    reasons: list[str] = []
    if document["status"] not in {"eligible", "approved_for_context"}:
        reasons.append("OAK-CAT-STATUS-NOT-ELIGIBLE")
    if document["availability_class"] not in ALLOWED_AVAILABILITY:
        reasons.append("OAK-CAT-AVAILABILITY-BLOCKED")
    if catalogue_timestamp(str(document["next_review_at"])) <= valid_at:
        reasons.append("OAK-CAT-EVIDENCE-STALE")
    if document["security"]["known_vulnerabilities"]:
        reasons.append("OAK-CAT-KNOWN-VULNERABILITY")
    if document["licensing"]["transitive_review"] != "passed":
        reasons.append("OAK-CAT-TRANSITIVE-LICENCE-UNRESOLVED")
    for domain in ("software", "model", "data"):
        licence = document["licensing"][domain]
        if licence["classification"] in DISALLOWED_LICENCE_CLASSES:
            reasons.append(f"OAK-CAT-{domain.upper()}-LICENCE-BLOCKED")
        if licence["review_status"] not in {"passed", "not_applicable"}:
            reasons.append(f"OAK-CAT-{domain.upper()}-LICENCE-UNREVIEWED")
    for evidence in document["evidence"]:
        if evidence["content_digest"] is None:
            reasons.append("OAK-CAT-EVIDENCE-UNDIGESTED")
        if catalogue_timestamp(str(evidence["checked_at"])) > valid_at:
            reasons.append("OAK-CAT-EVIDENCE-FUTURE")
    return tuple(sorted(set(reasons)))
