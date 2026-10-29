# SPDX-License-Identifier: Apache-2.0
"""The format chain's rules, each refused on its own (RR-017)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from oak.domain import Artifact, OAKError
from oak.domain.workspace_format import (
    CURRENT_MANIFEST_FORMAT,
    PRODUCTION_CHAIN,
    FormatChain,
    FormatStep,
    StepResult,
    manifest_format,
    migrate_manifest,
)

OBJECT = b"safe synthetic brief\n"
OBJECT_DIGEST = Artifact(
    id="brief.t", version="0.1.0", kind="brief_source", media_type="text/plain", content=OBJECT
).digest
CASE_REF = {
    "id": "design-case.t",
    "version": "0.1.0",
    "digest": f"sha256:{'c' * 64}",
    "media_type": "application/vnd.oak.design-case+json",
}


def _manifest(format_name: str = "0.3.9") -> dict[str, Any]:
    return {
        "schema_version": format_name,
        "id": "workspace.t",
        "version": 1,
        "tenant_id": "local",
        "created_at": "2026-10-29T00:00:00Z",
        "updated_at": "2026-10-29T00:00:00Z",
        "current_case_ref": copy.deepcopy(CASE_REF),
        "artifact_index": [
            {
                "id": "brief.t",
                "version": "0.1.0",
                "digest": OBJECT_DIGEST,
                "media_type": "text/plain",
                "kind": "brief_source",
                "size_bytes": len(OBJECT),
            }
        ],
        "audit_events": [{"id": "audit.1", "version": "1", "digest": "sha256:" + "e" * 64}],
        "idempotency_records": [{"key": "k" * 16}],
        "extensions": {},
    }


def _read(digest: str) -> bytes:
    assert digest == OBJECT_DIGEST
    return OBJECT


def _chain(*mutations: Any) -> FormatChain:
    """One step from 0.3.9 to the current format applying the given edits in order."""

    def apply(manifest: dict[str, Any], read: Any) -> StepResult:
        manifest["schema_version"] = CURRENT_MANIFEST_FORMAT
        result = StepResult(manifest=manifest)
        for mutation in mutations:
            result = mutation(result, read)
        return result

    return FormatChain((FormatStep("0.3.9", CURRENT_MANIFEST_FORMAT, "test-step", apply),))


def _migrate(chain: FormatChain, manifest: dict[str, Any] | None = None) -> Any:
    return migrate_manifest(
        manifest or _manifest(), chain, _read, source_digest=f"sha256:{'0' * 64}"
    )


def _refused(chain: FormatChain, manifest: dict[str, Any] | None = None) -> str:
    with pytest.raises(OAKError) as refusal:
        _migrate(chain, manifest)
    return refusal.value.code


def _refusal(chain: FormatChain, manifest: dict[str, Any] | None = None) -> str:
    """The refusal's message, for tests that pin which rule fired."""

    with pytest.raises(OAKError) as refusal:
        _migrate(chain, manifest)
    assert refusal.value.code == "OAK-WORKSPACE-MIGRATION"
    return refusal.value.message


def test_the_shipped_chain_holds_no_step_and_reads_only_the_current_format() -> None:
    assert PRODUCTION_CHAIN.known_formats == (CURRENT_MANIFEST_FORMAT,)
    assert PRODUCTION_CHAIN.path(CURRENT_MANIFEST_FORMAT) == ()
    with pytest.raises(OAKError) as refusal:
        PRODUCTION_CHAIN.path("0.3.9")
    assert refusal.value.code == "OAK-WORKSPACE-FORMAT"


@pytest.mark.parametrize(
    "steps",
    [
        [("0.4.0", "0.5.0")],  # a step from the current format
        [("0.3.9", "0.3.9")],  # a step to itself
        [("0.3.9", "0.4.0"), ("0.3.9", "0.4.0")],  # two steps from one format
        [("0.3.8", "0.3.9")],  # a step whose target no step accepts
        [("0.3.8", "0.3.9"), ("0.3.9", "0.3.8")],  # a cycle
    ],
)
def test_a_malformed_chain_cannot_be_built(steps: list[tuple[str, str]]) -> None:
    with pytest.raises(ValueError):
        FormatChain(
            tuple(
                FormatStep(start, end, f"step-{index}", lambda m, r: StepResult(manifest=m))
                for index, (start, end) in enumerate(steps)
            )
        )


@pytest.mark.parametrize(
    "document",
    [None, [], {}, {"schema_version": 4}, {"schema_version": ""}, {"schema_version": "v1"}],
)
def test_a_manifest_that_names_no_readable_format_is_corrupt(document: Any) -> None:
    with pytest.raises(OAKError) as refusal:
        manifest_format(document)
    assert refusal.value.code == "OAK-WORKSPACE-CORRUPT"


def test_a_current_manifest_migrates_as_a_no_op() -> None:
    outcome = _migrate(_chain(), _manifest(CURRENT_MANIFEST_FORMAT))
    assert outcome.steps == ()
    assert not outcome.changed
    assert not outcome.reshapes_case
    assert outcome.manifest == _manifest(CURRENT_MANIFEST_FORMAT)


def test_a_well_formed_step_carries_the_manifest_forward_and_names_what_it_added() -> None:
    added = Artifact(
        id="note.t", version="0.1.0", kind="brief_source", media_type="text/plain", content=b"n"
    )

    def add(result: StepResult, read: Any) -> StepResult:
        assert read(OBJECT_DIGEST) == OBJECT
        manifest = result.manifest
        manifest["artifact_index"].append(added.index_document())
        return StepResult(manifest=manifest, new_artifacts=(added,))

    outcome = _migrate(_chain(add))
    assert outcome.from_format == "0.3.9"
    assert outcome.to_format == CURRENT_MANIFEST_FORMAT
    assert outcome.steps == ("test-step",)
    assert outcome.new_artifacts == (added,)
    assert outcome.manifest["schema_version"] == CURRENT_MANIFEST_FORMAT
    assert outcome.changed and outcome.reshapes_case
    # Pure: the same inputs give the same outcome, and the input is left alone.
    source = _manifest()
    first = migrate_manifest(source, _chain(add), _read, source_digest="sha256:" + "0" * 64)
    second = migrate_manifest(source, _chain(add), _read, source_digest="sha256:" + "0" * 64)
    assert first == second
    assert source == _manifest()


def test_a_later_step_reads_what_an_earlier_one_produced() -> None:
    added = Artifact(
        id="note.t", version="0.1.0", kind="brief_source", media_type="text/plain", content=b"n"
    )

    def first(manifest: dict[str, Any], read: Any) -> StepResult:
        manifest["schema_version"] = "0.3.9"
        manifest["artifact_index"].append(added.index_document())
        return StepResult(manifest=manifest, new_artifacts=(added,))

    def second(manifest: dict[str, Any], read: Any) -> StepResult:
        assert read(added.digest) == b"n"
        manifest["schema_version"] = CURRENT_MANIFEST_FORMAT
        return StepResult(manifest=manifest)

    chain = FormatChain(
        (
            FormatStep("0.3.8", "0.3.9", "first", first),
            FormatStep("0.3.9", CURRENT_MANIFEST_FORMAT, "second", second),
        )
    )
    outcome = _migrate(chain, _manifest("0.3.8"))
    assert outcome.steps == ("first", "second")
    assert outcome.new_artifacts == (added,)


def test_a_step_that_drops_a_stored_object_is_refused() -> None:
    def drop(result: StepResult, read: Any) -> StepResult:
        result.manifest["artifact_index"].clear()
        return result

    assert _refused(_chain(drop)) == "OAK-WORKSPACE-MIGRATION"


def test_a_step_that_rewrites_a_stored_object_is_refused() -> None:
    def rewrite(result: StepResult, read: Any) -> StepResult:
        result.manifest["artifact_index"][0]["digest"] = "sha256:" + "f" * 64
        return result

    assert _refused(_chain(rewrite)) == "OAK-WORKSPACE-MIGRATION"


def test_a_step_that_names_an_object_it_did_not_produce_is_refused() -> None:
    def invent(result: StepResult, read: Any) -> StepResult:
        result.manifest["artifact_index"].append(
            {**result.manifest["artifact_index"][0], "id": "ghost", "digest": "sha256:" + "d" * 64}
        )
        return result

    assert _refused(_chain(invent)) == "OAK-WORKSPACE-MIGRATION"


def test_a_step_whose_index_does_not_name_what_it_produced_is_refused() -> None:
    added = Artifact(
        id="note.t", version="0.1.0", kind="brief_source", media_type="text/plain", content=b"n"
    )

    def forget(result: StepResult, read: Any) -> StepResult:
        return StepResult(manifest=result.manifest, new_artifacts=(added,))

    assert _refused(_chain(forget)) == "OAK-WORKSPACE-MIGRATION"


def test_a_step_that_returns_a_stored_object_as_new_is_refused() -> None:
    stored = Artifact(
        id="brief.t", version="0.1.0", kind="brief_source", media_type="text/plain", content=OBJECT
    )

    def repeat(result: StepResult, read: Any) -> StepResult:
        return StepResult(manifest=result.manifest, new_artifacts=(stored,))

    assert _refused(_chain(repeat)) == "OAK-WORKSPACE-MIGRATION"


@pytest.mark.parametrize("key", ["id", "tenant_id"])
def test_a_step_that_changes_the_workspace_identity_is_refused(key: str) -> None:
    def rename(result: StepResult, read: Any) -> StepResult:
        result.manifest[key] = "other"
        return result

    assert _refused(_chain(rename)) == "OAK-WORKSPACE-MIGRATION"


@pytest.mark.parametrize("key", ["schema_version", "id", "tenant_id", "artifact_index"])
def test_a_step_that_drops_an_invariant_key_is_refused(key: str) -> None:
    def drop(result: StepResult, read: Any) -> StepResult:
        del result.manifest[key]
        return result

    assert _refused(_chain(drop)) in {"OAK-WORKSPACE-MIGRATION", "OAK-WORKSPACE-CORRUPT"}


def test_a_step_that_does_not_reach_its_format_is_refused() -> None:
    def stall(result: StepResult, read: Any) -> StepResult:
        result.manifest["schema_version"] = "0.3.9"
        return result

    assert _refused(_chain(stall)) == "OAK-WORKSPACE-MIGRATION"


@pytest.mark.parametrize("key", ["audit_events", "idempotency_records"])
def test_a_step_that_edits_the_history_is_refused(key: str) -> None:
    def edit(result: StepResult, read: Any) -> StepResult:
        result.manifest[key].append(copy.deepcopy(result.manifest[key][0]))
        return result

    assert _refused(_chain(edit)) == "OAK-WORKSPACE-MIGRATION"


def test_a_step_that_moves_the_current_case_is_refused() -> None:
    def move(result: StepResult, read: Any) -> StepResult:
        result.manifest["current_case_ref"] = {**CASE_REF, "version": "0.1.1"}
        return result

    assert _refused(_chain(move)) == "OAK-WORKSPACE-MIGRATION"


def test_a_step_that_reshapes_another_case_is_refused() -> None:
    def other(result: StepResult, read: Any) -> StepResult:
        return StepResult(
            manifest=result.manifest, case_document={"id": "design-case.other", "version": "0.1.0"}
        )

    assert _refused(_chain(other)) == "OAK-WORKSPACE-MIGRATION"


def test_a_step_that_reshapes_a_case_the_workspace_does_not_hold_is_refused() -> None:
    def phantom(result: StepResult, read: Any) -> StepResult:
        return StepResult(manifest=result.manifest, case_document={**CASE_REF})

    manifest = _manifest()
    manifest["current_case_ref"] = None
    assert _refused(_chain(phantom), manifest) == "OAK-WORKSPACE-MIGRATION"


def test_a_step_that_returns_no_manifest_is_refused() -> None:
    def nothing(result: StepResult, read: Any) -> StepResult:
        return StepResult(manifest=None)  # type: ignore[arg-type]

    assert _refused(_chain(nothing)) == "OAK-WORKSPACE-MIGRATION"


@pytest.mark.parametrize("field", ["id", "version", "kind", "media_type"])
def test_a_step_that_relabels_an_indexed_object_is_refused(field: str) -> None:
    """The index entry is the object's identity: its bytes alone are not (review W3)."""

    def relabel(result: StepResult, read: Any) -> StepResult:
        entry = dict(result.manifest["artifact_index"][0])
        entry[field] = "other" if field != "version" else "9.9.9"
        result.manifest["artifact_index"][0] = entry
        return result

    assert "dropped, rewrote or reordered" in _refusal(_chain(relabel))


def test_a_step_that_reorders_the_index_or_drops_a_twin_entry_is_refused() -> None:
    def reorder(result: StepResult, read: Any) -> StepResult:
        result.manifest["artifact_index"].reverse()
        return result

    def drop_twin(result: StepResult, read: Any) -> StepResult:
        # Two entries sharing bytes: dropping one leaves the digest indexed, so a
        # digest-only rule would not notice.
        del result.manifest["artifact_index"][1]
        return result

    manifest = _manifest()
    twin = dict(manifest["artifact_index"][0])
    twin["id"] = "twin.object"
    manifest["artifact_index"].append(twin)
    assert "dropped, rewrote or reordered" in _refusal(_chain(reorder), manifest)
    assert "dropped, rewrote or reordered" in _refusal(_chain(drop_twin), manifest)


@pytest.mark.parametrize("edit", ["reverse", "drop"])
def test_a_step_that_reorders_or_drops_the_history_is_refused(edit: str) -> None:
    """A length check let a reversed or dropped history through (review W4)."""

    def reverse(result: StepResult, read: Any) -> StepResult:
        result.manifest["audit_events"].reverse()
        return result

    def drop(result: StepResult, read: Any) -> StepResult:
        del result.manifest["audit_events"]
        return result

    manifest = _manifest()
    manifest["audit_events"] = [
        {"id": "audit.1", "digest": "sha256:" + "1" * 64},
        {"id": "audit.2", "digest": "sha256:" + "2" * 64},
    ]
    assert "edited the workspace history" in _refusal(
        _chain(reverse if edit == "reverse" else drop), manifest
    )
