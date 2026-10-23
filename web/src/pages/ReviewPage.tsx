// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

import { CaseRail, Moment } from "../CaseRail";
import { ClaimBadge, MaterialityBadge, claimClassForSource } from "../claims";
import { getDesignCase, type JsonObject } from "../generated/api";
import { formatValue, readablePointer, resolvePointer } from "../jsonpointer";
import { ProblemAlert, toActionFailure, type ActionFailure } from "../problems";
import { Link } from "../router";
import { asArray, asNumber, asObject, asString } from "../support";

type ReviewState =
  | { readonly kind: "loading" }
  | {
      readonly kind: "ready";
      readonly caseDocument: JsonObject;
      readonly intent: JsonObject | null;
    }
  | { readonly kind: "failed"; readonly failure: ActionFailure };

export function ReviewPage({ caseId }: { readonly caseId: string }) {
  const [state, setState] = useState<ReviewState>({ kind: "loading" });

  const load = () => {
    setState({ kind: "loading" });
    getDesignCase(caseId)
      .then((response) =>
        setState({
          kind: "ready",
          caseDocument: response.case,
          intent: response.intent,
        }),
      )
      .catch((error: unknown) =>
        setState({ kind: "failed", failure: toActionFailure(error) }),
      );
  };

  useEffect(load, [caseId]);

  if (state.kind === "loading") {
    return (
      <p aria-live="polite" role="status">
        Loading brief review…
      </p>
    );
  }
  if (state.kind === "failed") {
    return <ProblemAlert failure={state.failure} onReload={load} />;
  }

  const intent = state.intent;
  const title = asString(state.caseDocument["title"]) ?? caseId;
  const back = (
    <p className="thread-aside">
      <Link to={`/cases/${encodeURIComponent(caseId)}`}>Back to the case</Link>
    </p>
  );

  if (intent === null) {
    return (
      <div className="convo">
        <div className="thread">
          <h1 id="page-heading">{title}</h1>
          <Moment fresh>
            <p>Nothing read yet. Interpret the brief first.</p>
          </Moment>
          {back}
        </div>
        <CaseRail caseId={caseId} caseDocument={state.caseDocument} />
      </div>
    );
  }

  const provenance = asObject(intent["provenance"]) ?? {};
  const pointers = Object.keys(provenance).sort();
  const unresolved = asArray(intent["unresolved"])
    .map(asObject)
    .filter((entry): entry is JsonObject => entry !== null);
  const confirmations = asArray(
    (asObject(intent["extensions"]) ?? {})["oak.community/confirmations"],
  )
    .map(asObject)
    .filter((entry): entry is JsonObject => entry !== null);

  return (
    <div className="convo">
      <div className="thread">
        <h1 id="page-heading">{title}</h1>
        <Moment fresh>
          <p>What I read, and where each value came from.</p>
          <p className="mono moment-meta">
            intent {asString(intent["version"])} · {asString(intent["status"])}
          </p>
        </Moment>

        <section aria-labelledby="claims-heading" className="card">
          <h2 id="claims-heading">Interpreted claims and their origin</h2>
          <div
            className="table-scroll"
            tabIndex={0}
            role="region"
            aria-label="Interpreted claims table"
          >
            <table>
              <caption className="visually-hidden">
                Interpreted intent values with provenance classification,
                materiality, confidence, and rationale
              </caption>
              <thead>
                <tr>
                  <th scope="col">Field</th>
                  <th scope="col">Value</th>
                  <th scope="col">Origin</th>
                  <th scope="col">Materiality</th>
                  <th scope="col">Rationale</th>
                </tr>
              </thead>
              <tbody>
                {pointers.map((pointer) => {
                  const entry = asObject(provenance[pointer]) ?? {};
                  const value = resolvePointer(intent, pointer);
                  const confirmedBy = asString(entry["confirmed_by"]);
                  const confidence = asNumber(entry["confidence"]);
                  return (
                    <tr key={pointer}>
                      <th scope="row">
                        <code className="pointer" title={pointer}>
                          {readablePointer(pointer)}
                        </code>
                      </th>
                      <td>
                        <pre className="value">{formatValue(value)}</pre>
                      </td>
                      <td>
                        <ClaimBadge
                          claimClass={claimClassForSource(
                            asString(entry["source"]),
                          )}
                        />
                        {confirmedBy !== null && (
                          <p className="timeline-meta">
                            confirmed by {confirmedBy} at{" "}
                            {asString(entry["confirmed_at"])}
                          </p>
                        )}
                      </td>
                      <td>
                        <MaterialityBadge
                          materiality={asString(entry["materiality"])}
                        />
                        {confidence !== null && (
                          <p className="timeline-meta">
                            confidence {confidence.toFixed(2)}
                          </p>
                        )}
                      </td>
                      <td>{asString(entry["rationale"])}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section aria-labelledby="unknowns-heading" className="card">
          <h2 id="unknowns-heading">Unknowns and open questions</h2>
          {unresolved.length === 0 ? (
            <p>Nothing unresolved.</p>
          ) : (
            <ul className="question-list">
              {unresolved.map((entry) => {
                const id = asString(entry["id"]) ?? "";
                return (
                  <li key={id}>
                    <p className="chip-row">
                      <ClaimBadge claimClass="unknown" />{" "}
                      <MaterialityBadge
                        materiality={asString(entry["materiality"])}
                      />{" "}
                      <span className="badge">{asString(entry["status"])}</span>
                    </p>
                    <p>{asString(entry["question"])}</p>
                    <p className="timeline-meta">
                      {id} · affects{" "}
                      <code title={asString(entry["path"]) ?? undefined}>
                        {readablePointer(asString(entry["path"]) ?? "")}
                      </code>
                    </p>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {confirmations.length > 0 && (
          <section aria-labelledby="confirmations-heading" className="card">
            <h2 id="confirmations-heading">Reviewer confirmations</h2>
            <ol className="timeline">
              {confirmations.map((entry, index) => (
                <li key={index}>
                  <p className="timeline-event">
                    <span className="badge">{asString(entry["decision"])}</span>{" "}
                    {asString(entry["question_id"])}
                  </p>
                  <p>{asString(entry["rationale"])}</p>
                  <p className="timeline-meta">
                    {asString(entry["actor"])} · {asString(entry["decided_at"])}
                  </p>
                </li>
              ))}
            </ol>
          </section>
        )}

        {back}
      </div>
      <CaseRail caseId={caseId} caseDocument={state.caseDocument} />
    </div>
  );
}
