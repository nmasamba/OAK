// SPDX-License-Identifier: Apache-2.0

export interface DiffRow {
  readonly pointer: string;
  readonly kind: "added" | "removed" | "changed";
  readonly before: string | null;
  readonly after: string | null;
}

function flatten(
  value: unknown,
  pointer: string,
  into: Map<string, string>,
): void {
  if (Array.isArray(value)) {
    value.forEach((entry, index) => {
      flatten(entry, `${pointer}/${index}`, into);
    });
    return;
  }
  if (typeof value === "object" && value !== null) {
    for (const [key, entry] of Object.entries(value)) {
      const token = key.replaceAll("~", "~0").replaceAll("/", "~1");
      flatten(entry, `${pointer}/${token}`, into);
    }
    return;
  }
  into.set(pointer === "" ? "/" : pointer, JSON.stringify(value));
}

export function semanticDiff(before: unknown, after: unknown): DiffRow[] {
  const beforeMap = new Map<string, string>();
  const afterMap = new Map<string, string>();
  flatten(before, "", beforeMap);
  flatten(after, "", afterMap);
  const pointers = [
    ...new Set([...beforeMap.keys(), ...afterMap.keys()]),
  ].sort();
  const rows: DiffRow[] = [];
  for (const pointer of pointers) {
    const previous = beforeMap.get(pointer) ?? null;
    const next = afterMap.get(pointer) ?? null;
    if (previous === next) {
      continue;
    }
    rows.push({
      pointer,
      kind: previous === null ? "added" : next === null ? "removed" : "changed",
      before: previous,
      after: next,
    });
  }
  return rows;
}
