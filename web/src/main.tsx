// SPDX-License-Identifier: Apache-2.0
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import { getVersion, type VersionResponse } from "./generated/api";
import "./styles.css";

type LoadState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly information: VersionResponse }
  | { readonly kind: "failed"; readonly message: string };

function App() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    getVersion()
      .then((information) => {
        if (!controller.signal.aborted) {
          setState({ kind: "ready", information });
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setState({
            kind: "failed",
            message: "The local OAK API is unavailable. Start it and retry.",
          });
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <main>
      <section className="status-card" aria-labelledby="status-heading">
        <p className="eyebrow">Local control plane</p>
        <h1 id="status-heading">OAK Community</h1>
        <p className="summary">
          A non-production harness for typed architecture design and planning.
        </p>

        <div className="status" aria-live="polite">
          {state.kind === "loading" && <p>Checking the local API…</p>}
          {state.kind === "failed" && <p className="error">{state.message}</p>}
          {state.kind === "ready" && (
            <dl>
              <div>
                <dt>API status</dt>
                <dd>
                  <span className="indicator" aria-hidden="true" /> Ready
                </dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd>{state.information.version}</dd>
              </div>
              <div>
                <dt>Canonical schemas</dt>
                <dd>{state.information.schema_versions.join(", ")}</dd>
              </div>
            </dl>
          )}
        </div>

        <p className="boundary">
          This harness has no target mutation, secret resolution, or
          inference-traffic path.
        </p>
      </section>
    </main>
  );
}

const container = document.getElementById("root");
if (container === null) {
  throw new Error("Application root is missing");
}
createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
