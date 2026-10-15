// SPDX-License-Identifier: Apache-2.0
import { useState, type ReactNode } from "react";

import { DownloadsSheet } from "./DownloadsSheet";
import type { JsonObject } from "./generated/api";
import { JOURNEY_STEPS, journeyDone, journeyLabel } from "./journey";
import { Link } from "./router";
import { ageOf, asString } from "./support";
import { Keycap } from "./ui";

/**
 * The case at a glance, beside the conversation: a ring for how far it has come, the raw
 * status in mono, the eight moments as pips, and the version. Every picture here has its
 * words: the ring is an image named by its step count, each pip names its step and state.
 */
export function CaseRail({
  caseId,
  caseDocument,
  children,
}: {
  readonly caseId: string;
  readonly caseDocument: JsonObject;
  readonly children?: ReactNode;
}) {
  const status = asString(caseDocument["status"]);
  const done = journeyDone(status);
  const radius = 23;
  const circumference = 2 * Math.PI * radius;
  const updated = asString(caseDocument["updated_at"]);
  const [sheetOpen, setSheetOpen] = useState(false);
  return (
    <aside aria-label="Case at a glance" className="rail">
      <div className="rail-head">
        <svg
          role="img"
          aria-label={journeyLabel(status)}
          width="56"
          height="56"
          viewBox="0 0 56 56"
          className="rail-ring"
        >
          <circle className="tile-ring-track" cx="28" cy="28" r={radius} />
          <circle
            className="tile-ring-fill"
            cx="28"
            cy="28"
            r={radius}
            strokeDasharray={`${(circumference * done) / JOURNEY_STEPS.length} ${circumference}`}
          />
        </svg>
        <code className="rail-status">{status ?? "unknown"}</code>
      </div>
      <ol aria-label="Journey" className="journey">
        {JOURNEY_STEPS.map((step, index) => {
          const state =
            index < done ? "done" : index === done ? "current" : "next";
          return (
            <li
              key={step}
              className={`journey-${state}${step === "Install" ? " journey-install" : ""}`}
              title={step}
            >
              <span className="visually-hidden">
                {step}: {state}
              </span>
            </li>
          );
        })}
      </ol>
      <p className="rail-meta">
        <span className="mono">{caseId}</span>
        <br />
        version{" "}
        <span className="mono">{asString(caseDocument["version"])}</span>
        {updated === null ? "" : ` · ${ageOf(updated)}`}
      </p>
      <div className="rail-actions">
        <Keycap
          tone="quiet"
          icon="download"
          onClick={() => setSheetOpen(true)}
          title="Every file, with digests"
        >
          Take it
        </Keycap>
      </div>
      {children}
      <p className="rail-links">
        <Link to="/">Back to all cases</Link>
      </p>
      {sheetOpen ? (
        <DownloadsSheet
          caseId={caseId}
          caseDocument={caseDocument}
          onClose={() => setSheetOpen(false)}
        />
      ) : null}
    </aside>
  );
}

/** One line from the machine, with its lamp. */
export function Moment({
  children,
  fresh = false,
  className,
}: {
  readonly children: ReactNode;
  /** Rises in, for the newest line. */
  readonly fresh?: boolean;
  readonly className?: string;
}) {
  const classes = ["moment", fresh ? "rise" : null, className]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={classes}>
      <span className="moment-lamp" aria-hidden="true">
        <svg
          aria-hidden="true"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M9 18h6" />
          <path d="M10 21h4" />
          <path d="M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3z" />
        </svg>
      </span>
      <div className="moment-body">{children}</div>
    </div>
  );
}
