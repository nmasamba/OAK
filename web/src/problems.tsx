// SPDX-License-Identifier: Apache-2.0
import { OakApiError, type Problem } from "./generated/api";

export type ActionFailure =
  | { readonly kind: "conflict"; readonly problem: Problem }
  | { readonly kind: "problem"; readonly problem: Problem }
  | { readonly kind: "unreachable" };

export function toActionFailure(error: unknown): ActionFailure {
  if (error instanceof OakApiError) {
    if (error.problem.code === "OAK-EXPECTED-VERSION") {
      return { kind: "conflict", problem: error.problem };
    }
    return { kind: "problem", problem: error.problem };
  }
  return { kind: "unreachable" };
}

export function ProblemAlert({
  failure,
  onReload,
}: {
  readonly failure: ActionFailure;
  readonly onReload: () => void;
}) {
  if (failure.kind === "unreachable") {
    return (
      <div className="problem" role="alert">
        <p className="problem-title">The local OAK API is unreachable.</p>
        <p>Start the API and retry.</p>
      </div>
    );
  }
  if (failure.kind === "conflict") {
    return (
      <div className="problem" role="alert">
        <p className="problem-title">
          This case changed while you were viewing it.
        </p>
        <p>
          The server refused the action because it was based on a stale version.
          Reload to see the current state, then repeat the action if it still
          applies.
        </p>
        <button type="button" onClick={onReload}>
          Reload case
        </button>
        <p className="problem-meta">
          {failure.problem.code}
          {failure.problem.correlation_id === null
            ? ""
            : ` · ${failure.problem.correlation_id}`}
        </p>
      </div>
    );
  }
  return (
    <div className="problem" role="alert">
      <p className="problem-title">{failure.problem.title}</p>
      <p>{failure.problem.detail}</p>
      <p className="problem-meta">
        {failure.problem.code}
        {failure.problem.correlation_id === null
          ? ""
          : ` · ${failure.problem.correlation_id}`}
      </p>
    </div>
  );
}
