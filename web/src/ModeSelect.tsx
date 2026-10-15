// SPDX-License-Identifier: Apache-2.0
import type { ModelStatusResponse } from "./generated/api";
import { Link } from "./router";
import { ageOf, asObject, asString } from "./support";
import { Icon } from "./ui/Icon";

/** The three ways a brief can be read. Chosen per request; nothing is "in force". */
export type InterpretMode = "deterministic" | "online" | "local";

export const INTERPRET_MODES: readonly InterpretMode[] = [
  "deterministic",
  "online",
  "local",
];

export function isInterpretMode(value: unknown): value is InterpretMode {
  return value === "deterministic" || value === "online" || value === "local";
}

/**
 * The token's verdict in words a reader cannot mistake: only what the Hub actually said is
 * called a verdict; "unreachable" and "unverifiable" mean it was not heard.
 */
export function describeVerdict(
  verdict: string | null,
  checkedAt: string | null,
  stale: boolean,
): string {
  if (verdict === null || checkedAt === null) {
    return "token not yet verified";
  }
  if (verdict === "unreachable") {
    return `token not verified (Hugging Face could not be reached ${ageOf(checkedAt)})`;
  }
  if (verdict === "unverifiable") {
    return `token not verified (no way to check it ${ageOf(checkedAt)})`;
  }
  const word = verdict === "scope_limited" ? "scope limited" : verdict;
  return `token ${word} ${ageOf(checkedAt)}${stale ? " (stale — verify again)" : ""}`;
}

/** What the status document says about one mode, flattened for display. */
export interface ModeSummary {
  readonly available: boolean;
  readonly reason: string | null;
  readonly label: string;
  readonly detail: string;
}

export function summariseModes(
  status: ModelStatusResponse | null,
  tokenPresent: boolean,
): Record<InterpretMode, ModeSummary> {
  const deterministic: ModeSummary = {
    available: true,
    reason: null,
    label: "Deterministic — nothing leaves this machine",
    detail:
      "Maps only what the brief states outright and asks about the rest. The default: no model, no token, and nothing leaves this machine.",
  };
  if (!tokenPresent) {
    const needsToken =
      "needs the model-configuration token; open Model settings to paste it";
    return {
      deterministic,
      online: {
        available: false,
        reason: needsToken,
        label: "Online AI — not ready",
        detail: `Online AI ${needsToken}.`,
      },
      local: {
        available: false,
        reason: needsToken,
        label: "Local AI — not ready",
        detail: `Local AI ${needsToken}.`,
      },
    };
  }
  const online = status === null ? null : asObject(status.modes["online"]);
  const pair = online === null ? null : asObject(online["pair"]);
  const verification =
    online === null ? null : asObject(online["verification"]);
  const local = status === null ? null : asObject(status.modes["local"]);

  const onlineAvailable = online?.["available"] === true;
  const model = pair === null ? null : asString(pair["model_id"]);
  const route = pair === null ? null : asString(pair["provider_route"]);
  const price =
    pair === null ? null : (pair["output_price_per_million"] as number | null);
  const source = pair === null ? null : asString(pair["source"]);
  const verdict =
    verification === null ? null : asString(verification["verdict"]);
  const checkedAt =
    verification === null ? null : asString(verification["checked_at"]);
  const stale = verification?.["stale"] === true;
  const onlineReason =
    online === null
      ? "model settings could not be read"
      : (asString(online["reason"]) ?? null);
  const verdictText = describeVerdict(verdict, checkedAt, stale);
  const onlineDetail = onlineAvailable
    ? `Sends this brief to Hugging Face Inference Providers: ${model ?? "?"}${
        route === null ? "" : ` via ${route}`
      }${price === null || price === undefined ? "" : ` at $${price}/M output tokens`}${
        source === "pinned" ? " (the pair you pinned)" : " (the preferred pair)"
      }. Your free monthly Hugging Face credit applies first; nothing beyond it is promised. ${verdictText}.`
    : `Online AI is not ready: ${onlineReason ?? "unknown"}.`;

  const localAvailable = local?.["available"] === true;
  const localModel = local === null ? null : asString(local["model_id"]);
  const endpoint = local === null ? null : asString(local["endpoint"]);
  const localReason = local === null ? null : asString(local["reason"]);
  return {
    deterministic,
    online: {
      available: onlineAvailable,
      reason: onlineAvailable ? null : onlineReason,
      label: onlineAvailable
        ? `Online AI — ${model ?? "?"}${route === null ? "" : ` via ${route}`}`
        : "Online AI — not ready",
      detail: onlineDetail,
    },
    local: {
      available: localAvailable,
      reason: localAvailable ? null : localReason,
      label: localAvailable
        ? `Local AI — ${localModel ?? "?"} on this machine`
        : "Local AI — not ready",
      detail: localAvailable
        ? `Sends this brief to ${localModel ?? "?"} on ${endpoint ?? "the loopback server"}; nothing leaves this machine.`
        : `Local AI is not ready: ${localReason ?? "unknown"}.`,
    },
  };
}

const MODE_WORDS: Readonly<Record<InterpretMode, string>> = {
  deterministic: "Deterministic",
  online: "Online AI",
  local: "Local AI",
};

/**
 * The three modes as a row of radio chips: the chosen one shows its glyph and its word,
 * the others their glyph with the word for assistive technology. A mode that is not
 * available is disabled and its reason sits in the chip's title. The group's name is the
 * question the pins read, "How should this brief be read?".
 */
export function ModeChooser({
  id,
  value,
  onChange,
  status,
  tokenPresent,
  disabled,
}: {
  readonly id: string;
  readonly value: InterpretMode;
  readonly onChange: (mode: InterpretMode) => void;
  readonly status: ModelStatusResponse | null;
  readonly tokenPresent: boolean;
  readonly disabled?: boolean | undefined;
}) {
  const summaries = summariseModes(status, tokenPresent);
  return (
    <fieldset className="mode-group" disabled={disabled === true}>
      <legend className="visually-hidden">
        How should this brief be read?
      </legend>
      {INTERPRET_MODES.map((mode) => {
        const summary = summaries[mode];
        const on = value === mode;
        return (
          <label
            key={mode}
            className={`mode${on ? " mode-on" : ""}${summary.available ? "" : " mode-off"}`}
            title={summary.detail}
          >
            <input
              type="radio"
              name={id}
              value={mode}
              checked={on}
              disabled={!summary.available}
              onChange={() => onChange(mode)}
            />
            <Icon name={mode} size={18} />
            <span className={on ? "mode-word" : "visually-hidden"}>
              {MODE_WORDS[mode]}
            </span>
          </label>
        );
      })}
    </fieldset>
  );
}

/** One line on the chosen mode, with the longer explanation in its title. */
export function ModeDetail({
  value,
  status,
  tokenPresent,
}: {
  readonly value: InterpretMode;
  readonly status: ModelStatusResponse | null;
  readonly tokenPresent: boolean;
}) {
  const summary = summariseModes(status, tokenPresent)[value];
  return (
    <p className="mode-detail" data-mode-detail={value} title={summary.detail}>
      {summary.label} · <Link to="/settings/models">Model settings</Link>
    </p>
  );
}

export function ModeSelect({
  id,
  value,
  onChange,
  status,
  tokenPresent,
  disabled,
}: {
  readonly id: string;
  readonly value: InterpretMode;
  readonly onChange: (mode: InterpretMode) => void;
  readonly status: ModelStatusResponse | null;
  readonly tokenPresent: boolean;
  readonly disabled?: boolean;
}) {
  return (
    <div className="mode-select">
      <ModeChooser
        id={id}
        value={value}
        onChange={onChange}
        status={status}
        tokenPresent={tokenPresent}
        disabled={disabled}
      />
      <ModeDetail value={value} status={status} tokenPresent={tokenPresent} />
    </div>
  );
}
