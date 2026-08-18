// SPDX-License-Identifier: Apache-2.0
import type { JsonObject } from "./generated/api";

export function newIdempotencyKey(step: string): string {
  return `web-${step}-${crypto.randomUUID()}`;
}

export function etagFor(version: string): string {
  return `"${version}"`;
}

export function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

export function asNumber(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

export function asObject(value: unknown): JsonObject | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as JsonObject)
    : null;
}

export function asArray(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? value : [];
}

export function caseField(caseDocument: JsonObject, key: string): unknown {
  return caseDocument[key];
}
