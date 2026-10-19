# SPDX-License-Identifier: Apache-2.0
"""A candidate's topology laid out exactly as `web/src/topology.ts` lays it out.

Nodes go in columns by longest path from a source, edges join their sides, and one
sentence says what the picture says. The report draws this layout in both files and the
workspace draws the TypeScript one; a contract test runs both on the reference candidate
and compares every coordinate.
"""

from __future__ import annotations

from typing import Any

NODE_WIDTH = 200
NODE_HEIGHT = 72
COLUMN_GAP = 96
ROW_GAP = 28
MARGIN = 24


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _columns(ids: list[str], edges: list[dict[str, str]]) -> dict[str, int]:
    column = dict.fromkeys(ids, 0)
    for _ in range(len(ids)):
        changed = False
        for edge in edges:
            source = column.get(edge["from"])
            target = column.get(edge["to"])
            if source is None or target is None:
                continue
            if target <= source and source + 1 < len(ids):
                column[edge["to"]] = source + 1
                changed = True
        if not changed:
            break
    return column


def layout_topology(topology: Any) -> dict[str, Any]:
    document = topology if isinstance(topology, dict) else {}
    raw_nodes = [node for node in document.get("nodes", []) or [] if isinstance(node, dict)]
    raw_edges = [edge for edge in document.get("edges", []) or [] if isinstance(edge, dict)]
    ids = [identifier for node in raw_nodes if (identifier := _text(node.get("id"))) is not None]
    edges = [
        {
            "from": _text(edge.get("from")) or "",
            "to": _text(edge.get("to")) or "",
            "label": _text(edge.get("interface")) or "",
        }
        for edge in raw_edges
    ]
    edges = [edge for edge in edges if edge["from"] in ids and edge["to"] in ids]
    column = _columns(ids, edges)
    rows: dict[int, int] = {}
    placed: dict[str, dict[str, Any]] = {}
    for node in raw_nodes:
        identifier = _text(node.get("id"))
        if identifier is None:
            continue
        col = column.get(identifier, 0)
        row = rows.get(col, 0)
        rows[col] = row + 1
        placed[identifier] = {
            "id": identifier,
            "role": _text(node.get("role")) or identifier,
            "component": _text(node.get("component_ref")),
            "x": MARGIN + col * (NODE_WIDTH + COLUMN_GAP),
            "y": MARGIN + row * (NODE_HEIGHT + ROW_GAP),
        }
    nodes = list(placed.values())
    laid_edges: list[dict[str, Any]] = []
    for edge in edges:
        source = placed.get(edge["from"])
        target = placed.get(edge["to"])
        if source is None or target is None:
            continue
        forward = target["x"] >= source["x"]
        laid_edges.append(
            {
                **edge,
                "x1": source["x"] + NODE_WIDTH if forward else source["x"],
                "y1": source["y"] + NODE_HEIGHT // 2,
                "x2": target["x"] if forward else target["x"] + NODE_WIDTH,
                "y2": target["y"] + NODE_HEIGHT // 2,
            }
        )
    columns = max([1, *[column.get(node["id"], 0) + 1 for node in nodes]])
    deepest = max([1, *rows.values()])
    sentences = []
    for edge in laid_edges:
        source_role = placed[edge["from"]]["role"]
        target_role = placed[edge["to"]]["role"]
        sentences.append(
            f"{source_role} feeds {target_role}"
            if edge["label"] == ""
            else f"{source_role} feeds {target_role} over {edge['label']}"
        )
    if not nodes:
        description = "No nodes."
    elif not sentences:
        plural = "" if len(nodes) == 1 else "s"
        roles = ", ".join(node["role"] for node in nodes)
        description = f"{len(nodes)} node{plural}: {roles}."
    else:
        description = f"{'; '.join(sentences)}. The table lists the same."
    return {
        "nodes": nodes,
        "edges": laid_edges,
        "width": MARGIN * 2 + columns * NODE_WIDTH + (columns - 1) * COLUMN_GAP,
        "height": MARGIN * 2 + deepest * NODE_HEIGHT + (deepest - 1) * ROW_GAP,
        "description": description,
    }
