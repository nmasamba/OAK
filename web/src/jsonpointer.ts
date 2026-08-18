// SPDX-License-Identifier: Apache-2.0

export function resolvePointer(document: unknown, pointer: string): unknown {
  if (pointer === "") {
    return document;
  }
  if (!pointer.startsWith("/")) {
    return undefined;
  }
  let current: unknown = document;
  for (const raw of pointer.slice(1).split("/")) {
    const token = raw.replaceAll("~1", "/").replaceAll("~0", "~");
    if (Array.isArray(current)) {
      const index = Number(token);
      current = Number.isInteger(index) ? current[index] : undefined;
    } else if (typeof current === "object" && current !== null) {
      current = (current as Record<string, unknown>)[token];
    } else {
      return undefined;
    }
  }
  return current;
}

export function formatValue(value: unknown): string {
  if (value === undefined) {
    return "(not set)";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value, null, 1);
}
