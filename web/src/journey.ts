// SPDX-License-Identifier: Apache-2.0
/**
 * The eight moments of a case, in order, and how far a status has come along them. The
 * rings and pips on the home tiles and the case rail draw from this; the words beside
 * them say the same thing.
 */
export const JOURNEY_STEPS = [
  "Brief",
  "Questions",
  "Designs",
  "Evaluation",
  "Decision",
  "Assurance",
  "Bundle",
  "Install",
] as const;

const DONE_BY_STATUS: Readonly<Record<string, number>> = {
  draft: 0,
  needs_confirmation: 1,
  ready_for_candidates: 2,
  candidates_ready: 3,
  candidate_selected: 5,
  assurance_planned: 6,
  bundle_compiled: 7,
  deployment_approved: 7,
  deployed: 8,
  observing: 8,
  closed: 8,
};

/** Steps done for a status; an unknown status counts as none. */
export function journeyDone(status: string | null): number {
  return status === null ? 0 : (DONE_BY_STATUS[status] ?? 0);
}

export function journeyLabel(status: string | null): string {
  return `${journeyDone(status)} of ${JOURNEY_STEPS.length} steps done`;
}

export function journeyProgress(status: string | null): number {
  return journeyDone(status) / JOURNEY_STEPS.length;
}
