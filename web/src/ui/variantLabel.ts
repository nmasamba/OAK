// SPDX-License-Identifier: Apache-2.0

/**
 * The one place a candidate's variant id becomes words. The ids are canonical schema
 * values and never change here; what the page shows is the owner's vocabulary. Raw ids
 * are never rendered, not in a tooltip and not in the table view (Sprint 12 copy rules).
 *
 * A researched design (ADR-0018) keeps its pattern's variant, so the bare map would say
 * "Balanced" twice; its label is the pattern label plus the one closed suffix,
 * "Balanced, new". The suffix is mirrored in `src/oak/application/report/labels.py` and
 * an agreement test holds the two equal. A label is never built from a model or
 * repository name.
 */
import type { JsonObject } from "../generated/api";

const VARIANT_LABELS: Readonly<Record<string, string>> = {
  simpler_baseline: "Baseline",
  minimum_sufficient: "Minimal",
  balanced_enterprise: "Balanced",
  high_assurance_sovereign: "High assurance",
};

export const RESEARCHED_SUFFIX = "new";
const RESEARCH_EXTENSION = "oak.community/research";

/** "Baseline" for `simpler_baseline`; any other id humanised ("some_new_kind" → "Some new kind"). */
export function variantLabel(variantId: string | null): string {
  if (variantId === null || variantId === "") {
    return "Unknown";
  }
  const known = VARIANT_LABELS[variantId];
  if (known !== undefined) {
    return known;
  }
  const words = variantId.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function extensionsOf(candidate: JsonObject): JsonObject {
  const extensions = candidate["extensions"];
  return typeof extensions === "object" &&
    extensions !== null &&
    !Array.isArray(extensions)
    ? (extensions as JsonObject)
    : {};
}

/**
 * A candidate's variant id: the pattern variant the compiler records in its extensions
 * (`simpler_baseline`, `balanced_enterprise`, ...), or the coarser canonical `variant`
 * field when the extension is absent.
 */
export function candidateVariantId(candidate: JsonObject): string | null {
  const pattern = extensionsOf(candidate)["oak.community/pattern_variant"];
  if (typeof pattern === "string") {
    return pattern;
  }
  const variant = candidate["variant"];
  return typeof variant === "string" ? variant : null;
}

/** True for a design the compiler built from a research snapshot. */
export function isResearched(candidate: JsonObject): boolean {
  const research = extensionsOf(candidate)[RESEARCH_EXTENSION];
  return (
    typeof research === "object" &&
    research !== null &&
    !Array.isArray(research)
  );
}

/** Only the curated baseline is a baseline; a researched design never is. */
export function isBaseline(candidate: JsonObject): boolean {
  return (
    !isResearched(candidate) &&
    candidateVariantId(candidate) === "simpler_baseline"
  );
}

export function candidateLabel(candidate: JsonObject): string {
  const label = variantLabel(candidateVariantId(candidate));
  return isResearched(candidate) ? `${label}, ${RESEARCHED_SUFFIX}` : label;
}
