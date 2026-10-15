// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";

import { Icon } from "./Icon";

/**
 * A command on a plate with a copy control. Copying writes the text to the clipboard
 * and nothing else: this component imports no API client and makes no request. The
 * commands it shows run only where the user pastes them, on the local command line.
 */
export function CopyPlate({
  command,
  label,
  className,
}: {
  readonly command: string;
  /** The copy control's accessible name; it starts with "Copy". */
  readonly label: string;
  readonly className?: string;
}) {
  const [status, setStatus] = useState<"idle" | "copied" | "failed">("idle");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setStatus("copied");
    } catch {
      setStatus("failed");
    }
  };
  const classes = ["plate", className].filter(Boolean).join(" ");
  return (
    <span className={classes}>
      <code className="plate-command">{command}</code>
      <button
        type="button"
        className={`plate-copy plate-copy-${status}`}
        onClick={() => {
          void copy();
        }}
        aria-label={label}
      >
        <Icon name={status === "copied" ? "check" : "copy"} size={14} />
        <span>Copy</span>
      </button>
      <span className="plate-status" role="status">
        {status === "copied"
          ? "Copied"
          : status === "failed"
            ? "Copy failed. Select the text."
            : ""}
      </span>
    </span>
  );
}
