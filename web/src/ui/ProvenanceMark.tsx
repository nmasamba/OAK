// SPDX-License-Identifier: Apache-2.0
import type { ClaimClass } from "../claims";

/**
 * Where a value came from, as a shape and a word: a filled square for a fact from the
 * brief, a ring for an inference, a triangle for a domain default, a diamond for a
 * model's proposal, a dashed square for an unknown, a half square for a reviewer's
 * correction. The word stays beside the shape; the e2e pins read the word.
 */
export function ProvenanceMark({
  claimClass,
  word,
  className,
}: {
  readonly claimClass: ClaimClass;
  readonly word: string;
  readonly className?: string;
}) {
  const classes = ["prov", `prov-${claimClass}`, className]
    .filter(Boolean)
    .join(" ");
  return (
    <span className={classes}>
      <span className="prov-shape" aria-hidden="true" />
      <span className="prov-word">{word}</span>
    </span>
  );
}
