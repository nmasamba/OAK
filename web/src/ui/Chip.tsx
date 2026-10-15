// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";

import { Icon, type IconName } from "./Icon";

export type ChipTone = "neutral" | "brass" | "ok" | "info" | "bad" | "unknown";

type RemoveProps =
  | { readonly onRemove?: undefined; readonly removeLabel?: undefined }
  | {
      /** Shows a remove control; its accessible name is `removeLabel`. */
      readonly onRemove: () => void;
      readonly removeLabel: string;
    };

/**
 * A pill with a glyph and a few words: an attached brief (name · size · remove), a
 * download's state, a prediction, a status. `small` is the inline size for a status
 * word beside text; the default is a 44px touch target.
 */
export function Chip({
  tone = "neutral",
  icon,
  mono = false,
  small = false,
  title,
  className,
  children,
  onRemove,
  removeLabel,
}: RemoveProps & {
  readonly tone?: ChipTone;
  readonly icon?: IconName;
  readonly mono?: boolean;
  readonly small?: boolean;
  readonly title?: string;
  readonly className?: string;
  readonly children: ReactNode;
}) {
  const classes = [
    "chip",
    `chip-${tone}`,
    mono ? "chip-mono" : null,
    small ? "chip-small" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <span className={classes} title={title}>
      {icon === undefined ? null : <Icon name={icon} size={small ? 14 : 16} />}
      <span className="chip-label">{children}</span>
      {onRemove === undefined ? null : (
        <button
          type="button"
          className="chip-remove"
          onClick={onRemove}
          aria-label={removeLabel}
        >
          <Icon name="close" size={14} />
        </button>
      )}
    </span>
  );
}
