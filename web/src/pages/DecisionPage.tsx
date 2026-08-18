// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

import {
  createAssurancePlan,
  getDesignCase,
  getJsonArtifact,
  type ArtifactReference,
  type JsonObject,
} from "../generated/api";
import { ProblemAlert, toActionFailure, type ActionFailure } from "../problems";
import { Link } from "../router";
import {
  asArray,
  asObject,
  asString,
  etagFor,
  newIdempotencyKey,
} from "../support";

type PageState =
  | { readonly kind: "loading" }
  | {
      readonly kind: "ready";
      readonly caseDocument: JsonObject;
      readonly decision: JsonObject | null;
      readonly assurance: JsonObject | null;
      readonly evaluation: JsonObject | null;
    }
  | { readonly kind: "failed"; readonly failure: ActionFailure };

function toReference(value: unknown): ArtifactReference | null {
  const entry = asObject(value);
  if (entry === null) {
    return null;
  }
  const id = asString(entry["id"]);
  const version = asString(entry["version"]);
  const digest = asString(entry["digest"]);
  if (id === null || version === null || digest === null) {
    return null;
  }
  return { id, version, digest };
}

function OwnedItemList({
  items,
  label,
}: {
  readonly items: readonly JsonObject[];
  readonly label: string;
}) {
  if (items.length === 0) {
    return <p>No {label} recorded.</p>;
  }
  return (
    <ul className="question-list">
      {items.map((item) => {
        const id = asString(item["id"]) ?? "";
        const itemStatus = asString(item["status"]);
        return (
          <li key={id}>
            <p>
              <span
                className={`badge ${
                  itemStatus === "satisfied" ? "claim-fact" : "claim-inference"
                }`}
              >
                {itemStatus}
              </span>{" "}
              {asString(item["description"])}
            </p>
            <p className="timeline-meta">
              {id} · owner {asString(item["owner"]) ?? "unassigned"}
            </p>
          </li>
        );
      })}
    </ul>
  );
}

export function DecisionPage({ caseId }: { readonly caseId: string }) {
  const [state, setState] = useState<PageState>({ kind: "loading" });
  const [failure, setFailure] = useState<ActionFailure | null>(null);
  const [pending, setPending] = useState(false);

  const load = () => {
    setState({ kind: "loading" });
    setFailure(null);
    getDesignCase(caseId)
      .then(async (response) => {
        const caseDocument = response.case;
        const decisionReference = toReference(
          (asObject(caseDocument["extensions"]) ?? {})[
            "oak.community/selection_decision_ref"
          ],
        );
        const assuranceReference = toReference(
          caseDocument["assurance_plan_ref"],
        );
        const evaluationReferences = asArray(
          (asObject(caseDocument["extensions"]) ?? {})[
            "oak.community/evaluation_refs"
          ],
        )
          .map(toReference)
          .filter(
            (reference): reference is ArtifactReference => reference !== null,
          );
        const [decision, assurance, evaluation] = await Promise.all([
          decisionReference === null
            ? Promise.resolve(null)
            : getJsonArtifact(caseId, decisionReference),
          assuranceReference === null
            ? Promise.resolve(null)
            : getJsonArtifact(caseId, assuranceReference),
          evaluationReferences.length === 0
            ? Promise.resolve(null)
            : getJsonArtifact(
                caseId,
                evaluationReferences[
                  evaluationReferences.length - 1
                ] as ArtifactReference,
              ),
        ]);
        setState({
          kind: "ready",
          caseDocument,
          decision,
          assurance,
          evaluation,
        });
      })
      .catch((error: unknown) =>
        setState({ kind: "failed", failure: toActionFailure(error) }),
      );
  };

  useEffect(load, [caseId]);

  if (state.kind === "loading") {
    return (
      <p aria-live="polite" role="status">
        Loading decision…
      </p>
    );
  }
  if (state.kind === "failed") {
    return <ProblemAlert failure={state.failure} onReload={load} />;
  }

  const caseDocument = state.caseDocument;
  const version = asString(caseDocument["version"]) ?? "";
  const status = asString(caseDocument["status"]) ?? "";
  const title = asString(caseDocument["title"]) ?? caseId;
  const selected = toReference(caseDocument["selected_candidate_ref"]);
  const decision = state.decision;
  const assurance = state.assurance;
  const evaluation = state.evaluation;

  const onAssure = () => {
    if (selected === null) {
      return;
    }
    setPending(true);
    setFailure(null);
    createAssurancePlan(caseId, selected.id, {
      idempotencyKey: newIdempotencyKey("assure"),
      etag: etagFor(version),
    })
      .then(load)
      .catch((error: unknown) => setFailure(toActionFailure(error)))
      .finally(() => setPending(false));
  };

  return (
    <>
      <p className="eyebrow">Decision and assurance</p>
      <h1 id="page-heading">{title}</h1>
      <p className="case-id">
        {caseId} · case version {version} · {status}
      </p>

      <section aria-labelledby="selection-heading" className="panel">
        <h2 id="selection-heading">Selection decision</h2>
        {selected === null ? (
          <p>
            No candidate is selected yet.{" "}
            <Link to={`/cases/${encodeURIComponent(caseId)}/candidates`}>
              Compare the candidates
            </Link>{" "}
            and record a selection with its rationale.
          </p>
        ) : (
          <>
            <p>
              Selected candidate: <strong>{selected.id}</strong>
            </p>
            {decision !== null && (
              <>
                <p>{asString(decision["rationale"])}</p>
                <p className="timeline-meta">
                  Decided by {asString(decision["owner"])} at{" "}
                  {asString(decision["decided_at"])}
                </p>
                <h3>Alternatives and why they were not selected</h3>
                <ul className="question-list">
                  {asArray(decision["alternatives"])
                    .map(asObject)
                    .filter((entry): entry is JsonObject => entry !== null)
                    .map((alternative) => {
                      const reference = toReference(
                        alternative["candidate_ref"],
                      );
                      return (
                        <li key={reference?.id ?? ""}>
                          <p>
                            <strong>{reference?.id}</strong> —{" "}
                            {asString(alternative["reason"])}
                          </p>
                        </li>
                      );
                    })}
                </ul>
                <details>
                  <summary>Raw decision document</summary>
                  <pre className="value">
                    {JSON.stringify(decision, null, 1)}
                  </pre>
                </details>
              </>
            )}
          </>
        )}
      </section>

      {evaluation !== null && (
        <section aria-labelledby="evaluation-heading" className="panel">
          <h2 id="evaluation-heading">Evaluation evidence</h2>
          <p>
            Contract result:{" "}
            <span
              className={`badge ${
                asString(evaluation["status"]) === "pass"
                  ? "claim-fact"
                  : "claim-unknown"
              }`}
            >
              {asString(evaluation["status"])}
            </span>{" "}
            · fixture {asString(evaluation["fixture_version"])}
          </p>
          <table>
            <caption className="visually-hidden">
              Evaluation metrics with thresholds and results
            </caption>
            <thead>
              <tr>
                <th scope="col">Metric</th>
                <th scope="col">Value</th>
                <th scope="col">Threshold</th>
                <th scope="col">Result</th>
              </tr>
            </thead>
            <tbody>
              {asArray(evaluation["metrics"])
                .map(asObject)
                .filter((entry): entry is JsonObject => entry !== null)
                .map((metric) => {
                  const id = asString(metric["metric_id"]) ?? "";
                  const result = asString(metric["result"]) ?? "";
                  return (
                    <tr key={id}>
                      <th scope="row">
                        <code className="pointer">{id}</code>
                      </th>
                      <td>
                        {String(metric["value"])} {asString(metric["unit"])}
                      </td>
                      <td>
                        {asString(metric["direction"])}{" "}
                        {String(metric["threshold"])}
                      </td>
                      <td>
                        <span
                          className={`badge ${
                            result === "pass" ? "claim-fact" : "claim-unknown"
                          }`}
                        >
                          {result}
                        </span>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
          <p className="hint">
            {asArray(evaluation["limitations"])
              .map((entry) => String(entry))
              .join(" ")}
          </p>
        </section>
      )}

      <section aria-labelledby="assurance-heading" className="panel">
        <h2 id="assurance-heading">Assurance plan</h2>
        {assurance === null ? (
          <>
            <p>No assurance plan exists yet for this case.</p>
            {status === "candidate_selected" && selected !== null && (
              <div className="actions">
                <button type="button" onClick={onAssure} disabled={pending}>
                  {pending
                    ? "Creating assurance plan…"
                    : `Create the assurance plan for ${selected.id}`}
                </button>
              </div>
            )}
          </>
        ) : (
          <>
            <h3>Controls</h3>
            <OwnedItemList
              items={asArray(assurance["controls"])
                .map(asObject)
                .filter((entry): entry is JsonObject => entry !== null)}
              label="controls"
            />
            <h3>Required tests</h3>
            <OwnedItemList
              items={asArray(assurance["required_tests"])
                .map(asObject)
                .filter((entry): entry is JsonObject => entry !== null)}
              label="required tests"
            />
            <h3>Evidence requirements</h3>
            <OwnedItemList
              items={asArray(assurance["evidence_requirements"])
                .map(asObject)
                .filter((entry): entry is JsonObject => entry !== null)}
              label="evidence requirements"
            />
            <h3>Gate blockers</h3>
            {asArray(assurance["gate_blockers"]).length === 0 ? (
              <p>No gate blockers are recorded.</p>
            ) : (
              <ul className="question-list">
                {asArray(assurance["gate_blockers"])
                  .map(asObject)
                  .filter((entry): entry is JsonObject => entry !== null)
                  .map((blocker, index) => (
                    <li key={index}>
                      <p>
                        <span className="badge claim-unknown">
                          {asString(blocker["gate"]) ?? "gate"}
                        </span>{" "}
                        {asString(blocker["description"]) ??
                          asString(blocker["reason"])}
                      </p>
                    </li>
                  ))}
              </ul>
            )}
            <details>
              <summary>Raw assurance plan</summary>
              <pre className="value">{JSON.stringify(assurance, null, 1)}</pre>
            </details>
          </>
        )}
        <div aria-live="polite">
          {failure !== null && (
            <ProblemAlert failure={failure} onReload={load} />
          )}
        </div>
      </section>

      <p>
        <Link to={`/cases/${encodeURIComponent(caseId)}/candidates`}>
          Back to candidates
        </Link>{" "}
        ·{" "}
        <Link to={`/cases/${encodeURIComponent(caseId)}`}>
          Back to the case
        </Link>
      </p>
    </>
  );
}
