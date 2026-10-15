// SPDX-License-Identifier: Apache-2.0
/**
 * The one place a candidate's variant id becomes words. The ids are canonical schema
 * values and never change here; what the page shows is the owner's vocabulary. Raw ids
 * are never rendered, not in a tooltip and not in the table view (Sprint 12 copy rules).
 */
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
