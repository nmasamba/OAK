// SPDX-License-Identifier: Apache-2.0
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { Icon, type IconName } from "./Icon";

export type KeycapTone = "brass" | "quiet" | "danger";

/**
 * A button that presses. Brass is the one thing to press on a screen; quiet is every
 * other control; danger is a cancel. A busy keycap is disabled, says so with
 * `aria-busy`, and shows its busy label in place of its label so the name on screen
 * still tells the truth.
 */
export function Keycap({
  tone = "brass",
  icon,
  busy = false,
  busyLabel,
  children,
  className,
  disabled,
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  readonly tone?: KeycapTone;
  readonly icon?: IconName;
  readonly busy?: boolean;
  readonly busyLabel?: string;
  readonly children?: ReactNode;
}) {
  const classes = [
    "keycap",
    `keycap-${tone}`,
    busy ? "keycap-busy" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <button
      {...rest}
      type={type}
      className={classes}
      disabled={disabled === true || busy}
      aria-busy={busy ? true : undefined}
    >
      {busy ? (
        <Icon name="spinner" className="icon-spin" />
      ) : icon === undefined ? null : (
        <Icon name={icon} />
      )}
      <span className="keycap-label">
        {busy && busyLabel !== undefined ? busyLabel : children}
      </span>
    </button>
  );
}
