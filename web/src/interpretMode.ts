// SPDX-License-Identifier: Apache-2.0
/**
 * The mode chosen for a case on the intake form, carried to the case page where the
 * interpretation actually runs. Per tab and per case, in `sessionStorage`, so it never
 * outlives the tab and is never mistaken for a setting on the machine.
 */

import { isInterpretMode, type InterpretMode } from "./ModeSelect";

const PREFIX = "oak.interpret-mode:";

export function rememberInterpretMode(
  caseId: string,
  mode: InterpretMode,
): void {
  try {
    window.sessionStorage.setItem(PREFIX + caseId, mode);
  } catch {
    // Storage may be unavailable (private windows, blocked site data); the case page then
    // starts from the deterministic default, which is the safe one.
  }
}

export function recallInterpretMode(caseId: string): InterpretMode {
  try {
    const stored = window.sessionStorage.getItem(PREFIX + caseId);
    return isInterpretMode(stored) ? stored : "deterministic";
  } catch {
    return "deterministic";
  }
}
