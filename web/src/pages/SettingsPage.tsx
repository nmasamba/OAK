// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  deleteModelCredential,
  discoverModels,
  getModels,
  putModelCredential,
  putModelSelection,
  clearModelSelection,
  type ModelStatusResponse,
  type ModelFamily,
} from "../generated/api";
import {
  announceModelSettingsChanged,
  currentModelToken,
  forgetModelToken,
  rememberModelToken,
} from "../modelToken";
import { ProblemAlert, toActionFailure, type ActionFailure } from "../problems";
import { Link } from "../router";
import { asObject, asString } from "../support";

type LoadState =
  | { readonly kind: "no-token" }
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly status: ModelStatusResponse }
  | { readonly kind: "failed"; readonly failure: ActionFailure };

function selectionOf(
  status: ModelStatusResponse,
): { family: string; modelId: string } | null {
  const selection = asObject(status.selection);
  const family = selection === null ? null : asString(selection["family"]);
  const modelId = selection === null ? null : asString(selection["model_id"]);
  return family === null || modelId === null
    ? null
    : { family, modelId: modelId };
}

export function SettingsPage() {
  const [token, setToken] = useState<string | null>(() => currentModelToken());
  const [tokenDraft, setTokenDraft] = useState("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [family, setFamily] = useState("huggingface");
  const [apiKey, setApiKey] = useState("");
  const [modelId, setModelId] = useState("");
  const [acknowledge, setAcknowledge] = useState(false);
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
      .then((status) => setState({ kind: "ready", status }))
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
      putModelCredential(family, value, token).then(() =>
        setNotice(`Stored the ${family} key on this machine.`),
      ),
    );
  };

  if (state.kind === "no-token" || token === null) {
    return (
      <>
        <h1 id="page-heading">Models</h1>
        <p className="summary">
          Configuring a model provider needs the capability token the API minted
          when it started. It is not a password: it authorises this browser to
          change model settings on this machine, and it changes every time the
          API restarts.
        </p>
        <section aria-labelledby="token-heading" className="panel">
          <h2 id="token-heading">Paste the model-configuration token</h2>
          <p>
            Print it on the machine running the API with{" "}
            <code>oak models token</code>, or under Compose with{" "}
            <code>docker compose exec -T api oak models token</code>.{" "}
            <code>oak serve</code> also prints a link that carries it.
          </p>
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
            <button type="submit" disabled={tokenDraft.trim().length < 16}>
              Use this token
            </button>
          </form>
        </section>
      </>
    );
  }

  const status = state.kind === "ready" ? state.status : null;
  const selection = status === null ? null : selectionOf(status);
  const credentials = new Map(
    (status?.credentials ?? []).map((row) => [row.family, row]),
  );
  const chosen: ModelFamily | undefined = status?.families.find(
    (row) => row.family === family,
  );
  const discovery = status?.discovery[family];

  return (
    <>
      <h1 id="page-heading">Models</h1>
      <p className="summary">
        A model is optional. With none configured, OAK interprets every brief
        deterministically and contacts nothing. With one configured, a
        plain-language brief is sent to that provider and its answers come back
        as claims you must confirm, correct or reject.
      </p>

      <div aria-live="polite">
        {state.kind === "loading" && <p>Loading model settings…</p>}
        {state.kind === "failed" && (
          <ProblemAlert failure={state.failure} onReload={load} />
        )}
        {failure !== null && <ProblemAlert failure={failure} onReload={load} />}
        {notice !== null && <p className="notice">{notice}</p>}
      </div>

      {status !== null && (
        <>
          <section aria-labelledby="current-heading" className="panel">
            <h2 id="current-heading">Current interpretation</h2>
            <p>
              {selection === null ? (
                <>
                  <strong>Deterministic interpretation.</strong> No model is
                  selected, and nothing leaves this machine.
                </>
              ) : (
                <>
                  <strong>
                    {selection.family}/{selection.modelId}
                  </strong>{" "}
                  interprets plain-language briefs.{" "}
                  {status.configured
                    ? "Its key is stored on this machine."
                    : "Its key is missing, so interpretation will refuse until you store one."}
                </>
              )}
            </p>
            {selection !== null && (
              <button
                type="button"
                disabled={busy !== null}
                onClick={() =>
                  run("clear", () =>
                    clearModelSelection(token).then(() =>
                      setNotice("Cleared the model selection."),
                    ),
                  )
                }
              >
                Interpret deterministically instead
              </button>
            )}
            <p className="problem-meta">
              Keys are stored at{" "}
              <code>{asString(status.stores["credentials"])}</code>
              {status.stores["under_compose"] === true
                ? " on the api container's own volume."
                : " on this machine."}{" "}
              They are never returned by this page.
            </p>
          </section>

          <section aria-labelledby="family-heading" className="panel">
            <h2 id="family-heading">Choose a provider</h2>
            <div className="field">
              <label htmlFor="model-family">Model family</label>
              <select
                id="model-family"
                name="model-family"
                value={family}
                onChange={(event) => {
                  setFamily(event.target.value);
                  setModelId("");
                  setNotice(null);
                }}
              >
                {status.families.map((row) => (
                  <option key={row.family} value={row.family}>
                    {row.display_name}
                    {row.default ? " (default)" : ""}
                  </option>
                ))}
              </select>
            </div>
            {chosen !== undefined && (
              <>
                <p>{chosen.data_use_note}.</p>
                <p className="problem-meta">
                  Licence class: {chosen.licence_class}.{" "}
                  {chosen.credential_required
                    ? `Needs ${chosen.key_hint}.`
                    : "Needs no key."}
                </p>
                {chosen.token_help_url !== null && (
                  <p>
                    <a
                      href={chosen.token_help_url}
                      rel="noreferrer noopener"
                      target="_blank"
                    >
                      Create a token for {chosen.display_name}
                    </a>
                  </p>
                )}
              </>
            )}

            <h3>Key</h3>
            <p>
              {credentials.get(family)?.configured === true ? (
                <>
                  A key is stored in the{" "}
                  <strong>{credentials.get(family)?.source}</strong> backend
                  (fingerprint {credentials.get(family)?.fingerprint},{" "}
                  {credentials.get(family)?.length} characters).
                </>
              ) : (
                <>No key is stored for this family.</>
              )}
            </p>
            <form onSubmit={onStoreKey}>
              <div className="field">
                <label htmlFor="api-key">API key</label>
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
              <button
                type="submit"
                disabled={busy !== null || apiKey.trim().length < 16}
              >
                Store key
              </button>
            </form>
            {credentials.get(family)?.configured === true && (
              <button
                type="button"
                disabled={busy !== null}
                onClick={() =>
                  run("remove-key", () =>
                    deleteModelCredential(family, token).then(() =>
                      setNotice(`Removed the ${family} key.`),
                    ),
                  )
                }
              >
                Remove key
              </button>
            )}
          </section>

          <section aria-labelledby="detect-heading" className="panel">
            <h2 id="detect-heading">Detect models</h2>
            <p>
              Detection asks the provider what this key can reach. For Hugging
              Face it works without a key at all.
            </p>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() =>
                run("discover", () =>
                  discoverModels(family, token).then(() =>
                    setNotice(`Detected models for ${family}.`),
                  ),
                )
              }
            >
              {busy === "discover" ? "Detecting…" : "Detect models"}
            </button>
            {discovery !== undefined && (
              <p className="problem-meta">
                {discovery.model_count} model(s) from the {discovery.source}{" "}
                catalogue at {discovery.fetched_at}
                {discovery.stale ? " (stale — detect again)" : ""}
                {discovery.recommended === null
                  ? ""
                  : `; recommended ${discovery.recommended}`}
              </p>
            )}

            <h3>Select a model</h3>
            <div className="field">
              <label htmlFor="model-id">Model identifier</label>
              <input
                id="model-id"
                name="model-id"
                type="text"
                spellCheck={false}
                value={modelId}
                placeholder={discovery?.recommended ?? "openai/gpt-oss-120b"}
                onChange={(event) => setModelId(event.target.value)}
              />
            </div>
            <label htmlFor="acknowledge-data-use">
              <input
                id="acknowledge-data-use"
                name="acknowledge-data-use"
                type="checkbox"
                checked={acknowledge}
                onChange={(event) => setAcknowledge(event.target.checked)}
              />{" "}
              This provider may train on my prompts, and that is acceptable
            </label>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => {
                const wanted = modelId.trim() || (discovery?.recommended ?? "");
                if (wanted === "") {
                  return;
                }
                run("select", () =>
                  putModelSelection(
                    {
                      family,
                      model_id: wanted,
                      acknowledge_data_use: acknowledge,
                    },
                    token,
                  ).then(() => setNotice(`Selected ${family}/${wanted}.`)),
                );
              }}
            >
              Use this model
            </button>
          </section>

          <section aria-labelledby="forget-heading" className="panel">
            <h2 id="forget-heading">This browser</h2>
            <button
              type="button"
              onClick={() => {
                forgetModelToken();
                load();
              }}
            >
              Forget the token in this browser
            </button>
            <p className="problem-meta">
              Forgetting the token here changes nothing on the machine; the
              stored keys and the selection stay as they are.{" "}
              <Link to="/">Back to all cases</Link>
            </p>
          </section>
        </>
      )}
    </>
  );
}
