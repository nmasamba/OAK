// SPDX-License-Identifier: Apache-2.0
/**
 * Inline SVG glyphs. Every icon is decorative (`aria-hidden`) unless it is given a
 * `label`, in which case it is an image with that accessible name. The glyphs are
 * strokes on a 24-unit grid so they scale with the text beside them.
 */
export type IconName =
  | "send"
  | "attach"
  | "close"
  | "check"
  | "cross"
  | "download"
  | "copy"
  | "spinner"
  | "grip"
  | "back"
  | "deterministic"
  | "online"
  | "local"
  | "cards"
  | "table"
  | "compare"
  | "topology"
  | "info"
  | "warning"
  | "clock"
  | "key"
  | "file"
  | "plus"
  | "up"
  | "cases"
  | "models"
  | "bulb";

const PATHS: Readonly<Record<IconName, readonly string[]>> = {
  send: ["M4 12h14", "M12 6l6 6-6 6"],
  attach: ["M8 12.5l7.5-7.5a3.2 3.2 0 0 1 4.5 4.5L10 19.5a5 5 0 0 1-7-7l8-8"],
  close: ["M6 6l12 12", "M18 6L6 18"],
  check: ["M5 12l5 5 9-10"],
  cross: ["M6 6l12 12", "M18 6L6 18"],
  download: ["M12 4v12", "M7 11l5 5 5-5", "M5 20h14"],
  copy: ["M9 9h10v10H9z", "M5 15V5h10"],
  spinner: ["M12 3a9 9 0 0 1 9 9"],
  grip: [
    "M9 6h.01",
    "M15 6h.01",
    "M9 12h.01",
    "M15 12h.01",
    "M9 18h.01",
    "M15 18h.01",
  ],
  back: ["M20 12H6", "M12 6l-6 6 6 6"],
  deterministic: [
    "M6 6h12v12H6z",
    "M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4",
  ],
  online: ["M7 18a5 5 0 0 1-.6-9.96A6 6 0 0 1 18 9a4.5 4.5 0 0 1-.5 9z"],
  local: ["M4 5h16v11H4z", "M2 19h20"],
  cards: ["M3 5h8v14H3z", "M13 5h8v14h-8z"],
  table: ["M3 6h18", "M3 12h18", "M3 18h18", "M9 6v12"],
  compare: ["M5 12l4-8 4 8H5z", "M11 20l4-8 4 8h-8z"],
  topology: ["M5 7h4v4H5z", "M15 13h4v4h-4z", "M9 9h3l3 4"],
  info: ["M12 8h.01", "M12 11v5", "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z"],
  warning: ["M12 9v4", "M12 17h.01", "M3 20h18L12 4z"],
  clock: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", "M12 7v5l3 2"],
  key: ["M8 14a4 4 0 1 1 0-8 4 4 0 0 1 0 8z", "M11 11l9 9", "M17 17l2-2"],
  file: ["M6 3h8l4 4v14H6z", "M14 3v4h4"],
  plus: ["M12 5v14", "M5 12h14"],
  up: ["M12 19V5", "M5 12l7-7 7 7"],
  cases: ["M3 3h7v7H3z", "M14 3h7v7h-7z", "M3 14h7v7H3z", "M14 14h7v7h-7z"],
  models: [
    "M4 7h10",
    "M18 7h2",
    "M16 7m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0",
    "M4 17h4",
    "M12 17h8",
    "M10 17m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0",
  ],
  bulb: [
    "M9 18h6",
    "M10 21h4",
    "M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3z",
  ],
};

export function Icon({
  name,
  label,
  size = 16,
  className,
}: {
  readonly name: IconName;
  /** An accessible name makes the icon an image; without one it is decorative. */
  readonly label?: string;
  readonly size?: number;
  readonly className?: string;
}) {
  const classes = ["icon", `icon-${name}`, className].filter(Boolean).join(" ");
  const accessibility =
    label === undefined
      ? { "aria-hidden": true as const }
      : { role: "img" as const, "aria-label": label };
  return (
    <svg
      {...accessibility}
      className={classes}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      focusable="false"
    >
      {PATHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
