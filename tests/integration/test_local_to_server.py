# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-025: a local case is re-created on a server from its brief and confirmed answers.

The owner's choice (Q3, 2026-10-28) was guided re-creation: a local export's workspace
identity is not rebound, because a compiled mutation plan, its signature and any approval
of it carry that identity. The server replays the brief and the confirmed answers through
its own steps under the importing command's authority, and records where the case came
from. Nothing else crosses: no approval, signature, tenant or later history.
"""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from oak.application import CommandContext, CommunityControlPlane
from oak.domain import (
    ArtifactReference,
    OAKError,
    canonical_json_bytes,
    content_digest,
)
from oak.interfaces.cli.remote import read_export_directory
from tests.integration.test_persistent_api import persistent_control_plane  # noqa: F401
from tests.mcp_support import build_file_control_plane
from tests.runner_support import ROOT, build_compiled_case

pytestmark = pytest.mark.integration

NOW = "2026-10-28T12:00:00Z"
LATER = "2026-10-28T12:01:00Z"
CASE_ID = "design-case.public-manual-qa"


def _context(key: str, *, tenant: str = "local") -> CommandContext:
    return CommandContext(
        actor="server-user",
        tenant_id=tenant,
        idempotency_key=f"import-test-{key}-0001",
        expected_version=None,
        correlation_id=f"correlation-import-{key}",
        interface_origin="api",
        occurred_at=NOW,
    )


def _local_export(tmp_path: Path, *, compiled: bool = False) -> dict[str, Any]:
    """A case taken to bundle_compiled locally (and its plan signed and approved, if asked)."""

    harness = build_compiled_case(tmp_path / "local")
    if compiled:
        case = harness.release._repository.current_case()
        harness.release.sign_plan(harness.context("local-sign-000001", str(case["version"])))
        case = harness.release._repository.current_case()
        harness.release.approve(
            "architecture", harness.context("local-approve-0001", str(case["version"]))
        )
    from oak.bootstrap import create_design_case_service

    destination = tmp_path / "export"
    create_design_case_service(harness.workspace).export_to(destination)
    return read_export_directory(destination)


def _server(tmp_path: Path) -> CommunityControlPlane:
    control_plane, _ = build_file_control_plane(tmp_path / "server")
    return control_plane


def _events(plane: CommunityControlPlane) -> list[dict[str, Any]]:
    return list(plane.list_audit_events(CASE_ID, tenant_id="local"))


def _user_step(context: CommandContext, expected_version: str) -> CommandContext:
    return replace(context, expected_version=expected_version)


def _refused_with(plane: CommunityControlPlane, document: dict[str, Any], code: str) -> None:
    with pytest.raises(OAKError) as refused:
        plane.import_design_case(document, context=_context("refused"))
    assert refused.value.code == code
    with pytest.raises(OAKError) as absent:
        plane.get_design_case(CASE_ID, tenant_id="local")
    assert absent.value.code == "OAK-CASE-NOT-FOUND", "nothing was created"


def test_a_local_export_is_recreated_from_its_brief_and_answers(tmp_path: Path) -> None:
    exported = _local_export(tmp_path)
    assert exported["manifest"]["id"] == "workspace.fixture"
    plane = _server(tmp_path)

    result = plane.import_design_case(exported, context=_context("journey"))

    case = result.case
    assert case["id"] == CASE_ID and case["status"] == "ready_for_candidates"
    assert result.duplicate is False
    origin = case["extensions"]["oak.community/recreated_from"]
    assert origin == {
        "workspace_id": "workspace.fixture",
        "case_id": CASE_ID,
        "case_version": exported["manifest"]["current_case_ref"]["version"],
        "case_digest": exported["manifest"]["current_case_ref"]["digest"],
    }
    events = _events(plane)
    assert [event["event_type"] for event in events] == [
        "case_created",
        "workspace_imported",
        "brief_interpreted",
        "claims_confirmed",
    ]
    assert {event["interface_origin"] for event in events} == {"import"}
    assert {event["actor"] for event in events} == {"server-user"}
    assert events[1]["extensions"]["oak.community/recreated_from"] == origin
    # The server's own steps made it: what was confirmed is the same, its records are new.
    local_intent = _local_document(exported, "system_intent", last=True)
    assert result.intent is not None
    assert result.intent["spec"] == local_intent["spec"]
    assert [
        (record["question_id"], record["decision"], record["value_digest"])
        for record in result.intent["extensions"]["oak.community/confirmations"]
    ] == [
        (record["question_id"], record["decision"], record["value_digest"])
        for record in local_intent["extensions"]["oak.community/confirmations"]
    ]
    local_digests = {entry["digest"] for entry in exported["manifest"]["artifact_index"]}
    assert ArtifactReference.from_document(case["intent_ref"]).digest not in local_digests


def test_a_retried_import_converges_on_the_same_case(tmp_path: Path) -> None:
    exported = _local_export(tmp_path)
    plane = _server(tmp_path)
    first = plane.import_design_case(exported, context=_context("retry"))

    again = plane.import_design_case(exported, context=_context("retry"))

    assert again.duplicate is True
    assert again.case["version"] == first.case["version"]
    assert len(_events(plane)) == 4


def test_an_approved_compiled_case_brings_no_plan_approval_or_signature(tmp_path: Path) -> None:
    """An approval bound to the local identity must not become valid under the new one."""

    exported = _local_export(tmp_path, compiled=True)
    approvals = [
        entry for entry in exported["manifest"]["artifact_index"] if entry["kind"] == "approval"
    ]
    assert approvals, "the local case holds an architecture approval"
    plane = _server(tmp_path)

    case = plane.import_design_case(exported, context=_context("compiled")).case

    assert case["status"] == "ready_for_candidates"
    for field in ("selected_candidate_ref", "deployment_bundle_ref", "runner_plan_ref"):
        assert case.get(field) is None, field
    held = {artifact["digest"] for artifact in plane.list_artifacts(CASE_ID, tenant_id="local")}
    carried = {entry["digest"] for entry in exported["manifest"]["artifact_index"]}
    assert held.isdisjoint(carried - {_brief_digest(exported)})
    serialized = json.dumps(case)
    for approval in approvals:
        assert approval["digest"] not in serialized and approval["id"] not in serialized


def test_an_export_that_claims_another_tenant_is_refused(tmp_path: Path) -> None:
    exported = _local_export(tmp_path)
    exported["manifest"]["tenant_id"] = "another-tenant"

    _refused_with(_server(tmp_path), exported, "OAK-IMPORT-SCOPE")


def test_a_manifest_whose_digests_were_edited_is_refused(tmp_path: Path) -> None:
    exported = _local_export(tmp_path)
    entry = next(
        entry for entry in exported["manifest"]["artifact_index"] if entry["kind"] == "brief_source"
    )
    entry["digest"] = "sha256:" + "0" * 64

    _refused_with(_server(tmp_path), exported, "OAK-IMPORT-INVALID")


def test_an_object_whose_digest_does_not_match_is_refused(tmp_path: Path) -> None:
    exported = _local_export(tmp_path)
    brief = _brief_digest(exported)
    item = next(item for item in exported["objects"] if item["digest"] == brief)
    edited = base64.b64decode(item["content_base64"]).replace(b"public", b"secret")
    item["content_base64"] = base64.b64encode(edited).decode("ascii")

    _refused_with(_server(tmp_path), exported, "OAK-IMPORT-DIGEST")


def test_a_case_the_server_already_holds_is_refused(tmp_path: Path) -> None:
    exported = _local_export(tmp_path)
    plane = _server(tmp_path)
    brief = (ROOT / "examples/briefs/public-manual-qa.yaml").read_bytes()
    plane.create_design_case(
        original_name="public-manual-qa.yaml", content=brief, context=_context("existing")
    )

    with pytest.raises(OAKError) as refused:
        plane.import_design_case(exported, context=_context("collides"))

    assert refused.value.code == "OAK-CASE-EXISTS"
    assert [event["event_type"] for event in _events(plane)] == ["case_created"]


def test_a_model_interpreted_case_is_refused_before_anything_is_created(tmp_path: Path) -> None:
    exported = _local_export(tmp_path)
    _rewrite_intents(
        exported,
        lambda intent: intent["extensions"].__setitem__(
            "oak.community/interpretation_proposal_ref",
            {"id": "proposal.x", "version": "0.1.0", "digest": "sha256:" + "a" * 64},
        ),
    )

    _refused_with(_server(tmp_path), exported, "OAK-IMPORT-REPLAY")


def test_an_answer_whose_value_cannot_be_recovered_is_refused(tmp_path: Path) -> None:
    exported = _local_export(tmp_path)

    def tamper(intent: dict[str, Any]) -> None:
        for record in intent["extensions"].get("oak.community/confirmations", []):
            record["value_digest"] = "sha256:" + "b" * 64

    _rewrite_intents(exported, tamper)

    _refused_with(_server(tmp_path), exported, "OAK-IMPORT-REPLAY")


def test_an_export_from_a_server_still_imports_as_itself(tmp_path: Path) -> None:
    """The server-shaped path restores the case: its identity is the server's. Since Tier
    3's Batch A the restore records the importer after the restored history, whose actors
    are the export's claims (OAK-V1-036)."""

    origin = _server(tmp_path / "origin")
    brief = (ROOT / "examples/briefs/public-manual-qa.yaml").read_bytes()
    origin.create_design_case(
        original_name="public-manual-qa.yaml",
        content=brief,
        context=replace(_context("origin"), actor="exporting-user"),
    )
    exported = origin.export_design_case(CASE_ID, tenant_id="local")
    plane = _server(tmp_path)

    result = plane.import_design_case(exported, context=_context("server-shaped"))
    case = result.case

    assert result.duplicate is False
    assert "oak.community/recreated_from" not in case["extensions"]
    events = _events(plane)
    assert [event["event_type"] for event in events] == ["case_created", "workspace_restored"]
    restored, importer = events
    assert restored["actor"] == "exporting-user", "the restored event keeps the export's claim"
    assert importer["actor"] == "server-user"
    assert importer["interface_origin"] == "import"
    assert importer["case_version"] == case["version"] != "0.1.0"
    origin_record = case["extensions"]["oak.community/restored_from"]
    assert origin_record == importer["extensions"]["oak.community/restored_from"]
    assert origin_record == {
        "manifest_id": exported["manifest"]["id"],
        "manifest_digest": content_digest(canonical_json_bytes(exported["manifest"])),
        "case_id": CASE_ID,
        "case_version": "0.1.0",
        "audit_events": 1,
    }
    assert case["status"] == "draft", "a restore changes no status"


def test_importing_a_server_export_again_is_a_duplicate_whatever_the_key(
    tmp_path: Path,
) -> None:
    origin = _server(tmp_path / "origin")
    brief = (ROOT / "examples/briefs/public-manual-qa.yaml").read_bytes()
    origin.create_design_case(
        original_name="public-manual-qa.yaml", content=brief, context=_context("origin")
    )
    exported = origin.export_design_case(CASE_ID, tenant_id="local")
    plane = _server(tmp_path)
    first = plane.import_design_case(exported, context=_context("restore-once"))

    same_key = plane.import_design_case(exported, context=_context("restore-once"))
    assert same_key.duplicate is True and same_key.case == first.case
    other_key = plane.import_design_case(exported, context=_context("restore-again"))
    assert other_key.duplicate is True and other_key.case == first.case
    assert [event["event_type"] for event in _events(plane)] == [
        "case_created",
        "workspace_restored",
    ], "a second import recorded a second restore"

    # A later export of the same case is another state: refused, never silently restored
    # over what the server holds.
    origin.interpret(CASE_ID, _user_step(_context("origin-moved"), "0.1.0"))
    moved = origin.export_design_case(CASE_ID, tenant_id="local")
    with pytest.raises(OAKError) as refusal:
        plane.import_design_case(moved, context=_context("restore-moved"))
    assert refusal.value.code == "OAK-IDEMPOTENCY-CONFLICT"
    assert len(_events(plane)) == 2


def _brief_digest(exported: dict[str, Any]) -> str:
    return next(
        entry["digest"]
        for entry in exported["manifest"]["artifact_index"]
        if entry["kind"] == "brief_source"
    )


def _objects(exported: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["digest"]: item for item in exported["objects"]}


def _local_document(exported: dict[str, Any], kind: str, *, last: bool) -> dict[str, Any]:
    entries = [entry for entry in exported["manifest"]["artifact_index"] if entry["kind"] == kind]
    entries.sort(key=lambda entry: tuple(int(part) for part in entry["version"].split(".")))
    entry = entries[-1] if last else entries[0]
    item = _objects(exported)[entry["digest"]]
    return json.loads(base64.b64decode(item["content_base64"]))


def _rewrite_intents(exported: dict[str, Any], change: Any) -> None:
    """Edit every intent and re-digest it consistently, so only the replay can object."""

    objects = _objects(exported)
    for entry in exported["manifest"]["artifact_index"]:
        if entry["kind"] != "system_intent":
            continue
        item = objects[entry["digest"]]
        document = json.loads(base64.b64decode(item["content_base64"]))
        change(document)
        content = canonical_json_bytes(document)
        digest = content_digest(content)
        old = entry["digest"]
        exported["objects"].remove(item)
        exported["objects"].append(
            {"digest": digest, "content_base64": base64.b64encode(content).decode("ascii")}
        )
        entry["digest"] = digest
        for other in exported["manifest"]["artifact_index"]:
            if other is not entry and other["digest"] == old:
                other["digest"] = digest
    exported["objects"].sort(key=lambda item: item["digest"])


def test_a_replay_the_server_refuses_part_way_says_how_far_it_got(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exported = _local_export(tmp_path)
    plane = _server(tmp_path)

    def refuse(*_: Any, **__: Any) -> Any:
        raise OAKError("OAK-CONFIRM-QUESTION", "answer references no open question")

    monkeypatch.setattr(plane, "confirm", refuse)
    with pytest.raises(OAKError) as stopped:
        plane.import_design_case(exported, context=_context("partial"))

    assert stopped.value.code == "OAK-IMPORT-REPLAY"
    assert "up to needs_confirmation" in stopped.value.message
    assert "OAK-CONFIRM-QUESTION" in stopped.value.message
    held = plane.get_design_case(CASE_ID, tenant_id="local").case
    assert held["status"] == "needs_confirmation"
    assert "oak.community/recreated_from" in held["extensions"]


def test_the_rest_import_route_recreates_a_local_export(tmp_path: Path) -> None:
    from oak.interfaces.api.app import create_app
    from tests.asgi_support import ASGIClient

    exported = _local_export(tmp_path)
    plane = _server(tmp_path)
    headers = {
        "Idempotency-Key": "rest-import-local-export-0001",
        "X-Correlation-ID": "correlation-rest-import",
    }

    with ASGIClient(create_app(control_plane=plane)) as client:
        response = client.post("/v1/design-cases:import", json=exported, headers=headers)
        again = client.post("/v1/design-cases:import", json=exported, headers=headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["case"]["status"] == "ready_for_candidates"
    assert body["case"]["extensions"]["oak.community/recreated_from"]["workspace_id"] == (
        "workspace.fixture"
    )
    assert again.json()["duplicate"] is True
    assert {event["interface_origin"] for event in _events(plane)} == {"import"}


def _drop_intents(exported: dict[str, Any], versions: set[str]) -> None:
    index = exported["manifest"]["artifact_index"]
    dropped = {
        entry["digest"]
        for entry in index
        if entry["kind"] == "system_intent" and entry["version"] in versions
    }
    exported["manifest"]["artifact_index"] = [
        entry for entry in index if entry["digest"] not in dropped
    ]
    exported["objects"] = [item for item in exported["objects"] if item["digest"] not in dropped]


@pytest.mark.parametrize("versions", [{"0.1.0"}, {"0.1.0", "0.1.1"}, {"0.1.1"}])
def test_an_export_whose_intent_chain_was_cut_is_refused(
    tmp_path: Path, versions: set[str]
) -> None:
    """FC-5: a chain missing its first or last versions would replay fewer answers."""

    exported = _local_export(tmp_path)
    _drop_intents(exported, versions)

    _refused_with(_server(tmp_path), exported, "OAK-IMPORT-REPLAY")


def test_a_malformed_object_is_a_stable_refusal_not_an_internal_error(tmp_path: Path) -> None:
    """FC-7: an index entry naming the brief as an intent is refused with a code."""

    exported = _local_export(tmp_path)
    brief = _brief_digest(exported)
    entry = next(
        entry for entry in exported["manifest"]["artifact_index"] if entry["digest"] == brief
    )
    exported["manifest"]["artifact_index"].append(
        {
            **entry,
            "id": "intent.forged",
            "version": "9.9.9",
            "kind": "system_intent",
            "media_type": "application/vnd.oak.system-intent+json",
        }
    )

    _refused_with(_server(tmp_path), exported, "OAK-IMPORT-REPLAY")


def test_a_deeply_nested_object_is_a_stable_refusal_not_an_internal_error(
    tmp_path: Path,
) -> None:
    """A document nested past the interpreter's recursion limit is refused with a code."""

    exported = _local_export(tmp_path)
    content = b'{"a":' + b"[" * 50_000 + b"]" * 50_000 + b"}"
    digest = content_digest(content)
    entry = next(
        entry for entry in exported["manifest"]["artifact_index"] if entry["kind"] == "design_case"
    )
    exported["manifest"]["artifact_index"].append(
        {**entry, "id": "design-case.forged", "digest": digest, "size_bytes": len(content)}
    )
    exported["objects"].append(
        {"digest": digest, "content_base64": base64.b64encode(content).decode("ascii")}
    )
    exported["objects"].sort(key=lambda item: item["digest"])

    _refused_with(_server(tmp_path), exported, "OAK-IMPORT-REPLAY")


def test_an_import_whose_case_moved_on_between_steps_says_so_and_is_not_retriable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first attempt died after creating the case, and a user carried it on before the
    retry: the origin step's version no longer holds, and no retry could pass it."""

    from oak.application.design_case import DesignCaseService

    exported = _local_export(tmp_path)
    plane = _server(tmp_path)

    def died(*_: Any, **__: Any) -> Any:
        raise OAKError("OAK-STORE-UNAVAILABLE", "the store went away", retriable=True)

    with monkeypatch.context() as patched:
        patched.setattr(DesignCaseService, "record_recreation", died)
        with pytest.raises(OAKError) as first:
            plane.import_design_case(exported, context=_context("moved"))
    assert first.value.code == "OAK-IMPORT-REPLAY" and first.value.retriable is True
    created = plane.get_design_case(CASE_ID, tenant_id="local").case
    user = _context("user")
    plane.interpret(CASE_ID, _user_step(user, str(created["version"])))

    with pytest.raises(OAKError) as again:
        plane.import_design_case(exported, context=_context("moved"))

    assert again.value.code == "OAK-IMPORT-REPLAY"
    assert "OAK-EXPECTED-VERSION" in again.value.message
    # The replay itself got only as far as creating the case; the user interpreted it.
    assert "up to draft" in again.value.message
    assert again.value.retriable is False


def test_a_retried_import_returns_what_it_recorded_not_where_the_case_went_since(
    tmp_path: Path,
) -> None:
    """The user generated candidates after the import; the retry returns the import's case,
    which the remote CLI then names, not the user's later one."""

    from oak.application import OperationWorker

    exported = _local_export(tmp_path)
    plane, store = build_file_control_plane(tmp_path / "server")
    first = plane.import_design_case(exported, context=_context("returned"))
    plane.submit_generate_candidates(
        CASE_ID, _user_step(_context("carried-on"), str(first.case["version"]))
    )
    worker = OperationWorker(store, {"generate_candidates": plane.execute_operation})
    assert worker.run_once(worker_id="test-worker", now=NOW, lease_expires_at=LATER) is not None
    later = plane.get_design_case(CASE_ID, tenant_id="local").case
    assert later["version"] != first.case["version"]

    again = plane.import_design_case(exported, context=_context("returned"))

    assert again.duplicate is True
    assert again.case == first.case
    assert again.intent == first.intent


def test_a_restore_records_its_event_under_a_key_of_its_own(tmp_path: Path) -> None:
    """Review W1: the export carries the origin's idempotency records, so the restore's
    event cannot borrow the import's key; it derives one from the key and the export."""

    origin = _server(tmp_path / "origin")
    brief = (ROOT / "examples/briefs/public-manual-qa.yaml").read_bytes()
    origin.create_design_case(
        original_name="public-manual-qa.yaml", content=brief, context=_context("shared")
    )
    exported = origin.export_design_case(CASE_ID, tenant_id="local")
    plane = _server(tmp_path)

    result = plane.import_design_case(exported, context=_context("shared"))

    assert result.duplicate is False
    assert [event["event_type"] for event in _events(plane)] == [
        "case_created",
        "workspace_restored",
    ]
    restore = _events(plane)[-1]
    assert restore["idempotency_key"].startswith("restore:")
    assert restore["idempotency_key"] != _context("shared").idempotency_key


def test_a_restore_interrupted_before_its_event_stays_without_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review W1, what remains: the import and its event are two writes, and a workspace
    left between them cannot be told from this server's own export imported back, so the
    next import answers it as a duplicate and records nothing; the derived key removed the
    natural trigger (an import key the origin had used), and this pins the window."""

    from oak.application.design_case import DesignCaseService

    origin = _server(tmp_path / "origin")
    brief = (ROOT / "examples/briefs/public-manual-qa.yaml").read_bytes()
    origin.create_design_case(
        original_name="public-manual-qa.yaml", content=brief, context=_context("origin")
    )
    exported = origin.export_design_case(CASE_ID, tenant_id="local")
    plane = _server(tmp_path)

    def crash(self: Any, *arguments: Any, **keywords: Any) -> Any:
        raise OSError("the process died after the workspace was written")

    monkeypatch.setattr(DesignCaseService, "record_restore", crash)
    with pytest.raises(OSError):
        plane.import_design_case(exported, context=_context("first-try"))
    assert [event["event_type"] for event in _events(plane)] == ["case_created"]
    monkeypatch.undo()

    again = plane.import_design_case(exported, context=_context("second-try"))

    assert again.duplicate is True
    assert [event["event_type"] for event in _events(plane)] == ["case_created"]


def test_a_repeated_import_answers_with_the_case_the_restore_recorded(tmp_path: Path) -> None:
    """Review W6: like a re-created import's retry, a repeat names the restore's case, not
    where the case went since."""

    origin = _server(tmp_path / "origin")
    brief = (ROOT / "examples/briefs/public-manual-qa.yaml").read_bytes()
    origin.create_design_case(
        original_name="public-manual-qa.yaml", content=brief, context=_context("origin")
    )
    exported = origin.export_design_case(CASE_ID, tenant_id="local")
    plane = _server(tmp_path)
    restored = plane.import_design_case(exported, context=_context("restore")).case
    assert restored["version"] == "0.1.1"
    moved = plane.interpret(CASE_ID, _user_step(_context("moved"), "0.1.1")).case
    assert moved["version"] == "0.1.2"

    again = plane.import_design_case(exported, context=_context("again"))

    assert again.duplicate is True
    assert again.case == restored
    assert plane.get_design_case(CASE_ID, tenant_id="local").case["version"] == "0.1.2"


def test_the_recorded_origin_comes_from_the_manifest_not_the_case_document(
    tmp_path: Path,
) -> None:
    """A-2: the case document is not schema-validated, so none of its text is recorded."""

    exported = _local_export(tmp_path)
    reference = exported["manifest"]["current_case_ref"]
    objects = _objects(exported)
    item = objects[reference["digest"]]
    document = json.loads(base64.b64decode(item["content_base64"]))
    document["version"] = "‮forged\x00"
    content = canonical_json_bytes(document)
    digest = content_digest(content)
    exported["objects"].remove(item)
    exported["objects"].append(
        {"digest": digest, "content_base64": base64.b64encode(content).decode("ascii")}
    )
    for entry in exported["manifest"]["artifact_index"]:
        if entry["digest"] == reference["digest"]:
            entry["digest"] = digest
    reference["digest"] = digest

    case = _server(tmp_path).import_design_case(exported, context=_context("origin")).case

    origin = case["extensions"]["oak.community/recreated_from"]
    assert origin["case_version"] == reference["version"]
    assert origin["case_digest"] == digest
    assert "forged" not in json.dumps(case)


def test_a_local_export_relabelled_as_a_server_one_brings_no_authority(tmp_path: Path) -> None:
    """FC-6: the restore-or-re-create choice rests on `manifest.id`, which no digest covers,
    so the restore path refuses what only a local workspace writes."""

    exported = _local_export(tmp_path, compiled=True)
    exported["manifest"]["id"] = "workspace.public-manual-qa"

    _refused_with(_server(tmp_path), exported, "OAK-IMPORT-AUTHORITY")


def test_a_local_export_is_recreated_on_the_postgresql_store(
    tmp_path: Path,
    persistent_control_plane: Any,  # noqa: F811 (the fixture, imported above)
) -> None:
    """Review H-F3: the server a user runs keeps its cases in PostgreSQL."""

    plane, _ = persistent_control_plane
    exported = _local_export(tmp_path, compiled=True)

    result = plane.import_design_case(exported, context=_context("postgresql"))
    again = plane.import_design_case(exported, context=_context("postgresql"))

    assert result.case["status"] == "ready_for_candidates"
    assert result.case.get("runner_plan_ref") is None
    assert again.duplicate is True and again.case["version"] == result.case["version"]
    assert [event["event_type"] for event in _events(plane)] == [
        "case_created",
        "workspace_imported",
        "brief_interpreted",
        "claims_confirmed",
    ]


def test_the_remote_cli_says_it_recreated_the_case(tmp_path: Path) -> None:
    """Review H-F3: `oak --server import` names what it did, through a real server."""

    from oak.interfaces.cli.main import app as cli_app
    from tests.integration.test_remote_cli import _LiveServer, runner

    _local_export(tmp_path)
    server = _LiveServer(tmp_path / "live")
    server.start()
    try:
        result = runner.invoke(
            cli_app, ["--server", server.url, "import", str(tmp_path / "export")]
        )
    finally:
        server.stop()

    assert result.exit_code == 0, result.output
    assert f"Re-created {CASE_ID}@" in result.output
    assert "from workspace.fixture" in result.output


def test_the_remote_cli_says_it_imported_a_server_export_of_a_recreated_case(
    tmp_path: Path,
) -> None:
    """A case re-created on one server and exported from it is restored as itself on the
    next, with the origin it already carried: that is an import, not a re-creation."""

    from oak.interfaces.cli.main import app as cli_app
    from oak.interfaces.cli.remote import write_export_directory
    from tests.integration.test_remote_cli import _LiveServer, runner

    first = _server(tmp_path / "first")
    first.import_design_case(_local_export(tmp_path), context=_context("first-server"))
    write_export_directory(
        tmp_path / "server-export", first.export_design_case(CASE_ID, tenant_id="local")
    )
    server = _LiveServer(tmp_path / "live")
    server.start()
    try:
        result = runner.invoke(
            cli_app, ["--server", server.url, "import", str(tmp_path / "server-export")]
        )
    finally:
        server.stop()

    assert result.exit_code == 0, result.output
    assert f"Imported {CASE_ID}@" in result.output
    assert "Re-created" not in result.output
