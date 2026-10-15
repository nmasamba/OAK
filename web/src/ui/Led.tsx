// SPDX-License-Identifier: Apache-2.0
export type LedState =
  | "absent"
  | "current"
  | "ok"
  | "expired"
  | "revoked"
  | "failed"
  | "busy"
  | "unknown";

/**
 * A status light with its word. The shapes differ, not only the colours: a ring for
 * absent, a lit dot for current and ok, a half dot for expired, a cross for revoked and
 * failed, a dashed ring for unknown, a turning arc for busy. The word is always visible.
 */
export function Led({
  state,
  word,
  className,
}: {
  readonly state: LedState;
  readonly word: string;
  readonly className?: string;
}) {
  const classes = ["led", `led-${state}`, className].filter(Boolean).join(" ");
  return (
    <span className={classes}>
      <span className="led-light" aria-hidden="true" />
      <span className="led-word mono">{word}</span>
    </span>
  );
}
