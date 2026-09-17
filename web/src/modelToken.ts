// SPDX-License-Identifier: Apache-2.0

/**
 * The capability token the serving API process minted.
 *
 * It is a capability, not a password: it authorises this browser to configure the model
 * provider on this machine, and it dies with the API process that minted it. It is kept in
 * `sessionStorage` so it does not outlive the tab, and when it arrives in the URL fragment
 * (which `oak serve` prints) the fragment is stripped immediately so the token does not sit
 * in the address bar, in history, or in anything the page later links to.
 */

const STORAGE_KEY = "oak.model-token";

/** Fired after anything changes the stored model configuration on this machine. */
export const MODEL_SETTINGS_CHANGED = "oak:model-settings-changed";

export function announceModelSettingsChanged(): void {
  window.dispatchEvent(new Event(MODEL_SETTINGS_CHANGED));
}

function readStorage(): string | null {
  try {
    return window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    // Private windows and blocked site data both throw here; the paste field still works.
    return null;
  }
}

function writeStorage(token: string | null): void {
  try {
    if (token === null) {
      window.sessionStorage.removeItem(STORAGE_KEY);
    } else {
      window.sessionStorage.setItem(STORAGE_KEY, token);
    }
  } catch {
    // Nothing to do: the caller keeps the token in component state for this page load.
  }
}

/** Take a `#token=…` fragment, store it, and remove it from the address bar. */
export function adoptTokenFromFragment(): string | null {
  const fragment = window.location.hash;
  if (!fragment.startsWith("#token=")) {
    return null;
  }
  const token = decodeURIComponent(fragment.slice("#token=".length)).trim();
  if (token.length < 16) {
    return null;
  }
  writeStorage(token);
  window.history.replaceState(
    null,
    "",
    `${window.location.pathname}${window.location.search}`,
  );
  return token;
}

export function currentModelToken(): string | null {
  return adoptTokenFromFragment() ?? readStorage();
}

export function rememberModelToken(token: string): void {
  writeStorage(token.trim());
}

export function forgetModelToken(): void {
  writeStorage(null);
}
