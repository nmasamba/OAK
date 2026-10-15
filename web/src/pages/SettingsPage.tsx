// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Moment } from "../CaseRail";
import {
  clearModelSelection,
  deleteModelCredential,
  discoverModels,
  getModelCatalogue,
  getModels,
  putModelCredential,
  putModelSelection,
  verifyModelCredential,
  type JsonObject,
  type ModelStatusResponse,
} from "../generated/api";
import {
  announceModelSettingsChanged,
  currentModelToken,
  forgetModelToken,
  rememberModelToken,
} from "../modelToken";
import { ProblemAlert, toActionFailure, type ActionFailure } from "../problems";
import { Link } from "../router";
import { ageOf, asArray, asObject, asString } from "../support";
import { Chip, CopyPlate, Keycap } from "../ui";

type LoadState =
  | { readonly kind: "no-token" }
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly status: ModelStatusResponse }
  | { readonly kind: "failed"; readonly failure: ActionFailure };

interface Pair {
  readonly modelId: string;
  readonly provider: string;
  readonly licence: string;
  readonly price: number | null;
  readonly throughput: number | null;
  readonly free: boolean;
  readonly structured: boolean;
}

function pairsOf(catalogue: JsonObject | null): readonly Pair[] {
  if (catalogue === null) {
    return [];
  }
  const pairs: Pair[] = [];
  for (const model of asArray(catalogue["models"]).map(asObject)) {
    if (model === null) {
      continue;
    }
    const modelId = asString(model["id"]);
    if (modelId === null) {
      continue;
    }
    for (const route of asArray(model["providers"]).map(asObject)) {
      if (route === null) {
        continue;
      }
      const provider = asString(route["provider"]);
      if (provider === null) {
        continue;
      }
      pairs.push({
        modelId,
        provider,
        licence: asString(model["licence"]) ?? "unknown",
        price:
          typeof route["output_price_per_million"] === "number"
            ? route["output_price_per_million"]
            : null,
        throughput:
          typeof route["throughput"] === "number" ? route["throughput"] : null,
        free: route["is_free"] === true,
        structured: route["supports_structured_output"] === true,
      });
    }
  }
  return pairs;
}

function sentence(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function VerdictBadge({
  verification,
}: {
  readonly verification: JsonObject | null;
}) {
  if (verification === null) {
    return (
      <Chip small icon="clock">
        not yet verified
      </Chip>
    );
  }
  const verdict = asString(verification["verdict"]) ?? "unknown";
  const checkedAt = asString(verification["checked_at"]);
  const stale = verification["stale"] === true;
  const definitive =
    verdict === "accepted" ||
    verdict === "rejected" ||
    verdict === "scope_limited";
  const attempt = asObject(verification["last_attempt"]);
  const role = asString(verification["token_role"]);
  const permission = verification["inference_permission"];
  const canPay = verification["can_pay"];
  const reason = asString(verification["reason"]);
  const details: string[] = [];
  if (role !== null) {
    details.push(`${role} token`);
  }
  if (permission === false) {
    details.push("no Inference Providers permission");
  } else if (permission === null && verdict === "accepted") {
    details.push("Inference Providers permission unknown");
  }
  if (typeof canPay === "boolean") {
    details.push(`account can pay: ${canPay ? "yes" : "no"}`);
  }
  return (
    <span data-verdict={verdict}>
      <Chip
        small
        tone={verdict === "accepted" ? "ok" : definitive ? "brass" : "neutral"}
        icon={
          verdict === "accepted" ? "check" : definitive ? "warning" : "clock"
        }
      >
        {definitive ? verdict.replace("_", " ") : "not verified"}
      </Chip>{" "}
      {checkedAt === null
        ? ""
        : definitive
          ? `${ageOf(checkedAt)} (${checkedAt})`
          : `attempted ${ageOf(checkedAt)}`}
      {stale && definitive ? " — stale; verify again" : ""}
      {details.length > 0 ? ` — ${details.join("; ")}` : ""}
      {reason !== null && verdict !== "accepted" ? ` — ${reason}` : ""}
      {attempt !== null
        ? ` (the last check ${ageOf(asString(attempt["at"]) ?? "")} could not reach Hugging Face; this verdict stands)`
        : ""}
    </span>
  );
}

export function SettingsPage() {
  const [token, setToken] = useState<string | null>(() => currentModelToken());
  const [tokenDraft, setTokenDraft] = useState("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [catalogue, setCatalogue] = useState<JsonObject | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [localModel, setLocalModel] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<ActionFailure | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    const current = currentModelToken();
    setToken(current);
    if (current === null) {
      setState({ kind: "no-token" });
      return;
    }
    setState({ kind: "loading" });
    getModels(current)
      .then((status) => {
        setState({ kind: "ready", status });
        return getModelCatalogue("huggingface", current)
          .then((response) => setCatalogue(asObject(response.discovery)))
          .catch(() => setCatalogue(null));
      })
      .catch((error: unknown) =>
        setState({ kind: "failed", failure: toActionFailure(error) }),
      );
  }, []);

  useEffect(load, [load]);

  const run = (label: string, action: () => Promise<unknown>) => {
    setBusy(label);
    setFailure(null);
    setNotice(null);
    action()
      .then(() => {
        announceModelSettingsChanged();
        load();
      })
      .catch((error: unknown) => setFailure(toActionFailure(error)))
      .finally(() => setBusy(null));
  };

  const onAdoptToken = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    rememberModelToken(tokenDraft);
    setTokenDraft("");
    load();
  };

  const onStoreKey = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (token === null) {
      return;
    }
    const value = apiKey;
    // Clear the field before the request resolves: the key must not sit in the DOM
    // waiting for a network round trip to finish.
    setApiKey("");
    run("store-key", () =>
      putModelCredential("huggingface", value, token)
        // Storing verifies by default: one free request to huggingface.co that generates
        // nothing. The verdict lands in the status the page reloads.
        .then(() => verifyModelCredential("huggingface", token))
        .then((status) => {
          const row = status.credentials.find(
            (credential) => credential.family === "huggingface",
          );
          const verdict = asObject(row?.verification ?? null);
          const word = verdict === null ? null : asString(verdict["verdict"]);
          setNotice(
            word === "accepted" ||
              word === "rejected" ||
              word === "scope_limited"
              ? `Stored the Hugging Face token on this machine; Hugging Face says: ${word.replace("_", " ")}.`
              : "Stored the Hugging Face token on this machine; it could not be verified " +
                  "(Hugging Face was not heard), so it is unverified until you try again.",
          );
        }),
    );
  };

  if (state.kind === "no-token" || token === null) {
    return (
      <div className="convo">
        <div className="thread">
          <h1 id="page-heading">Models</h1>
          <Moment fresh>
            <p>This page needs the token the API printed.</p>
          </Moment>
          <section aria-labelledby="token-heading" className="card">
            <h2 id="token-heading">Paste the model-configuration token</h2>
            <p className="thread-aside">
              Not a password. It lets this browser change model settings here.
              It changes when the API restarts.
            </p>
            <CopyPlate
              command="docker compose exec -T api oak models token"
              label="Copy the command that prints the token"
            />
            <details>
              <summary>Without Compose</summary>
              <p className="thread-aside">
                Run <code>oak models token</code> where the API runs.{" "}
                <code>oak serve</code> also prints a link that carries it.
              </p>
            </details>
            <form onSubmit={onAdoptToken}>
              <div className="field">
                <label htmlFor="model-token">Model-configuration token</label>
                <input
                  id="model-token"
                  name="model-token"
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                  value={tokenDraft}
                  onChange={(event) => setTokenDraft(event.target.value)}
                />
              </div>
              <Keycap
                type="submit"
                icon="key"
                disabled={tokenDraft.trim().length < 16}
              >
                Use this token
              </Keycap>
            </form>
          </section>
        </div>
      </div>
    );
  }

  const status = state.kind === "ready" ? state.status : null;
  const huggingface = status?.credentials.find(
    (row) => row.family === "huggingface",
  );
  const verification = asObject(huggingface?.verification ?? null);
  const online = status === null ? null : asObject(status.modes["online"]);
  const pair = online === null ? null : asObject(online["pair"]);
  const local = status === null ? null : asObject(status.modes["local"]);
  const pinned = asObject(status?.selections["huggingface"] ?? null);
  const pinnedLocal = asObject(status?.selections["local"] ?? null);
  const discovery = status?.discovery["huggingface"];
  const family = status?.families.find((row) => row.family === "huggingface");
  const pairs = pairsOf(catalogue).filter((row) => row.structured);
  const pairsWithoutStructured = pairsOf(catalogue).length - pairs.length;

  return (
    <div className="convo">
      <div className="thread">
        <h1 id="page-heading">Models</h1>
        <Moment fresh>
          <p>
            Every brief is read deterministically unless you choose otherwise.
          </p>
          <p className="thread-aside">
            Online AI and Local AI are set up here.
          </p>
        </Moment>

        <div aria-live="polite">
          {state.kind === "loading" && <p>Loading model settings…</p>}
          {state.kind === "failed" && (
            <ProblemAlert failure={state.failure} onReload={load} />
          )}
          {failure !== null && (
            <ProblemAlert failure={failure} onReload={load} />
          )}
          {notice !== null && <p className="notice">{notice}</p>}
        </div>

        {status !== null && (
          <>
            <section aria-labelledby="token-status-heading" className="card">
              <h2 id="token-status-heading">Hugging Face account</h2>
              <p className="thread-aside">
                {sentence(
                  family?.data_use_note ??
                    "requests are routed by Hugging Face to a provider",
                )}
                . Your free monthly credit applies first; OAK never buys credit.
                {family?.token_help_url ? (
                  <>
                    {" "}
                    <a
                      href={family.token_help_url}
                      rel="noreferrer noopener"
                      target="_blank"
                    >
                      Create a token
                    </a>{" "}
                    ({family.key_hint}).
                  </>
                ) : null}
              </p>
              <p>
                {huggingface?.configured === true ? (
                  <>
                    A token is stored in the{" "}
                    <strong>{huggingface.source}</strong> backend (fingerprint{" "}
                    {huggingface.fingerprint}, {huggingface.length} characters).
                    Hugging Face says:{" "}
                    <VerdictBadge verification={verification} />
                  </>
                ) : (
                  <>No Hugging Face token is stored on this machine.</>
                )}
              </p>
              <form onSubmit={onStoreKey}>
                <div className="field">
                  <label htmlFor="api-key">Hugging Face token</label>
                  <input
                    id="api-key"
                    name="api-key"
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    value={apiKey}
                    onChange={(event) => setApiKey(event.target.value)}
                  />
                </div>
                <div className="actions">
                  <Keycap
                    type="submit"
                    icon="key"
                    busy={busy === "store-key"}
                    busyLabel="Storing and verifying…"
                    disabled={busy !== null || apiKey.trim().length < 16}
                    title="One request to huggingface.co that generates nothing: whether the token is accepted, its role, and whether the account can pay. The token itself is never returned."
                  >
                    Store and verify
                  </Keycap>
                  {huggingface?.configured === true && (
                    <>
                      <Keycap
                        tone="quiet"
                        busy={busy === "verify"}
                        busyLabel="Verifying…"
                        disabled={busy !== null}
                        onClick={() =>
                          run("verify", () =>
                            verifyModelCredential("huggingface", token).then(
                              () =>
                                setNotice(
                                  "Asked Hugging Face about the stored token.",
                                ),
                            ),
                          )
                        }
                      >
                        Verify again
                      </Keycap>
                      <Keycap
                        tone="quiet"
                        icon="cross"
                        disabled={busy !== null}
                        onClick={() =>
                          run("remove-key", () =>
                            deleteModelCredential("huggingface", token).then(
                              () =>
                                setNotice("Removed the Hugging Face token."),
                            ),
                          )
                        }
                      >
                        Remove token
                      </Keycap>
                    </>
                  )}
                </div>
              </form>
            </section>

            <section aria-labelledby="online-heading" className="card">
              <h2 id="online-heading">Online AI</h2>
              <p>
                {online?.["available"] === true && pair !== null ? (
                  <>
                    Would call <strong>{asString(pair["model_id"])}</strong>
                    {asString(pair["provider_route"]) === null
                      ? ""
                      : ` via ${asString(pair["provider_route"])}`}
                    {typeof pair["output_price_per_million"] === "number"
                      ? ` at $${pair["output_price_per_million"]}/M output tokens`
                      : ""}{" "}
                    (
                    {asString(pair["source"]) === "pinned"
                      ? "the pair you pinned"
                      : "the preferred pair: the current top model on Hugging Face with a structured-output route"}
                    ).
                  </>
                ) : (
                  <>
                    Not ready:{" "}
                    {asString(online?.["reason"] ?? null) ?? "unknown"}.
                  </>
                )}
              </p>
              <div className="actions">
                <Keycap
                  tone="quiet"
                  icon="online"
                  busy={busy === "discover"}
                  busyLabel="Reading the catalogue…"
                  disabled={busy !== null}
                  title="Reads two public pages anonymously; the token is not sent."
                  onClick={() =>
                    run("discover", () =>
                      discoverModels("huggingface", token).then(() =>
                        setNotice("Read the Hugging Face catalogue."),
                      ),
                    )
                  }
                >
                  Refresh models
                </Keycap>
                {pinned !== null && (
                  <Keycap
                    tone="quiet"
                    disabled={busy !== null}
                    onClick={() =>
                      run("clear", () =>
                        clearModelSelection("huggingface", token).then(() =>
                          setNotice("Online AI uses the preferred pair again."),
                        ),
                      )
                    }
                  >
                    Use the preferred pair instead
                  </Keycap>
                )}
              </div>
              {discovery !== undefined && (
                <p className="timeline-meta">
                  {discovery.model_count} model(s) from the {discovery.source}{" "}
                  catalogue, read {ageOf(discovery.fetched_at)} (
                  {discovery.fetched_at})
                  {discovery.stale ? " — stale; refresh" : ""}
                  {discovery.recommended === null
                    ? ""
                    : `; preferred ${discovery.recommended}`}
                  .
                </p>
              )}
              {pairs.length > 0 && (
                <>
                  <h3>Pick a model and provider pair</h3>
                  <p className="timeline-meta">
                    Routes with structured output only
                    {pairsWithoutStructured > 0
                      ? ` (${pairsWithoutStructured} other route(s) omitted)`
                      : ""}
                    . Prices are the provider's published output price per
                    million tokens; throughput is Hugging Face's last
                    measurement.
                  </p>
                  <div
                    className="table-scroll"
                    tabIndex={0}
                    role="region"
                    aria-label="Model and provider pairs table"
                  >
                    <table>
                      <caption className="visually-hidden">
                        Model and provider pairs the stored token can call
                      </caption>
                      <thead>
                        <tr>
                          <th scope="col">Model</th>
                          <th scope="col">Provider</th>
                          <th scope="col">Licence</th>
                          <th scope="col">$/M output</th>
                          <th scope="col">Tokens/s</th>
                          <th scope="col">
                            <span className="visually-hidden">Pick</span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {pairs.map((row) => {
                          const isPinned =
                            pinned !== null &&
                            asString(pinned["model_id"]) === row.modelId &&
                            asString(pinned["provider_route"]) === row.provider;
                          return (
                            <tr key={`${row.modelId}:${row.provider}`}>
                              <th scope="row">
                                {row.modelId}
                                {discovery?.recommended === row.modelId ? (
                                  <>
                                    {" "}
                                    <Chip small tone="brass">
                                      preferred
                                    </Chip>
                                  </>
                                ) : null}
                              </th>
                              <td>{row.provider}</td>
                              <td>{row.licence}</td>
                              <td className="mono">
                                {row.free
                                  ? "free (promotion)"
                                  : row.price === null
                                    ? "—"
                                    : `$${row.price}`}
                              </td>
                              <td className="mono">
                                {row.throughput === null
                                  ? "—"
                                  : Math.round(row.throughput)}
                              </td>
                              <td>
                                <Keycap
                                  tone="quiet"
                                  className="keycap-small"
                                  disabled={busy !== null || isPinned}
                                  onClick={() =>
                                    run("select", () =>
                                      putModelSelection(
                                        {
                                          family: "huggingface",
                                          model_id: row.modelId,
                                          provider_route: row.provider,
                                        },
                                        token,
                                      ).then(() =>
                                        setNotice(
                                          `Pinned ${row.modelId} via ${row.provider} for Online AI.`,
                                        ),
                                      ),
                                    )
                                  }
                                >
                                  {isPinned ? "Pinned" : "Use this pair"}
                                </Keycap>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </section>

            <section aria-labelledby="local-heading" className="card">
              <h2 id="local-heading">Local AI</h2>
              <p className="thread-aside">
                An OpenAI-compatible server on this machine at{" "}
                <code>{asString(local?.["endpoint"] ?? null) ?? "—"}</code>.
                Nothing leaves this machine.{" "}
                <span title="Set OAK_MODEL_ENDPOINT_LOCAL on the API process to change the endpoint.">
                  The endpoint is set on the API process.
                </span>
              </p>
              <p>
                {local?.["available"] === true ? (
                  <>
                    Would call <strong>{asString(local["model_id"])}</strong>.
                  </>
                ) : (
                  <>
                    Not ready:{" "}
                    {asString(local?.["reason"] ?? null) ??
                      "no model is pinned"}
                    .
                  </>
                )}
              </p>
              <div className="field">
                <label htmlFor="local-model">
                  Model the local server serves
                </label>
                <input
                  id="local-model"
                  name="local-model"
                  type="text"
                  spellCheck={false}
                  value={localModel}
                  placeholder={
                    asString(pinnedLocal?.["model_id"] ?? null) ?? "qwen3:8b"
                  }
                  onChange={(event) => setLocalModel(event.target.value)}
                />
              </div>
              <div className="actions">
                <Keycap
                  icon="local"
                  disabled={busy !== null || localModel.trim() === ""}
                  busy={busy === "select-local"}
                  busyLabel="Pinning…"
                  onClick={() => {
                    const wanted = localModel.trim();
                    run("select-local", () =>
                      putModelSelection(
                        { family: "local", model_id: wanted },
                        token,
                      ).then(() => {
                        setLocalModel("");
                        setNotice(`Pinned ${wanted} for Local AI.`);
                      }),
                    );
                  }}
                >
                  Use this model
                </Keycap>
                {pinnedLocal !== null && (
                  <Keycap
                    tone="quiet"
                    disabled={busy !== null}
                    onClick={() =>
                      run("clear-local", () =>
                        clearModelSelection("local", token).then(() =>
                          setNotice("Local AI has no model pinned."),
                        ),
                      )
                    }
                  >
                    Clear
                  </Keycap>
                )}
              </div>
            </section>

            <section aria-labelledby="forget-heading" className="card">
              <h2 id="forget-heading">This browser</h2>
              <p className="timeline-meta">
                Keys are stored at{" "}
                <code>{asString(status.stores["credentials"])}</code>
                {status.stores["under_compose"] === true
                  ? " on the api container's own volume."
                  : " on this machine."}{" "}
                They are never returned by this page.
              </p>
              <div className="actions">
                <Keycap
                  tone="quiet"
                  onClick={() => {
                    forgetModelToken();
                    load();
                  }}
                  title="Changes nothing on the machine; the stored keys and the pinned models stay as they are."
                >
                  Forget the token in this browser
                </Keycap>
              </div>
              <p className="thread-aside">
                <Link to="/">Back to all cases</Link>
              </p>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
