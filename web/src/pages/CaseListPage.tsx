// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState, type FormEvent } from "react";

import {
  createDesignCase,
  getModels,
  listDesignCases,
  type JsonObject,
} from "../generated/api";
import { currentModelToken } from "../modelToken";
import { ProblemAlert, toActionFailure, type ActionFailure } from "../problems";
import { Link, useRouter } from "../router";
import { asObject, asString, newIdempotencyKey } from "../support";

type ListState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly items: readonly JsonObject[] }
  | { readonly kind: "failed"; readonly failure: ActionFailure };

export function CaseListPage() {
  const { navigate } = useRouter();
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [structured, setStructured] = useState(false);
  const [originalName, setOriginalName] = useState("brief.md");
  const [content, setContent] = useState("");
  const [creating, setCreating] = useState(false);
  const [createFailure, setCreateFailure] = useState<ActionFailure | null>(
    null,
  );

  // What the workspace can say about interpretation without a token is nothing, so this
  // distinguishes "deterministic" from "unknown" rather than guessing.
  const [interpreter, setInterpreter] = useState<
    "model" | "deterministic" | null
  >(null);

  useEffect(() => {
    const token = currentModelToken();
    if (token === null) {
      return;
    }
    getModels(token)
      .then((status) =>
        setInterpreter(
          asObject(status.modes["online"] ?? null)?.["available"] === true
            ? "model"
            : "deterministic",
        ),
      )
      .catch(() => setInterpreter(null));
  }, []);

  const load = () => {
    setState({ kind: "loading" });
    listDesignCases()
      .then((response) => setState({ kind: "ready", items: response.items }))
      .catch((error: unknown) =>
        setState({ kind: "failed", failure: toActionFailure(error) }),
      );
  };

  useEffect(load, []);

  const onCreate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCreating(true);
    setCreateFailure(null);
    createDesignCase(
      { original_name: originalName, content },
      { idempotencyKey: newIdempotencyKey("create-case") },
    )
      .then((response) => {
        const caseId = asString(response.case["id"]);
        if (caseId !== null) {
          navigate(`/cases/${encodeURIComponent(caseId)}`);
        }
      })
      .catch((error: unknown) => setCreateFailure(toActionFailure(error)))
      .finally(() => setCreating(false));
  };

  return (
    <>
      <h1 id="page-heading">Design cases</h1>
      <p className="summary">
        Open a case to review its brief, interpretation, and lineage, or
        describe a new system in your own words. A structured YAML or JSON brief
        works too, and is interpreted deterministically.
      </p>

      <section aria-labelledby="case-list-heading" className="panel">
        <h2 id="case-list-heading">Open a case</h2>
        <div aria-live="polite">
          {state.kind === "loading" && <p>Loading cases…</p>}
          {state.kind === "failed" && (
            <ProblemAlert failure={state.failure} onReload={load} />
          )}
          {state.kind === "ready" && state.items.length === 0 && (
            <p>No design cases exist yet. Create the first one below.</p>
          )}
        </div>
        {state.kind === "ready" && state.items.length > 0 && (
          <table>
            <caption className="visually-hidden">
              Design cases in this workspace, ordered by identifier
            </caption>
            <thead>
              <tr>
                <th scope="col">Case</th>
                <th scope="col">Status</th>
                <th scope="col">Version</th>
                <th scope="col">Updated</th>
              </tr>
            </thead>
            <tbody>
              {state.items.map((item) => {
                const id = asString(item["id"]) ?? "";
                return (
                  <tr key={id}>
                    <th scope="row">
                      <Link to={`/cases/${encodeURIComponent(id)}`}>
                        {asString(item["title"]) ?? id}
                      </Link>
                      <span className="case-id">{id}</span>
                    </th>
                    <td>
                      <span className="badge">{asString(item["status"])}</span>
                    </td>
                    <td>{asString(item["version"])}</td>
                    <td>{asString(item["updated_at"])}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      <section aria-labelledby="create-heading" className="panel">
        <h2 id="create-heading">Describe what you want to build</h2>
        <p className="hint">
          Write it the way you would explain it to a colleague. OAK turns it
          into a typed intent with a source recorded for every value, and asks
          you to confirm anything it had to propose.{" "}
          {interpreter === "model"
            ? "Online AI is set up; you choose how each brief is read when you interpret it."
            : "No model is set up, so briefs are interpreted deterministically — which maps only what a brief states outright."}{" "}
          <Link to="/settings/models">Model settings</Link>
        </p>
        <div className="field">
          <label htmlFor="brief-structured">
            <input
              id="brief-structured"
              name="brief-structured"
              type="checkbox"
              checked={structured}
              onChange={(event) => {
                const next = event.target.checked;
                setStructured(next);
                setOriginalName(next ? "brief.yaml" : "brief.md");
              }}
            />{" "}
            I have a structured YAML or JSON brief instead
          </label>
        </div>
        <form onSubmit={onCreate}>
          <div className="field">
            <label htmlFor="brief-name">Brief file name</label>
            <input
              id="brief-name"
              name="brief-name"
              value={originalName}
              onChange={(event) => setOriginalName(event.target.value)}
              required
              maxLength={240}
            />
          </div>
          <div className="field">
            <label htmlFor="brief-content">Brief content</label>
            <textarea
              id="brief-content"
              name="brief-content"
              value={content}
              onChange={(event) => setContent(event.target.value)}
              rows={12}
              required
              spellCheck={false}
            />
          </div>
          <button type="submit" disabled={creating}>
            {creating ? "Creating…" : "Create case"}
          </button>
        </form>
        <div aria-live="polite">
          {createFailure !== null && (
            <ProblemAlert failure={createFailure} onReload={load} />
          )}
        </div>
      </section>
    </>
  );
}
