// SPDX-License-Identifier: Apache-2.0

/**
 * The one place a candidate's variant id becomes words. The ids are canonical schema
 * values and never change here; what the page shows is the owner's vocabulary. Raw ids
 * are never rendered, not in a tooltip and not in the table view (Sprint 12 copy rules).
 */
import type { JsonObject } from "../generated/api";

const VARIANT_LABELS: Readonly<Record<string, string>> = {
  simpler_baseline: "Baseline",
  minimum_sufficient: "Minimal",
  balanced_enterprise: "Balanced",
  high_assurance_sovereign: "High assurance",
};

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

/**
 * A candidate's variant id: the pattern variant the compiler records in its extensions
 * (`simpler_baseline`, `balanced_enterprise`, ...), or the coarser canonical `variant`
 * field when the extension is absent.
 */
export function candidateVariantId(candidate: JsonObject): string | null {
  const extensions = candidate["extensions"];
  const pattern =
    typeof extensions === "object" &&
    extensions !== null &&
    !Array.isArray(extensions)
      ? (extensions as JsonObject)["oak.community/pattern_variant"]
      : undefined;
  if (typeof pattern === "string") {
    return pattern;
  }
  const variant = candidate["variant"];
  return typeof variant === "string" ? variant : null;
}

export function candidateLabel(candidate: JsonObject): string {
  return variantLabel(candidateVariantId(candidate));
}
