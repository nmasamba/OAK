// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

import {
  generateCandidates,
  getDesignCase,
  interpretDesignCase,
  listAuditEvents,
  listCandidates,
  type JsonObject,
} from "../generated/api";
import { ProblemAlert, toActionFailure, type ActionFailure } from "../problems";
import { Link, useRouter } from "../router";
import {
  asArray,
  asObject,
  asString,
  etagFor,
  newIdempotencyKey,
} from "../support";

type CaseState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly caseDocument: JsonObject }
  | { readonly kind: "failed"; readonly failure: ActionFailure };

export function CasePage({ caseId }: { readonly caseId: string }) {
  const { navigate } = useRouter();
  const [state, setState] = useState<CaseState>({ kind: "loading" });
  const [candidates, setCandidates] = useState<readonly JsonObject[] | null>(
    null,
  );
  const [auditEvents, setAuditEvents] = useState<readonly JsonObject[]>([]);
  const [failure, setFailure] = useState<ActionFailure | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  const load = () => {
    setState({ kind: "loading" });
    setFailure(null);
    getDesignCase(caseId)
      .then((response) => {
        setState({ kind: "ready", caseDocument: response.case });
        return Promise.all([
          listAuditEvents(caseId).then((trail) => setAuditEvents(trail.items)),
          listCandidates(caseId)
            .then((listed) => setCandidates(listed.items))
            .catch(() => setCandidates(null)),
        ]);
      })
      .catch((error: unknown) =>
        setState({ kind: "failed", failure: toActionFailure(error) }),
      );
  };

  useEffect(load, [caseId]);

  if (state.kind === "loading") {
    return (
      <p aria-live="polite" role="status">
        Loading case…
      </p>
    );
  }
  if (state.kind === "failed") {
    return <ProblemAlert failure={state.failure} onReload={load} />;
  }

  const caseDocument = state.caseDocument;
  const status = asString(caseDocument["status"]) ?? "unknown";
  const version = asString(caseDocument["version"]) ?? "";
  const title = asString(caseDocument["title"]) ?? caseId;
  const questions = asArray(caseDocument["unresolved_questions"]);
  const openQuestions = questions
    .map(asObject)
    .filter((question): question is JsonObject => question !== null)
    .filter((question) => asString(question["status"]) === "open");

  const runAction = (
    action: string,
    invoke: () => Promise<unknown>,
    onDone: (result: unknown) => void,
  ) => {
    setPendingAction(action);
    setFailure(null);
    invoke()
      .then(onDone)
      .catch((error: unknown) => setFailure(toActionFailure(error)))
      .finally(() => setPendingAction(null));
  };

  const onInterpret = () =>
    runAction(
      "interpret",
      () =>
        interpretDesignCase(caseId, {
          idempotencyKey: newIdempotencyKey("interpret"),
          etag: etagFor(version),
        }),
      load,
    );

  const onGenerateCandidates = () =>
    runAction(
      "generate",
      () =>
        generateCandidates(caseId, {
          idempotencyKey: newIdempotencyKey("generate"),
          etag: etagFor(version),
        }),
      (result) => {
        const operation = asObject(result);
        const operationId =
          operation === null ? null : asString(operation["operation_id"]);
        if (operationId !== null) {
          navigate(`/operations/${encodeURIComponent(operationId)}`);
        }
      },
    );

  return (
    <>
      <p className="eyebrow">Design case</p>
      <h1 id="page-heading">{title}</h1>
      <p className="case-id">{caseId}</p>

      <section aria-labelledby="state-heading" className="panel">
        <h2 id="state-heading">Current state</h2>
        <dl>
          <div>
            <dt>Status</dt>
            <dd>
              <span className="badge">{status}</span>
            </dd>
          </div>
          <div>
            <dt>Version</dt>
            <dd>{version}</dd>
          </div>
          <div>
            <dt>Updated</dt>
            <dd>{asString(caseDocument["updated_at"])}</dd>
          </div>
          <div>
            <dt>Open questions</dt>
            <dd>{openQuestions.length}</dd>
          </div>
        </dl>
        <div className="actions">
          {status === "draft" && (
            <button
              type="button"
              onClick={onInterpret}
              disabled={pendingAction !== null}
            >
              {pendingAction === "interpret"
                ? "Interpreting…"
                : "Interpret brief"}
            </button>
          )}
          {status === "ready_for_candidates" && (
            <button
              type="button"
              onClick={onGenerateCandidates}
              disabled={pendingAction !== null}
            >
              {pendingAction === "generate"
                ? "Requesting…"
                : "Generate candidates"}
            </button>
          )}
          <button
            type="button"
            onClick={load}
            disabled={pendingAction !== null}
          >
            Refresh
          </button>
        </div>
        <div aria-live="polite">
          {failure !== null && (
            <ProblemAlert failure={failure} onReload={load} />
          )}
        </div>
        {status === "needs_confirmation" && (
          <p className="hint">
            This case needs its open questions answered.{" "}
            <Link to={`/cases/${encodeURIComponent(caseId)}/confirm`}>
              Answer the {openQuestions.length} ranked question
              {openQuestions.length === 1 ? "" : "s"}
            </Link>{" "}
            after{" "}
            <Link to={`/cases/${encodeURIComponent(caseId)}/review`}>
              reviewing the interpreted claims
            </Link>
            .
          </p>
        )}
        {caseDocument["intent_ref"] !== null &&
          caseDocument["intent_ref"] !== undefined && (
            <p className="hint">
              <Link to={`/cases/${encodeURIComponent(caseId)}/review`}>
                Review the brief interpretation
              </Link>{" "}
              to see which values are facts, inferences, defaults, or unknowns.
            </p>
          )}
      </section>

      {candidates !== null && candidates.length > 0 && (
        <section aria-labelledby="candidates-heading" className="panel">
          <h2 id="candidates-heading">Candidates</h2>
          <p className="hint">
            <Link to={`/cases/${encodeURIComponent(caseId)}/candidates`}>
              Open the full comparison
            </Link>{" "}
            for constraints, objective ranges, Pareto status, evaluation, and
            selection.
            {caseDocument["selected_candidate_ref"] !== null &&
              caseDocument["selected_candidate_ref"] !== undefined && (
                <>
                  {" "}
                  <Link to={`/cases/${encodeURIComponent(caseId)}/decision`}>
                    See the decision and assurance plan
                  </Link>
                  .
                </>
              )}
          </p>
          <table>
            <caption className="visually-hidden">
              Architecture candidates for this case
            </caption>
            <thead>
              <tr>
                <th scope="col">Candidate</th>
                <th scope="col">Variant</th>
                <th scope="col">Feasibility</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((candidate) => {
                const id = asString(candidate["id"]) ?? "";
                return (
                  <tr key={id}>
                    <th scope="row">{id}</th>
                    <td>{asString(candidate["variant"])}</td>
                    <td>
                      <span className="badge">
                        {asString(candidate["feasibility"]) ??
                          asString(candidate["status"])}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}

      <section aria-labelledby="audit-heading" className="panel">
        <h2 id="audit-heading">Audit timeline</h2>
        {auditEvents.length === 0 ? (
          <p>No audit events are recorded yet.</p>
        ) : (
          <ol className="timeline">
            {auditEvents.map((event) => {
              const sequence = String(event["sequence"]);
              return (
                <li key={sequence}>
                  <p className="timeline-event">
                    <span className="badge">
                      {asString(event["event_type"])}
                    </span>{" "}
                    case version {asString(event["case_version"])}
                  </p>
                  <p className="timeline-meta">
                    #{sequence} · {asString(event["actor"])} via{" "}
                    {asString(event["interface_origin"])} ·{" "}
                    {asString(event["occurred_at"])}
                  </p>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <p>
        <Link to="/">Back to all cases</Link>
      </p>
    </>
  );
}
