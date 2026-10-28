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
from tests.mcp_support import build_file_control_plane
from tests.runner_support import ROOT, build_compiled_case

pytestmark = pytest.mark.integration

NOW = "2026-10-28T12:00:00Z"
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
    """The server-shaped path is unchanged: its identity is the server's, so it is restored."""

    origin = _server(tmp_path / "origin")
    brief = (ROOT / "examples/briefs/public-manual-qa.yaml").read_bytes()
    origin.create_design_case(
        original_name="public-manual-qa.yaml", content=brief, context=_context("origin")
    )
    exported = origin.export_design_case(CASE_ID, tenant_id="local")
    plane = _server(tmp_path)

    case = plane.import_design_case(exported, context=_context("server-shaped")).case

    assert "oak.community/recreated_from" not in case["extensions"]
    assert [event["event_type"] for event in _events(plane)] == ["case_created"]


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
