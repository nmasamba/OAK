// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";

import { Link } from "../router";

/**
 * A recent case: a link the size of a hand, with a progress ring and the raw status in
 * mono. The ring is decoration; `stepLabel` ("Step 3 of 7") is the text that carries
 * it, visually hidden, and the status word is visible.
 */
export function Tile({
  to,
  title,
  status,
  progress,
  stepLabel,
  meta,
}: {
  readonly to: string;
  readonly title: ReactNode;
  readonly status: string;
  /** 0 to 1. */
  readonly progress: number;
  readonly stepLabel: string;
  readonly meta?: ReactNode;
}) {
  const clamped = Math.min(1, Math.max(0, progress));
  const radius = 15;
  const circumference = 2 * Math.PI * radius;
  return (
    <Link to={to} className="tile">
      <span className="tile-ring" aria-hidden="true">
        <svg aria-hidden="true" width="40" height="40" viewBox="0 0 40 40">
          <circle className="tile-ring-track" cx="20" cy="20" r={radius} />
          <circle
            className="tile-ring-fill"
            cx="20"
            cy="20"
            r={radius}
            strokeDasharray={`${circumference * clamped} ${circumference}`}
          />
        </svg>
      </span>
      <span className="tile-body">
        <span className="tile-title">{title}</span>
        {meta === undefined ? null : <span className="tile-meta">{meta}</span>}
        <span className="tile-status">
          <span className="visually-hidden">{stepLabel}, </span>
          <code className="mono">{status}</code>
        </span>
      </span>
    </Link>
  );
}
