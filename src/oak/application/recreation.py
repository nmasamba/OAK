# SPDX-License-Identifier: Apache-2.0
"""Read from a local export what a server needs to re-create its case.

A server keeps one workspace per case, named from the case, while a local workspace is
named from its directory, so a local export carries an identity the server does not hold.
It is not rebound: the workspace identity is inside a compiled mutation plan, its
signature and any approval of it. Instead the server re-creates the case through its own
steps (create, interpret, confirm) from two things in the export, the brief and the
confirmed answers, under the importing command's authority. Nothing else from the export
reaches the server: no approval, signature, tenant or later history.

Confirming stores no answers document. Each answer's question, decision and rationale are
kept in the intent with a digest of its value, and the value itself is written into the
intent. So each value is read back from the intent version that answer produced, and is
used only if it hashes to the recorded digest; an answer that cannot be recovered exactly
stops the re-creation before anything is created.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from oak.application.design_case import PROPOSAL_REF_EXTENSION, DesignCaseService
from oak.contracts import load_json_document
from oak.domain import OAKError, canonical_json_bytes, content_digest

CONFIRMATIONS_EXTENSION = "oak.community/confirmations"
SOURCE_RECORD_EXTENSION = "oak.community/source_record_ref"
RECREATED_FROM_EXTENSION = "oak.community/recreated_from"


@dataclass(frozen=True, slots=True)
class ReplayPlan:
    """What the server replays, and the origin it records."""

    original_name: str
    content: bytes
    interpreted: bool
    rounds: tuple[tuple[dict[str, Any], ...], ...]
    origin: dict[str, Any]


def _refused(message: str) -> OAKError:
    return OAKError("OAK-IMPORT-REPLAY", message)


def _document(objects: Mapping[str, bytes], reference: object) -> dict[str, Any]:
    digest = reference.get("digest") if isinstance(reference, dict) else None
    if not isinstance(digest, str) or digest not in objects:
        raise _refused("the export does not hold an object the case refers to")
    document = load_json_document(objects[digest].decode("utf-8"))
    if not isinstance(document, dict):
        raise _refused("an object the case refers to is not a document")
    return document


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _value_digest(value: Any) -> str:
    return content_digest(canonical_json_bytes({"value": value}))


def _pointer(document: dict[str, Any], path: str) -> tuple[bool, Any]:
    try:
        return True, DesignCaseService._pointer_get(document, path)
    except OAKError:
        return False, None


def replay_plan(manifest: Mapping[str, Any], objects: Mapping[str, bytes]) -> ReplayPlan:
    """Read the brief and the confirmed answers, each checked against its digest.

    `objects` are the export's objects, already checked against their digests and the
    manifest's index by the caller; the documents inside them are not otherwise validated,
    so anything malformed is refused here with a stable code, never a raw exception whose
    message could quote the export.
    """

    try:
        return _replay_plan(manifest, objects)
    except OAKError:
        raise
    except (AttributeError, IndexError, KeyError, TypeError, UnicodeError, ValueError) as error:
        raise _refused("an object in the export is not the document its index says") from error


def _replay_plan(manifest: Mapping[str, Any], objects: Mapping[str, bytes]) -> ReplayPlan:
    current = manifest["current_case_ref"]
    case = _document(objects, current)
    brief_refs = case.get("brief_refs")
    if not isinstance(brief_refs, list) or len(brief_refs) != 1:
        raise _refused("the case does not name exactly one brief")
    brief_digest = brief_refs[0].get("digest") if isinstance(brief_refs[0], dict) else None
    if not isinstance(brief_digest, str) or brief_digest not in objects:
        raise _refused("the export does not hold the case's brief")
    extensions = case.get("extensions")
    source = _document(
        objects, extensions.get(SOURCE_RECORD_EXTENSION) if isinstance(extensions, dict) else None
    )
    original_name = source.get("original_name")
    if not isinstance(original_name, str) or not original_name:
        raise _refused("the brief's source record names no file")

    entries = [entry for entry in manifest.get("artifact_index", []) if isinstance(entry, dict)]
    intents = sorted(
        (_document(objects, entry) for entry in entries if entry.get("kind") == "system_intent"),
        key=lambda intent: _version_key(str(intent["version"])),
    )
    paths: dict[str, str] = {}
    for entry in entries:
        if entry.get("kind") != "design_case":
            continue
        for question in _document(objects, entry).get("unresolved_questions", []):
            question_id, path = str(question.get("id")), str(question.get("path"))
            if paths.setdefault(question_id, path) != path:
                raise _refused("a question names two different claims")

    # The chain must run from the interpreted intent to the case's own: an export with its
    # first or last versions removed would otherwise replay fewer answers, or none, and
    # still record the full case as its origin.
    intent_ref = case.get("intent_ref")
    if intent_ref is None and intents:
        raise _refused("the export holds intents its case does not name")
    if intent_ref is not None and (
        not intents
        or _document(objects, intent_ref) != intents[-1]
        or not isinstance(intent_ref, dict)
        or intent_ref.get("digest") not in {str(entry.get("digest")) for entry in entries}
    ):
        raise _refused("the export's intents do not end at the case's own intent")
    if intents and (
        intents[0].get("supersedes") is not None
        or intents[0].get("extensions", {}).get(CONFIRMATIONS_EXTENSION)
    ):
        raise _refused("the export's intents do not start at the interpretation")
    rounds: list[tuple[dict[str, Any], ...]] = []
    if intents:
        if len({str(intent["id"]) for intent in intents}) != 1:
            raise _refused("the export holds more than one intent")
        if PROPOSAL_REF_EXTENSION in intents[0].get("extensions", {}):
            # Its claims came from a model run the server would have to repeat, and a
            # model's answer can differ; the answers might then confirm other claims.
            raise _refused(
                "the case was interpreted with a model; create it on the server with "
                "`oak --server design` and confirm the answers again"
            )
        for previous, intent in pairwise(intents):
            if intent.get("supersedes") != f"{previous['id']}@{previous['version']}":
                raise _refused("the export's intent versions do not form one chain")
            before = previous.get("extensions", {}).get(CONFIRMATIONS_EXTENSION, [])
            after = intent.get("extensions", {}).get(CONFIRMATIONS_EXTENSION, [])
            if after[: len(before)] != before or len(after) == len(before):
                raise _refused("an intent version does not add to the confirmations")
            rounds.append(
                tuple(_recover(record, paths, previous, intent) for record in after[len(before) :])
            )
    return ReplayPlan(
        original_name=original_name,
        content=objects[brief_digest],
        interpreted=bool(intents),
        rounds=tuple(rounds),
        # From the manifest's reference, which its schema bounds, never from the case
        # document, which nothing validates.
        origin={
            "workspace_id": str(manifest["id"]),
            "case_id": str(current["id"]),
            "case_version": str(current["version"]),
            "case_digest": str(current["digest"]),
        },
    )


def _recover(
    record: Mapping[str, Any],
    paths: Mapping[str, str],
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    """One answer, its value read back from the intent and checked against its digest."""

    question_id = str(record.get("question_id"))
    decision = str(record.get("decision"))
    path = paths.get(question_id)
    if path is None:
        raise _refused("an answer names a question the export does not hold")
    candidates: list[Any] = []
    if decision == "reject":
        # A rejection removes the claim; the value it was sent with is not in the intent,
        # so the two values a client sends with one are tried.
        candidates.append(None)
        found, value = _pointer(before, path)
        if found:
            candidates.append(value)
    else:
        found, value = _pointer(after, path)
        if found:
            candidates.append(value)
    digest = record.get("value_digest")
    for candidate in candidates:
        if _value_digest(candidate) == digest:
            return {
                "question_id": question_id,
                "decision": decision,
                "value": candidate,
                "rationale": str(record.get("rationale", "")),
            }
    raise _refused("an answer's value cannot be recovered from the export exactly")
