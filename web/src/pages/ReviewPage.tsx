// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

import { ClaimBadge, MaterialityBadge, claimClassForSource } from "../claims";
import { getDesignCase, type JsonObject } from "../generated/api";
import { formatValue, resolvePointer } from "../jsonpointer";
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

  if (intent === null) {
    return (
      <>
        <p className="eyebrow">Brief and inference review</p>
        <h1 id="page-heading">{title}</h1>
        <p className="case-id">{caseId}</p>
        <section className="panel">
          <p>
            This case has no interpreted intent yet. Interpret the brief from
            the case page first.
          </p>
          <p>
            <Link to={`/cases/${encodeURIComponent(caseId)}`}>
              Back to the case
            </Link>
          </p>
        </section>
      </>
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
    <>
      <p className="eyebrow">Brief and inference review</p>
      <h1 id="page-heading">{title}</h1>
      <p className="case-id">
        {caseId} · intent {asString(intent["version"])} ·{" "}
        {asString(intent["status"])}
      </p>

      <section aria-labelledby="claims-heading" className="panel">
        <h2 id="claims-heading">Interpreted claims and their origin</h2>
        <p className="hint">
          Every value below is labelled with how it entered the design: stated
          in the brief, inferred, supplied as a domain default, corrected by a
          reviewer, or still unknown. Inferred and default values deserve
          scrutiny before candidates are trusted.
        </p>
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
                    <code className="pointer">{pointer}</code>
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
      </section>

      <section aria-labelledby="unknowns-heading" className="panel">
        <h2 id="unknowns-heading">Unknowns and open questions</h2>
        {unresolved.length === 0 ? (
          <p>No unresolved items remain on the interpreted intent.</p>
        ) : (
          <ul className="question-list">
            {unresolved.map((entry) => {
              const id = asString(entry["id"]) ?? "";
              return (
                <li key={id}>
                  <p>
                    <ClaimBadge claimClass="unknown" />{" "}
                    <MaterialityBadge
                      materiality={asString(entry["materiality"])}
                    />{" "}
                    <span className="badge">{asString(entry["status"])}</span>
                  </p>
                  <p>{asString(entry["question"])}</p>
                  <p className="timeline-meta">
                    {id} · affects <code>{asString(entry["path"])}</code>
                  </p>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {confirmations.length > 0 && (
        <section aria-labelledby="confirmations-heading" className="panel">
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

      <p>
        <Link to={`/cases/${encodeURIComponent(caseId)}`}>
          Back to the case
        </Link>
      </p>
    </>
  );
}
