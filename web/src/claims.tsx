// SPDX-License-Identifier: Apache-2.0
import type { JsonObject } from "./generated/api";
import { asString } from "./support";

export type ClaimClass =
  | "fact"
  | "correction"
  | "inference"
  | "default"
  | "unknown";

const SOURCE_CLASSES: Record<string, ClaimClass> = {
  explicit: "fact",
  user_correction: "correction",
  inferred_from_brief: "inference",
  domain_default: "default",
};

const CLASS_LABELS: Record<ClaimClass, string> = {
  fact: "Fact from brief",
  correction: "Corrected by reviewer",
  inference: "Inference",
  default: "Domain default",
  unknown: "Unknown",
};

export function claimClassForSource(source: string | null): ClaimClass {
  if (source === null) {
    return "unknown";
  }
  return SOURCE_CLASSES[source] ?? "unknown";
}

export function ClaimBadge({
  claimClass,
}: {
  readonly claimClass: ClaimClass;
}) {
  return (
    <span className={`badge claim-${claimClass}`}>
      {CLASS_LABELS[claimClass]}
    </span>
  );
}

export function MaterialityBadge({
  materiality,
}: {
  readonly materiality: string | null;
}) {
  if (materiality === null) {
    return null;
  }
  return (
    <span className={`badge materiality-${materiality}`}>{materiality}</span>
  );
}

export function provenanceSource(entry: JsonObject): string | null {
  return asString(entry["source"]);
}
