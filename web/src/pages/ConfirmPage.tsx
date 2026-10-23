// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState, type FormEvent } from "react";

import { CaseRail, Moment } from "../CaseRail";
import { ClaimBadge, MaterialityBadge, claimClassForSource } from "../claims";
import {
  confirmDesignCase,
  getDesignCase,
  type JsonObject,
} from "../generated/api";
import { formatValue, readablePointer, resolvePointer } from "../jsonpointer";
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
import { Chip, Icon, Keycap } from "../ui";

/**
 * The four decisions. `shown` is the word on the chip; `rest` completes the accessible
 * name the pins read, visually hidden, so "Confirm" is named "Confirm the current value".
 */
const DECISIONS = [
  {
    value: "confirm",
    shown: "Confirm",
    rest: " the current value",
    done: "Confirmed",
  },
  {
    value: "correct",
    shown: "Correct",
    rest: " it to a different value",
    done: "Corrected",
  },
  { value: "reject", shown: "Reject", rest: " the claim", done: "Rejected" },
  {
    value: "accept_risk",
    shown: "Accept the risk",
    rest: " of leaving it open",
    done: "Risk accepted",
  },
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

const QUESTIONS_PER_ROUND = 5;

/** A value as chips: one per scalar, one per array item, one per object field. */
function valueChips(value: unknown): readonly string[] {
  if (value === undefined || value === null) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatValue(item));
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>).map(
      ([key, item]) => `${key}: ${formatValue(item)}`,
    );
  }
  return [formatValue(value)];
}

/**
 * Where a question's current value came from.
 *
 * A question at `/spec/<section>` covers every leaf under it, so the lowest-confidence
 * model-proposed record under the path is the one worth showing: it is the claim the
 * reviewer is most likely to want to correct.
 */
function ClaimOrigin({
  intent,
  path,
}: {
  readonly intent: JsonObject | null;
  readonly path: string | null;
}) {
  if (intent === null || path === null) {
    return null;
  }
  const provenance = asObject(intent["provenance"]);
  if (provenance === null) {
    return null;
  }
  let lowest: { confidence: number; rationale: string; source: string } | null =
    null;
  for (const [recordPath, value] of Object.entries(provenance)) {
    if (recordPath !== path && !recordPath.startsWith(`${path}/`)) {
      continue;
    }
    const record = asObject(value);
    if (record === null) {
      continue;
    }
    const source = asString(record["source"]) ?? "unknown";
    const confidence = asNumber(record["confidence"]) ?? 0;
    const rationale = asString(record["rationale"]) ?? "";
    if (lowest === null || confidence < lowest.confidence) {
      lowest = { confidence, rationale, source };
    }
  }
  if (lowest === null) {
    return null;
  }
  const detail =
    lowest.source === "model_proposed"
      ? `Proposed by the model with confidence ${lowest.confidence.toFixed(2)}. ${lowest.rationale}`
      : lowest.rationale;
  return (
    <span className="question-origin" title={detail}>
      <ClaimBadge claimClass={claimClassForSource(lowest.source)} />
    </span>
  );
}

export function ConfirmPage({ caseId }: { readonly caseId: string }) {
  const { navigate } = useRouter();
  const [state, setState] = useState<ConfirmState>({ kind: "loading" });
  const [drafts, setDrafts] = useState<Record<string, AnswerDraft>>({});
  const [collapsed, setCollapsed] = useState<readonly string[]>([]);
  const [failure, setFailure] = useState<ActionFailure | null>(null);
  const [validation, setValidation] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = () => {
    setState({ kind: "loading" });
    setFailure(null);
    setValidation(null);
    setDrafts({});
    setCollapsed([]);
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
  const href = (suffix: string) =>
    `/cases/${encodeURIComponent(caseId)}${suffix}`;

  if (status !== "needs_confirmation" || openQuestions.length === 0) {
    return (
      <div className="convo">
        <div className="thread">
          <h1 id="page-heading">{title}</h1>
          <Moment fresh>
            <p>No open questions.</p>
            <p className="thread-aside">
              <Link to={href("")}>Back to the case</Link>
            </p>
          </Moment>
        </div>
        <CaseRail caseId={caseId} caseDocument={caseDocument} />
      </div>
    );
  }

  // The case persists every ranked question; a round asks five, which is also the most
  // the confirmation schema accepts in one submission.
  const presented = openQuestions.slice(0, QUESTIONS_PER_ROUND);
  const deferred = openQuestions.length - presented.length;

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

  const isAnswered = (draft: AnswerDraft) =>
    draft.decision !== "" && draft.rationale.trim() !== "";
  const answeredCount = presented.filter((question) =>
    isAnswered(
      draftFor(asString(question["id"]) ?? "", asString(question["path"])),
    ),
  ).length;
  const currentIndex = presented.findIndex((question) => {
    const id = asString(question["id"]) ?? "";
    return !collapsed.includes(id);
  });

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setValidation(null);
    setFailure(null);
    const answers: JsonObject[] = [];
    for (const question of presented) {
      const id = asString(question["id"]) ?? "";
      const path = asString(question["path"]);
      const draft = draftFor(id, path);
      if (draft.decision === "") {
        continue;
      }
      if (draft.rationale.trim() === "") {
        setValidation(`${id} needs a rationale, or clear its decision.`);
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
      .then(() => navigate(href("")))
      .catch((error: unknown) => setFailure(toActionFailure(error)))
      .finally(() => setSubmitting(false));
  };

  return (
    <div className="convo">
      <div className="thread">
        <h1 id="page-heading">{title}</h1>
        <Moment fresh>
          <p>
            {openQuestions.length} check
            {openQuestions.length === 1 ? "" : "s"} before I design.
          </p>
          <span
            role="img"
            aria-label={`Question ${Math.min(answeredCount + 1, presented.length)} of ${presented.length}`}
            className="pips"
          >
            {presented.map((question, index) => (
              <span
                key={asString(question["id"]) ?? index}
                className={
                  index < answeredCount
                    ? "pip pip-done"
                    : index === answeredCount
                      ? "pip pip-current"
                      : "pip"
                }
              />
            ))}
          </span>
        </Moment>

        <section aria-labelledby="questions-heading" className="questions">
          <h2 id="questions-heading" className="visually-hidden">
            {openQuestions.length} ranked question
            {openQuestions.length === 1 ? "" : "s"} block this design
          </h2>
          {deferred > 0 ? (
            <p className="thread-aside">
              Five per round; {deferred} more follow.
            </p>
          ) : null}
          <form onSubmit={onSubmit}>
            <ol className="question-list">
              {presented.map((question, index) => {
                const id = asString(question["id"]) ?? "";
                const path = asString(question["path"]);
                const draft = draftFor(id, path);
                const isCollapsed = collapsed.includes(id);
                const decision = DECISIONS.find(
                  (option) => option.value === draft.decision,
                );
                const chips =
                  intent !== null && path !== null
                    ? valueChips(resolvePointer(intent, path))
                    : [];
                const dataState = isCollapsed
                  ? "answered"
                  : index === currentIndex
                    ? "current"
                    : "upcoming";
                return (
                  <li key={id}>
                    <fieldset className="question" data-state={dataState}>
                      <legend>
                        {asString(question["question"])}{" "}
                        <MaterialityBadge
                          materiality={asString(question["materiality"])}
                        />
                      </legend>
                      <p className="timeline-meta">
                        {id} · affects{" "}
                        <code title={path ?? undefined}>
                          {readablePointer(path ?? "")}
                        </code>{" "}
                        · blocks {asString(question["blocking_stage"])}
                      </p>
                      {isCollapsed && decision !== undefined ? (
                        <div className="bubble bubble-reply rise">
                          <Icon name="check" />
                          <span>{decision.done}</span>
                          <button
                            type="button"
                            className="chipb"
                            onClick={() =>
                              setCollapsed((current) =>
                                current.filter((entry) => entry !== id),
                              )
                            }
                          >
                            Edit
                          </button>
                        </div>
                      ) : (
                        <>
                          <div className="chip-row question-values">
                            <ClaimOrigin intent={intent} path={path} />
                            {chips.map((chip) => (
                              <Chip key={chip} small mono>
                                {chip}
                              </Chip>
                            ))}
                          </div>
                          <details className="question-why">
                            <summary>Why it matters</summary>
                            <p>{asString(question["reason"])}</p>
                          </details>
                          <div
                            role="radiogroup"
                            aria-label={`Decision for ${id}`}
                            className="decision-chips"
                          >
                            {DECISIONS.map((option) => (
                              <label
                                key={option.value}
                                className={`chipb${draft.decision === option.value ? " chipb-on" : ""}`}
                              >
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
                                />
                                {option.shown}
                                <span className="visually-hidden">
                                  {option.rest}
                                </span>
                              </label>
                            ))}
                          </div>
                          {draft.decision !== "" && (
                            <div className="question-answer rise">
                              {draft.decision === "correct" && (
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
                              )}
                              <div className="field">
                                <label htmlFor={`rationale-${id}`}>
                                  Rationale
                                </label>
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
                              <div className="chip-row">
                                <button
                                  type="button"
                                  className="chipb"
                                  disabled={!isAnswered(draft)}
                                  onClick={() =>
                                    setCollapsed((current) => [...current, id])
                                  }
                                >
                                  Done
                                </button>
                                <button
                                  type="button"
                                  className="chipb"
                                  onClick={() =>
                                    updateDraft(id, path, { decision: "" })
                                  }
                                >
                                  Clear decision
                                </button>
                              </div>
                            </div>
                          )}
                        </>
                      )}
                    </fieldset>
                  </li>
                );
              })}
            </ol>
            <div className="actions">
              <Keycap
                type="submit"
                busy={submitting}
                busyLabel="Recording…"
                icon="check"
              >
                Record decisions
              </Keycap>
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

        <p className="thread-aside">
          <Link to={href("/review")}>Review the interpreted claims first</Link>{" "}
          · <Link to={href("")}>Back to the case</Link>
        </p>
      </div>
      <CaseRail caseId={caseId} caseDocument={caseDocument} />
    </div>
  );
}
