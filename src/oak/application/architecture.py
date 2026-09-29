# SPDX-License-Identifier: Apache-2.0
"""The chosen architecture as one portable document — a place a user may stop.

A read of documents the case already holds: the candidate (the selected one unless
another is named), the owner's decision when one is recorded, and — once the case is
compiled for a target that can install — the node-to-image map and whether the two
approvals an install needs exist. Producing it compiles, signs, approves and installs
nothing, and it publishes no case successor and no audit event.
"""

from __future__ import annotations

from typing import Any

from oak.domain import OAKError

NOTICE = (
    "Read from the design case. Producing this compiled, signed, approved and installed "
    "nothing; a user who wants only the architecture can stop here."
)
INSTALL_APPROVALS = ("architecture", "apply")


def select_candidate_reference(case: dict[str, Any], candidate_id: str | None) -> dict[str, Any]:
    """The reference of the named candidate, or of the selected one when none is named."""

    if candidate_id is None:
        selected = case.get("selected_candidate_ref")
        if not isinstance(selected, dict):
            raise OAKError(
                "OAK-ARCHITECTURE-UNSELECTED",
                "no candidate is selected yet; name one, for example `oak architecture "
                "candidate-03`",
            )
        return selected
    for reference in case.get("candidate_refs", []):
        if isinstance(reference, dict) and reference.get("id") == candidate_id:
            return reference
    raise OAKError("OAK-CANDIDATE-NOT-FOUND", "candidate is not part of this design case")


def architecture_document(
    *,
    case: dict[str, Any],
    candidate: dict[str, Any],
    decision: dict[str, Any] | None,
    plan: dict[str, Any] | None,
    approvals: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    selected = case.get("selected_candidate_ref")
    is_selected = isinstance(selected, dict) and selected.get("id") == candidate.get("id")
    return {
        "architecture": {
            "case": {
                "id": case["id"],
                "version": case["version"],
                "status": case["status"],
                "title": case.get("title"),
            },
            "selected": is_selected,
            "candidate": candidate,
            "decision": decision if is_selected else None,
            "installation": _installation(plan, approvals) if is_selected else None,
            "notice": NOTICE,
        }
    }


def _installation(
    plan: dict[str, Any] | None, approvals: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    if plan is None:
        return None
    apply = next((item for item in plan["operations"] if item["kind"] == "apply"), None)
    if apply is None:
        return None
    parameters = apply["parameters"]
    return {
        "target_id": plan["target"]["id"],
        "isolation": parameters["isolation"],
        "starts_containers": parameters["isolation"] == "network-none-started-hardened",
        "containers": [
            {
                "node_id": entry["node_id"],
                "manifest_id": entry["manifest_id"],
                "container_name": entry["container_name"],
                "image": f"{entry['image_reference']}@{entry['image_digest']}",
            }
            for entry in parameters["containers"]
        ],
        "approvals": {
            action: (
                "absent"
                if action not in approvals
                else "revoked"
                if approvals[action].get("revoked") is True
                else "recorded"
            )
            for action in INSTALL_APPROVALS
        },
    }


def architecture_human(document: dict[str, Any]) -> str:
    architecture = document["architecture"]
    candidate = architecture["candidate"]
    variant = candidate.get("variant") or candidate.get("extensions", {}).get(
        "oak.community/pattern_variant"
    )
    header = f"{candidate['id']} ({variant}) in {architecture['case']['id']}"
    decision = architecture.get("decision")
    if decision:
        header += f" — selected by {decision['owner']}"
    elif not architecture["selected"]:
        header += " — not the selected candidate"
    lines = [header, "", "Nodes:"]
    for node in candidate["topology"]["nodes"]:
        component = node.get("component_ref") or "no component"
        lines.append(f"  {node['id']:<24} {node['role']} -> {component}")
    edges = candidate["topology"].get("edges", [])
    if edges:
        lines += ["", "Edges:"]
        lines += [f"  {edge['from']} -> {edge['to']} ({edge['interface']})" for edge in edges]
    lines += ["", "Predictions (value [lower, upper] unit):"]
    for objective in candidate.get("objectives", []):
        interval = (
            f" [{objective.get('lower')}, {objective.get('upper')}]"
            if objective.get("lower") is not None and objective.get("upper") is not None
            else ""
        )
        lines.append(
            f"  {objective['name']:<24} {objective['value']}{interval} {objective['unit']}"
        )
    installation = architecture.get("installation")
    if installation:
        starts = "starts containers" if installation["starts_containers"] else "never starts them"
        lines += ["", f"Would install on {installation['target_id']} ({starts}):"]
        lines += [f"  {item['node_id']:<24} {item['image']}" for item in installation["containers"]]
        approvals = ", ".join(
            f"{action} {state}" for action, state in installation["approvals"].items()
        )
        lines += [f"Approvals needed before any install: {approvals}"]
    lines += ["", architecture["notice"]]
    return "\n".join(lines)
