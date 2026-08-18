// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

import {
  evaluateCandidate,
  getDesignCase,
  listCandidates,
  selectCandidate,
  type JsonObject,
} from "../generated/api";
import { ProblemAlert, toActionFailure, type ActionFailure } from "../problems";
import { Link, useRouter } from "../router";
import {
  asArray,
  asNumber,
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
      readonly candidates: readonly JsonObject[];
    }
  | { readonly kind: "failed"; readonly failure: ActionFailure };

function variantOf(candidate: JsonObject): string {
  const extensions = asObject(candidate["extensions"]) ?? {};
  return (
    asString(extensions["oak.community/pattern_variant"]) ??
    asString(candidate["variant"]) ??
    "unknown"
  );
}

function objectiveNames(candidates: readonly JsonObject[]): readonly string[] {
  const names: string[] = [];
  for (const candidate of candidates) {
    for (const objective of asArray(candidate["objectives"])) {
      const name = asString(asObject(objective)?.["name"]);
      if (name !== null && !names.includes(name)) {
        names.push(name);
      }
    }
  }
  return names;
}

function objectiveFor(candidate: JsonObject, name: string): JsonObject | null {
  for (const objective of asArray(candidate["objectives"])) {
    const entry = asObject(objective);
    if (entry !== null && asString(entry["name"]) === name) {
      return entry;
    }
  }
  return null;
}

function ObjectiveCell({
  objective,
}: {
  readonly objective: JsonObject | null;
}) {
  if (objective === null) {
    return <td>—</td>;
  }
  const value = asNumber(objective["value"]);
  const lower = asNumber(objective["lower"]);
  const upper = asNumber(objective["upper"]);
  const unit = asString(objective["unit"]) ?? "";
  return (
    <td>
      <span className="objective-value">
        {value !== null ? value.toLocaleString() : "—"}
      </span>
      <span className="timeline-meta">
        {" "}
        {unit}
        {lower !== null && upper !== null && (
          <>
            {" "}
            ({lower.toLocaleString()}–{upper.toLocaleString()})
          </>
        )}
      </span>
    </td>
  );
}

function ConstraintTable({ candidate }: { readonly candidate: JsonObject }) {
  const constraints = asArray(candidate["hard_constraints"])
    .map(asObject)
    .filter((entry): entry is JsonObject => entry !== null);
  return (
    <table>
      <caption className="visually-hidden">
        Hard constraint results for {asString(candidate["id"])}
      </caption>
      <thead>
        <tr>
          <th scope="col">Constraint</th>
          <th scope="col">Result</th>
          <th scope="col">Reason</th>
          <th scope="col">Requirements</th>
        </tr>
      </thead>
      <tbody>
        {constraints.map((constraint) => {
          const id = asString(constraint["id"]) ?? "";
          const result = asString(constraint["result"]) ?? "unknown";
          return (
            <tr key={id}>
              <th scope="row">
                <code className="pointer">{id}</code>
              </th>
              <td>
                <span
                  className={`badge ${result === "pass" ? "claim-fact" : "claim-unknown"}`}
                >
                  {result}
                </span>
              </td>
              <td>{asString(constraint["reason"])}</td>
              <td>
                {asArray(constraint["requirement_ids"])
                  .map((entry) => String(entry))
                  .join(", ")}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function CandidateDetail({ candidate }: { readonly candidate: JsonObject }) {
  const topology = asObject(candidate["topology"]) ?? {};
  const nodes = asArray(topology["nodes"])
    .map(asObject)
    .filter((entry): entry is JsonObject => entry !== null);
  const extensions = asObject(candidate["extensions"]) ?? {};
  const explanation = asObject(extensions["oak.community/explanation"]) ?? {};
  const pareto = asObject(candidate["pareto"]) ?? {};
  return (
    <div className="candidate-detail">
      <h3>Hard constraints</h3>
      <ConstraintTable candidate={candidate} />
      <h3>Topology</h3>
      <ul>
        {nodes.map((node) => {
          const id = asString(node["id"]) ?? "";
          return (
            <li key={id}>
              <code className="pointer">{id}</code> — {asString(node["role"])} (
              {asString(node["component_ref"])})
            </li>
          );
        })}
      </ul>
      <h3>Pareto and sensitivity</h3>
      <p>
        {asString(pareto["sensitivity_summary"]) ?? "No sensitivity summary."}
      </p>
      <h3>Explanation</h3>
      <p className="timeline-meta">
        Satisfied requirements:{" "}
        {asArray(explanation["satisfied_requirements"])
          .map((entry) => String(entry))
          .join(", ") || "none listed"}
      </p>
      <ul>
        {asArray(explanation["uncertainties"]).map((entry, index) => (
          <li key={index}>{String(entry)}</li>
        ))}
      </ul>
      <details>
        <summary>Raw candidate document</summary>
        <pre className="value">{JSON.stringify(candidate, null, 1)}</pre>
      </details>
    </div>
  );
}

export function CandidatesPage({ caseId }: { readonly caseId: string }) {
  const { navigate } = useRouter();
  const [state, setState] = useState<PageState>({ kind: "loading" });
  const [failure, setFailure] = useState<ActionFailure | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [rationales, setRationales] = useState<Record<string, string>>({});
  const [validation, setValidation] = useState<string | null>(null);

  const load = () => {
    setState({ kind: "loading" });
    setFailure(null);
    setValidation(null);
    Promise.all([getDesignCase(caseId), listCandidates(caseId)])
      .then(([caseResponse, candidatesResponse]) =>
        setState({
          kind: "ready",
          caseDocument: caseResponse.case,
          candidates: candidatesResponse.items,
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
        Loading candidates…
      </p>
    );
  }
  if (state.kind === "failed") {
    return <ProblemAlert failure={state.failure} onReload={load} />;
  }

  const caseDocument = state.caseDocument;
  const candidates = state.candidates;
  const version = asString(caseDocument["version"]) ?? "";
  const status = asString(caseDocument["status"]) ?? "";
  const title = asString(caseDocument["title"]) ?? caseId;
  const names = objectiveNames(candidates);
  const selectable = status === "candidates_ready";

  const onEvaluate = (candidateId: string) => {
    setPending(`evaluate-${candidateId}`);
    setFailure(null);
    evaluateCandidate(caseId, candidateId, {
      idempotencyKey: newIdempotencyKey("evaluate"),
      etag: etagFor(version),
    })
      .then((operation) =>
        navigate(`/operations/${encodeURIComponent(operation.operation_id)}`),
      )
      .catch((error: unknown) => setFailure(toActionFailure(error)))
      .finally(() => setPending(null));
  };

  const onSelect = (candidateId: string) => {
    const rationale = (rationales[candidateId] ?? "").trim();
    if (rationale === "") {
      setValidation(
        `Provide a selection rationale for ${candidateId} before selecting it.`,
      );
      return;
    }
    setPending(`select-${candidateId}`);
    setFailure(null);
    setValidation(null);
    selectCandidate(
      caseId,
      { candidate_id: candidateId, rationale },
      {
        idempotencyKey: newIdempotencyKey("select"),
        etag: etagFor(version),
      },
    )
      .then(() => navigate(`/cases/${encodeURIComponent(caseId)}/decision`))
      .catch((error: unknown) => setFailure(toActionFailure(error)))
      .finally(() => setPending(null));
  };

  return (
    <>
      <p className="eyebrow">Candidate comparison</p>
      <h1 id="page-heading">{title}</h1>
      <p className="case-id">
        {caseId} · case version {version} · {status}
      </p>

      <section aria-labelledby="comparison-heading" className="panel">
        <h2 id="comparison-heading">
          {candidates.length} candidate architecture
          {candidates.length === 1 ? "" : "s"}
        </h2>
        <p className="hint">
          The simpler baseline appears first. Objective values are transparent
          estimator outputs with ranges; every raw document is inspectable
          below. Infeasible variants stay visible with their rejection reasons.
        </p>
        <div
          className="table-scroll"
          tabIndex={0}
          role="region"
          aria-label="Candidate comparison table"
        >
          <table>
            <caption className="visually-hidden">
              Candidate architectures with feasibility, Pareto status, and
              objective ranges
            </caption>
            <thead>
              <tr>
                <th scope="col">Candidate</th>
                <th scope="col">Variant</th>
                <th scope="col">Status</th>
                <th scope="col">Frontier</th>
                {names.map((name) => (
                  <th scope="col" key={name}>
                    {name.replaceAll("_", " ")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {candidates.map((candidate) => {
                const id = asString(candidate["id"]) ?? "";
                const candidateStatus = asString(candidate["status"]) ?? "";
                const pareto = asObject(candidate["pareto"]) ?? {};
                const rejections = asArray(candidate["rejection_reasons"]).map(
                  (entry) => String(entry),
                );
                return (
                  <tr key={id}>
                    <th scope="row">{id}</th>
                    <td>{variantOf(candidate)}</td>
                    <td>
                      <span
                        className={`badge ${
                          candidateStatus === "feasible"
                            ? "claim-fact"
                            : "claim-unknown"
                        }`}
                      >
                        {candidateStatus}
                      </span>
                      {rejections.length > 0 && (
                        <p className="timeline-meta">{rejections.join("; ")}</p>
                      )}
                    </td>
                    <td>
                      {pareto["frontier_member"] === true ? "member" : "—"}
                    </td>
                    {names.map((name) => (
                      <ObjectiveCell
                        key={name}
                        objective={objectiveFor(candidate, name)}
                      />
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {candidates.map((candidate) => {
        const id = asString(candidate["id"]) ?? "";
        return (
          <section
            key={id}
            aria-labelledby={`candidate-${id}-heading`}
            className="panel"
          >
            <h2 id={`candidate-${id}-heading`}>
              {id} · {variantOf(candidate)}
            </h2>
            <CandidateDetail candidate={candidate} />
            <div className="actions">
              <button
                type="button"
                onClick={() => onEvaluate(id)}
                disabled={pending !== null || !selectable}
              >
                {pending === `evaluate-${id}`
                  ? "Requesting evaluation…"
                  : "Evaluate against the contract"}
              </button>
            </div>
            {selectable && (
              <div className="field">
                <label htmlFor={`rationale-${id}`}>
                  Selection rationale for {id}
                </label>
                <textarea
                  id={`rationale-${id}`}
                  rows={2}
                  value={rationales[id] ?? ""}
                  onChange={(event) =>
                    setRationales((current) => ({
                      ...current,
                      [id]: event.target.value,
                    }))
                  }
                />
                <button
                  type="button"
                  onClick={() => onSelect(id)}
                  disabled={pending !== null}
                >
                  {pending === `select-${id}`
                    ? "Recording selection…"
                    : `Select ${id}`}
                </button>
              </div>
            )}
          </section>
        );
      })}

      <div aria-live="polite">
        {validation !== null && (
          <p className="problem" role="alert">
            {validation}
          </p>
        )}
        {failure !== null && <ProblemAlert failure={failure} onReload={load} />}
      </div>

      <p>
        <Link to={`/cases/${encodeURIComponent(caseId)}`}>
          Back to the case
        </Link>
      </p>
    </>
  );
}
