# SPDX-License-Identifier: Apache-2.0
"""A per-case daily count of billable model requests (RR-041).

Every model-backed interpretation and every model-narrated report a case records is one
billable request to the provider (plus at most the one rate-limit retry the adapter makes
inside it). The count is read from the case's own audit history, so it survives restarts
and holds for the CLI, the API and MCP alike: an interpretation event that names an
interpreter, and a report event whose artifacts include a narrative, each count once on the
UTC day they were recorded. A request the provider refused or that failed records nothing
and is not counted; the adapters already stop such a request at one attempt and one retry.
"""

from __future__ import annotations

from typing import Any

from oak.domain import ArtifactReference, OAKError
from oak.ports import WorkspaceRepository

DEFAULT_MODEL_REQUESTS_PER_CASE_PER_DAY = 100
INTERPRETER_EXTENSION = "oak.community/interpreter"
NARRATIVE_ID_PREFIX = "narrative."


def _is_billable(event: dict[str, Any]) -> bool:
    extensions = event.get("extensions")
    extensions = extensions if isinstance(extensions, dict) else {}
    if event.get("event_type") == "brief_interpreted":
        return INTERPRETER_EXTENSION in extensions
    if event.get("event_type") == "report_recorded":
        references = extensions.get("oak.community/artifact_refs")
        return isinstance(references, list) and any(
            isinstance(item, dict) and str(item.get("id", "")).startswith(NARRATIVE_ID_PREFIX)
            for item in references
        )
    return False


def billable_requests_on(repository: WorkspaceRepository, day: str) -> int:
    """How many billable model requests the case recorded on `day` (`YYYY-MM-DD`, UTC)."""

    count = 0
    for reference in repository.manifest().get("audit_events", []):
        event = repository.read_json_artifact(ArtifactReference.from_document(reference))
        if str(event.get("occurred_at", ""))[:10] == day and _is_billable(event):
            count += 1
    return count


def check_model_budget(repository: WorkspaceRepository, *, occurred_at: str, maximum: int) -> None:
    """Refuse the next billable request once the case has made `maximum` today; `0` is off.

    Called before anything is sent to a provider, so a refused request spends nothing.
    """

    if maximum <= 0:
        return
    day = str(occurred_at)[:10]
    made = billable_requests_on(repository, day)
    if made >= maximum:
        raise OAKError(
            "OAK-MODEL-BUDGET",
            f"this case has recorded {made} billable model request(s) today, the configured "
            "daily maximum; try again after 00:00 UTC, raise "
            "OAK_MODEL_REQUESTS_PER_CASE_PER_DAY, or use the deterministic mode",
            retriable=True,
        )


__all__ = [
    "DEFAULT_MODEL_REQUESTS_PER_CASE_PER_DAY",
    "billable_requests_on",
    "check_model_budget",
]
