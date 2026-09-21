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

/**
 * A short age for an ISO timestamp — "just now", "5 min ago", "3 h ago", "2 d ago" — so a
 * verdict or a catalogue read is never mistaken for current. Unparsable input comes back as
 * given rather than as a guess.
 */
export function ageOf(iso: string, now: number = Date.now()): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) {
    return iso;
  }
  const seconds = Math.max(0, Math.round((now - then) / 1000));
  if (seconds < 60) {
    return "just now";
  }
  if (seconds < 3600) {
    return `${Math.round(seconds / 60)} min ago`;
  }
  if (seconds < 86400) {
    return `${Math.round(seconds / 3600)} h ago`;
  }
  return `${Math.round(seconds / 86400)} d ago`;
}
