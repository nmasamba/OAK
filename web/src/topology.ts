// SPDX-License-Identifier: Apache-2.0
/**
 * A candidate's topology laid out for drawing: nodes in columns by dependency order,
 * edges between them, and one sentence that says what the picture says. The page draws
 * it as SVG; the download serialises the same layout to a file.
 */
import type { JsonObject } from "./generated/api";
import { asArray, asObject, asString } from "./support";

export interface LaidOutNode {
  readonly id: string;
  readonly role: string;
  readonly component: string | null;
  readonly x: number;
  readonly y: number;
}

export interface LaidOutEdge {
  readonly from: string;
  readonly to: string;
  readonly label: string;
  readonly x1: number;
  readonly y1: number;
  readonly x2: number;
  readonly y2: number;
}

export interface TopologyLayout {
  readonly nodes: readonly LaidOutNode[];
  readonly edges: readonly LaidOutEdge[];
  readonly width: number;
  readonly height: number;
  readonly description: string;
}

export const NODE_WIDTH = 200;
export const NODE_HEIGHT = 72;
const COLUMN_GAP = 96;
const ROW_GAP = 28;
const MARGIN = 24;

/** Columns by longest path from a source; a cycle or an unknown edge end falls back to list order. */
function columnsOf(
  ids: readonly string[],
  edges: readonly { readonly from: string; readonly to: string }[],
): ReadonlyMap<string, number> {
  const column = new Map<string, number>(ids.map((id) => [id, 0]));
  for (let pass = 0; pass < ids.length; pass += 1) {
    let changed = false;
    for (const edge of edges) {
      const from = column.get(edge.from);
      const to = column.get(edge.to);
      if (from === undefined || to === undefined) {
        continue;
      }
      if (to <= from && from + 1 < ids.length) {
        column.set(edge.to, from + 1);
        changed = true;
      }
    }
    if (!changed) {
      break;
    }
  }
  return column;
}

export function layoutTopology(topology: unknown): TopologyLayout {
  const document = asObject(topology) ?? {};
  const rawNodes = asArray(document["nodes"])
    .map(asObject)
    .filter((entry): entry is JsonObject => entry !== null);
  const rawEdges = asArray(document["edges"])
    .map(asObject)
    .filter((entry): entry is JsonObject => entry !== null);
  const ids = rawNodes
    .map((node) => asString(node["id"]))
    .filter((id): id is string => id !== null);
  const edges = rawEdges
    .map((edge) => ({
      from: asString(edge["from"]) ?? "",
      to: asString(edge["to"]) ?? "",
      label: asString(edge["interface"]) ?? "",
    }))
    .filter((edge) => ids.includes(edge.from) && ids.includes(edge.to));
  const column = columnsOf(ids, edges);
  const rows = new Map<number, number>();
  const placed = new Map<string, LaidOutNode>();
  for (const node of rawNodes) {
    const id = asString(node["id"]);
    if (id === null) {
      continue;
    }
    const col = column.get(id) ?? 0;
    const row = rows.get(col) ?? 0;
    rows.set(col, row + 1);
    placed.set(id, {
      id,
      role: asString(node["role"]) ?? id,
      component: asString(node["component_ref"]),
      x: MARGIN + col * (NODE_WIDTH + COLUMN_GAP),
      y: MARGIN + row * (NODE_HEIGHT + ROW_GAP),
    });
  }
  const nodes = [...placed.values()];
  const laidEdges: LaidOutEdge[] = [];
  for (const edge of edges) {
    const from = placed.get(edge.from);
    const to = placed.get(edge.to);
    if (from === undefined || to === undefined) {
      continue;
    }
    const forward = to.x >= from.x;
    laidEdges.push({
      ...edge,
      x1: forward ? from.x + NODE_WIDTH : from.x,
      y1: from.y + NODE_HEIGHT / 2,
      x2: forward ? to.x : to.x + NODE_WIDTH,
      y2: to.y + NODE_HEIGHT / 2,
    });
  }
  const columns = Math.max(
    1,
    ...nodes.map((node) => (column.get(node.id) ?? 0) + 1),
  );
  const deepest = Math.max(1, ...rows.values());
  const sentences = laidEdges.map((edge) => {
    const from = placed.get(edge.from)?.role ?? edge.from;
    const to = placed.get(edge.to)?.role ?? edge.to;
    return edge.label === ""
      ? `${from} feeds ${to}`
      : `${from} feeds ${to} over ${edge.label}`;
  });
  const description =
    nodes.length === 0
      ? "No nodes."
      : sentences.length === 0
        ? `${nodes.length} node${nodes.length === 1 ? "" : "s"}: ${nodes.map((node) => node.role).join(", ")}.`
        : `${sentences.join("; ")}. The table lists the same.`;
  return {
    nodes,
    edges: laidEdges,
    width: MARGIN * 2 + columns * NODE_WIDTH + (columns - 1) * COLUMN_GAP,
    height: MARGIN * 2 + deepest * NODE_HEIGHT + (deepest - 1) * ROW_GAP,
    description,
  };
}
