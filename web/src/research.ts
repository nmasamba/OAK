// SPDX-License-Identifier: Apache-2.0
/**
 * The words research shows: an evidence class beside every claim, a tier, a verdict and
 * a source. `EVIDENCE_WORDS` mirrors `oak.domain.research.EVIDENCE_WORDS` and a contract
 * test holds the pair equal (Sprint 14, ADR-0018). The researched label suffix lives
 * with the other labels in `ui/variantLabel.ts`.
 */
import type { JsonObject } from "./generated/api";
import { asArray, asObject, asString } from "./support";

export const EVIDENCE_WORDS: Readonly<Record<string, string>> = {
  served_by_live_route: "Live route",
  published_release: "Published release",
  published_by_source: "Published by source",
  measured_by_source: "Measured by source",
  claimed_by_model_card: "Claimed by model card",
  claimed_by_release_notes: "Claimed by release notes",
  unverified: "Unverified",
};

export const TIER_WORDS: Readonly<Record<string, string>> = {
  trusted: "Trusted source",
  unvetted: "Unvetted",
};

export const VERDICT_WORDS: Readonly<Record<string, string>> = {
  passed: "Passed the gates",
  needs_review: "Needs your review",
  failed: "Did not pass",
};

/** Where a researched item came from; the fixture source is named as synthetic. */
export const SOURCE_WORDS: Readonly<Record<string, string>> = {
  huggingface_hub: "Hugging Face Hub",
  huggingface_router: "Hugging Face router",
  github: "GitHub",
  fixture: "Fixture (synthetic)",
};

export const KIND_WORDS: Readonly<Record<string, string>> = {
  model: "Model",
  serving_runtime: "Serving runtime",
  agent_framework: "Agent framework",
  retrieval_engine: "Retrieval engine",
};

export function sourceWord(source: string | null): string {
  return source === null ? "Unknown source" : (SOURCE_WORDS[source] ?? source);
}

export function kindWord(kind: string | null): string {
  return kind === null ? "Component" : (KIND_WORDS[kind] ?? kind);
}

/** The date part of a timestamp, or an em dash when the source published none. */
export function dateWord(timestamp: string | null): string {
  return timestamp === null || timestamp.length < 10
    ? "—"
    : timestamp.slice(0, 10);
}

/**
 * The verdict a review changed: an accepted item passes, a rejected one fails, and an
 * item nobody reviewed keeps the verdict the gates gave it.
 */
export function effectiveVerdict(
  item: JsonObject,
  reviews: readonly JsonObject[],
): { readonly verdict: string; readonly reviewed: boolean } {
  const verdict = asString(item["verdict"]) ?? "failed";
  const itemId = asString(item["id"]);
  if (verdict !== "needs_review" || itemId === null) {
    return { verdict, reviewed: false };
  }
  for (const review of reviews) {
    if (asString(review["item_id"]) === itemId) {
      return {
        verdict:
          asString(review["decision"]) === "accept" ? "passed" : "failed",
        reviewed: true,
      };
    }
  }
  return { verdict, reviewed: false };
}

export const RESEARCH_EXTENSION = "oak.community/research";
export const COMPARISON_EXTENSION = "oak.community/comparison";
export const RESEARCH_SNAPSHOT_REF = "oak.community/research_snapshot_ref";
export const RESEARCH_REVIEW_REFS = "oak.community/research_review_refs";

export function evidenceWord(evidenceClass: string | null): string {
  if (evidenceClass === null) {
    return EVIDENCE_WORDS["unverified"] ?? "Unverified";
  }
  return (
    EVIDENCE_WORDS[evidenceClass] ??
    EVIDENCE_WORDS["unverified"] ??
    "Unverified"
  );
}

/** The research extension a researched design carries, or null for a curated one. */
export function researchOf(candidate: JsonObject): JsonObject | null {
  return asObject(
    (asObject(candidate["extensions"]) ?? {})[RESEARCH_EXTENSION],
  );
}

export function comparisonOf(candidate: JsonObject): JsonObject | null {
  return asObject(
    (asObject(candidate["extensions"]) ?? {})[COMPARISON_EXTENSION],
  );
}

function constraintWords(ids: readonly unknown[]): string {
  return ids
    .map((id) => asString(id))
    .filter((id): id is string => id !== null)
    .map((id) => id.replace(/^constraint\./, "").replaceAll("-", " "))
    .join(", ");
}

/**
 * Why a researched design cannot be selected in this release, in plain words, from its typed
 * comparison: the reviews still pending and the values no source published.
 */
export function whyNotSelectable(candidate: JsonObject): string | null {
  const comparison = comparisonOf(candidate);
  if (comparison === null) {
    return null;
  }
  const pending = constraintWords(asArray(comparison["pending_review"]));
  const unknown = constraintWords(asArray(comparison["unknown_value"]));
  const failed = constraintWords(asArray(comparison["failed"]));
  const parts: string[] = [];
  if (pending !== "") {
    parts.push(`${pending} review pending`);
  }
  if (unknown !== "") {
    parts.push(`${unknown} not published by the source`);
  }
  if (failed !== "") {
    parts.push(`${failed} failed`);
  }
  const compared =
    comparison["comparable"] === true
      ? "Compared with the other designs, never selectable in this release"
      : "Not compared, and never selectable in this release";
  return parts.length === 0
    ? `${compared}.`
    : `${compared}: ${parts.join("; ")}.`;
}
