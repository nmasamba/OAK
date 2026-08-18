// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState, type FormEvent } from "react";

import { MaterialityBadge } from "../claims";
import {
  confirmDesignCase,
  getDesignCase,
  type JsonObject,
} from "../generated/api";
import { formatValue, resolvePointer } from "../jsonpointer";
import { ProblemAlert, toActionFailure, type ActionFailure } from "../problems";
import { Link, useRouter } from "../router";
import {
  asArray,
  asObject,
  asString,
  etagFor,
  newIdempotencyKey,
} from "../support";

const DECISIONS = [
  { value: "confirm", label: "Confirm the current value" },
  { value: "correct", label: "Correct it to a different value" },
  { value: "reject", label: "Reject the claim" },
  { value: "accept_risk", label: "Accept the risk of leaving it open" },
] as const;

type ConfirmState =
  | { readonly kind: "loading" }
  | {
      readonly kind: "ready";
      readonly caseDocument: JsonObject;
      readonly intent: JsonObject | null;
    }
  | { readonly kind: "failed"; readonly failure: ActionFailure };

interface AnswerDraft {
  readonly decision: string;
  readonly value: string;
  readonly rationale: string;
}

function parseValue(raw: string): unknown {
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return raw;
  }
}

export function ConfirmPage({ caseId }: { readonly caseId: string }) {
  const { navigate } = useRouter();
  const [state, setState] = useState<ConfirmState>({ kind: "loading" });
  const [drafts, setDrafts] = useState<Record<string, AnswerDraft>>({});
  const [failure, setFailure] = useState<ActionFailure | null>(null);
  const [validation, setValidation] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = () => {
    setState({ kind: "loading" });
    setFailure(null);
    setValidation(null);
    setDrafts({});
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
        Loading questions…
      </p>
    );
  }
  if (state.kind === "failed") {
    return <ProblemAlert failure={state.failure} onReload={load} />;
  }

  const caseDocument = state.caseDocument;
  const intent = state.intent;
  const version = asString(caseDocument["version"]) ?? "";
  const title = asString(caseDocument["title"]) ?? caseId;
  const status = asString(caseDocument["status"]);
  const openQuestions = asArray(caseDocument["unresolved_questions"])
    .map(asObject)
    .filter((question): question is JsonObject => question !== null)
    .filter((question) => asString(question["status"]) === "open");

  if (status !== "needs_confirmation" || openQuestions.length === 0) {
    return (
      <>
        <p className="eyebrow">Question review</p>
        <h1 id="page-heading">{title}</h1>
        <p className="case-id">{caseId}</p>
        <section className="panel">
          <p>
            This case has no open questions awaiting confirmation. Its current
            status is <span className="badge">{status}</span>.
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

  const draftFor = (questionId: string, path: string | null): AnswerDraft =>
    drafts[questionId] ?? {
      decision: "",
      value:
        intent !== null && path !== null
          ? formatValue(resolvePointer(intent, path))
          : "",
      rationale: "",
    };

  const updateDraft = (
    questionId: string,
    path: string | null,
    change: Partial<AnswerDraft>,
  ) => {
    setDrafts((current) => ({
      ...current,
      [questionId]: { ...draftFor(questionId, path), ...change },
    }));
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setValidation(null);
    setFailure(null);
    const answers: JsonObject[] = [];
    for (const question of openQuestions) {
      const id = asString(question["id"]) ?? "";
      const path = asString(question["path"]);
      const draft = draftFor(id, path);
      if (draft.decision === "") {
        continue;
      }
      if (draft.rationale.trim() === "") {
        setValidation(
          `Provide a rationale for ${id} or clear its decision before submitting.`,
        );
        return;
      }
      answers.push({
        question_id: id,
        decision: draft.decision,
        value: parseValue(draft.value),
        rationale: draft.rationale.trim(),
      } as JsonObject);
    }
    if (answers.length === 0) {
      setValidation("Choose a decision for at least one question.");
      return;
    }
    setSubmitting(true);
    confirmDesignCase(
      caseId,
      {
        answers_version: "0.1.0",
        design_case_id: caseId,
        answers,
      } as JsonObject,
      {
        idempotencyKey: newIdempotencyKey("confirm"),
        etag: etagFor(version),
      },
    )
      .then(() => navigate(`/cases/${encodeURIComponent(caseId)}`))
      .catch((error: unknown) => setFailure(toActionFailure(error)))
      .finally(() => setSubmitting(false));
  };

  return (
    <>
      <p className="eyebrow">Question review</p>
      <h1 id="page-heading">{title}</h1>
      <p className="case-id">
        {caseId} · case version {version}
      </p>

      <section aria-labelledby="questions-heading" className="panel">
        <h2 id="questions-heading">
          {openQuestions.length} ranked question
          {openQuestions.length === 1 ? "" : "s"} block this design
        </h2>
        <p className="hint">
          Decisions are recorded with your local actor identity and a value
          digest. You can answer a subset now; unanswered questions stay open
          and the case remains awaiting confirmation.
        </p>
        <form onSubmit={onSubmit}>
          <ol className="question-list">
            {openQuestions.map((question) => {
              const id = asString(question["id"]) ?? "";
              const path = asString(question["path"]);
              const draft = draftFor(id, path);
              return (
                <li key={id}>
                  <fieldset>
                    <legend>
                      {asString(question["question"])}{" "}
                      <MaterialityBadge
                        materiality={asString(question["materiality"])}
                      />
                    </legend>
                    <p className="timeline-meta">
                      {id} · affects <code>{path}</code> · blocks{" "}
                      {asString(question["blocking_stage"])}
                    </p>
                    <p className="hint">{asString(question["reason"])}</p>
                    <div
                      role="radiogroup"
                      aria-label={`Decision for ${id}`}
                      className="decision-options"
                    >
                      {DECISIONS.map((option) => (
                        <label key={option.value} className="decision-option">
                          <input
                            type="radio"
                            name={`decision-${id}`}
                            value={option.value}
                            checked={draft.decision === option.value}
                            onChange={() =>
                              updateDraft(id, path, {
                                decision: option.value,
                              })
                            }
                          />{" "}
                          {option.label}
                        </label>
                      ))}
                    </div>
                    {draft.decision !== "" && (
                      <>
                        <div className="field">
                          <label htmlFor={`value-${id}`}>
                            Value (JSON or plain text)
                          </label>
                          <textarea
                            id={`value-${id}`}
                            rows={3}
                            value={draft.value}
                            onChange={(event) =>
                              updateDraft(id, path, {
                                value: event.target.value,
                              })
                            }
                            spellCheck={false}
                          />
                        </div>
                        <div className="field">
                          <label htmlFor={`rationale-${id}`}>Rationale</label>
                          <textarea
                            id={`rationale-${id}`}
                            rows={2}
                            value={draft.rationale}
                            onChange={(event) =>
                              updateDraft(id, path, {
                                rationale: event.target.value,
                              })
                            }
                          />
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            updateDraft(id, path, { decision: "" })
                          }
                        >
                          Clear decision for this question
                        </button>
                      </>
                    )}
                  </fieldset>
                </li>
              );
            })}
          </ol>
          <div className="actions">
            <button type="submit" disabled={submitting}>
              {submitting ? "Recording decisions…" : "Record decisions"}
            </button>
          </div>
        </form>
        <div aria-live="polite">
          {validation !== null && (
            <p className="problem" role="alert">
              {validation}
            </p>
          )}
          {failure !== null && (
            <ProblemAlert failure={failure} onReload={load} />
          )}
        </div>
      </section>

      <p>
        <Link to={`/cases/${encodeURIComponent(caseId)}/review`}>
          Review the interpreted claims first
        </Link>{" "}
        ·{" "}
        <Link to={`/cases/${encodeURIComponent(caseId)}`}>
          Back to the case
        </Link>
      </p>
    </>
  );
}
