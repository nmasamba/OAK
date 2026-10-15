// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

import { CaseRail, Moment } from "../CaseRail";
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
  asReference,
  asString,
  etagFor,
  newIdempotencyKey,
} from "../support";
import { Chip, Keycap } from "../ui";

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
    <ul className="question-list owned">
      {items.map((item) => {
        const id = asString(item["id"]) ?? "";
        const itemStatus = asString(item["status"]) ?? "unknown";
        return (
          <li key={id}>
            <p className="chip-row">
              <Chip
                small
                tone={itemStatus === "satisfied" ? "ok" : "neutral"}
                icon={itemStatus === "satisfied" ? "check" : "clock"}
              >
                {itemStatus}
              </Chip>
              <span>{asString(item["description"])}</span>
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
        const extensions = asObject(caseDocument["extensions"]) ?? {};
        const decisionReference = asReference(
          extensions["oak.community/selection_decision_ref"],
        );
        const assuranceReference = asReference(
          caseDocument["assurance_plan_ref"],
        );
        const evaluationReferences = asArray(
          extensions["oak.community/evaluation_refs"],
        )
          .map(asReference)
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
  const selected = asReference(caseDocument["selected_candidate_ref"]);
  const decision = state.decision;
  const assurance = state.assurance;
  const evaluation = state.evaluation;
  const href = (suffix: string) =>
    `/cases/${encodeURIComponent(caseId)}${suffix}`;

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

  const evaluationStatus =
    evaluation === null ? null : asString(evaluation["status"]);

  return (
    <div className="convo">
      <div className="thread">
        <h1 id="page-heading">{title}</h1>

        {selected === null ? (
          <Moment fresh>
            <p>
              Nothing chosen yet.{" "}
              <Link to={href("/candidates")}>Compare the candidates</Link>
            </p>
          </Moment>
        ) : (
          <Moment fresh>
            <p>
              Selected candidate: <span className="mono">{selected.id}</span>
            </p>
            {decision !== null && (
              <>
                <p className="thread-aside">
                  {asString(decision["rationale"])}
                </p>
                <p className="timeline-meta">
                  Decided by {asString(decision["owner"])} at{" "}
                  {asString(decision["decided_at"])}
                </p>
              </>
            )}
          </Moment>
        )}

        {decision !== null && (
          <section aria-labelledby="selection-heading" className="card">
            <h2 id="selection-heading">Selection decision</h2>
            <h3>Alternatives and why they were not selected</h3>
            <ul className="question-list">
              {asArray(decision["alternatives"])
                .map(asObject)
                .filter((entry): entry is JsonObject => entry !== null)
                .map((alternative) => {
                  const reference = asReference(alternative["candidate_ref"]);
                  return (
                    <li key={reference?.id ?? ""}>
                      <p>
                        <span className="mono">{reference?.id}</span> —{" "}
                        {asString(alternative["reason"])}
                      </p>
                    </li>
                  );
                })}
            </ul>
            <details>
              <summary>Raw decision document</summary>
              <pre className="value">{JSON.stringify(decision, null, 1)}</pre>
            </details>
          </section>
        )}

        {evaluation !== null && (
          <section aria-labelledby="evaluation-heading" className="card">
            <h2 id="evaluation-heading">Evaluation evidence</h2>
            <p className="chip-row">
              <span>Contract result:</span>
              <Chip
                small
                tone={evaluationStatus === "pass" ? "ok" : "bad"}
                icon={evaluationStatus === "pass" ? "check" : "cross"}
              >
                {evaluationStatus ?? "unknown"}
              </Chip>
              <span className="timeline-meta">
                fixture {asString(evaluation["fixture_version"])}
              </span>
            </p>
            <div
              className="table-scroll"
              tabIndex={0}
              role="region"
              aria-label="Evaluation metrics table"
            >
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
                          <td className="mono">
                            {String(metric["value"])} {asString(metric["unit"])}
                          </td>
                          <td className="mono">
                            {asString(metric["direction"])}{" "}
                            {String(metric["threshold"])}
                          </td>
                          <td>
                            <Chip
                              small
                              tone={result === "pass" ? "ok" : "bad"}
                              icon={result === "pass" ? "check" : "cross"}
                            >
                              {result}
                            </Chip>
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
            {asArray(evaluation["limitations"]).length > 0 ? (
              <details>
                <summary>Limitations</summary>
                <p className="thread-aside">
                  {asArray(evaluation["limitations"])
                    .map((entry) => String(entry))
                    .join(" ")}
                </p>
              </details>
            ) : null}
          </section>
        )}

        <section aria-labelledby="assurance-heading" className="card">
          <h2 id="assurance-heading">Assurance plan</h2>
          {assurance === null ? (
            <>
              <p>No assurance plan yet.</p>
              {status === "candidate_selected" && selected !== null && (
                <div className="actions">
                  <Keycap
                    icon="shield"
                    onClick={onAssure}
                    busy={pending}
                    busyLabel="Creating…"
                  >
                    Create the assurance plan for {selected.id}
                  </Keycap>
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
                <ul className="question-list owned">
                  {asArray(assurance["gate_blockers"])
                    .map(asObject)
                    .filter((entry): entry is JsonObject => entry !== null)
                    .map((blocker, index) => (
                      <li key={index}>
                        <p className="chip-row">
                          <Chip small tone="bad" icon="warning">
                            {asString(blocker["gate"]) ?? "gate"}
                          </Chip>
                          <span>
                            {asString(blocker["description"]) ??
                              asString(blocker["reason"])}
                          </span>
                        </p>
                      </li>
                    ))}
                </ul>
              )}
              <details>
                <summary>Raw assurance plan</summary>
                <pre className="value">
                  {JSON.stringify(assurance, null, 1)}
                </pre>
              </details>
            </>
          )}
          <div aria-live="polite">
            {failure !== null && (
              <ProblemAlert failure={failure} onReload={load} />
            )}
          </div>
        </section>

        <p className="thread-aside">
          <Link to={href("/candidates")}>Back to candidates</Link> ·{" "}
          <Link to={href("")}>Back to the case</Link>
        </p>
      </div>
      <CaseRail caseId={caseId} caseDocument={caseDocument} />
    </div>
  );
}
