// SPDX-License-Identifier: Apache-2.0
import { OakApiError, type Problem } from "./generated/api";
import { Link } from "./router";

export type ActionFailure =
  | { readonly kind: "conflict"; readonly problem: Problem }
  | { readonly kind: "model"; readonly problem: Problem }
  | { readonly kind: "problem"; readonly problem: Problem }
  | { readonly kind: "unreachable" };

/** Every refusal that comes from the optional model path, rather than from OAK's own rules. */
function isModelProblem(code: string): boolean {
  return code.startsWith("OAK-MODEL-") || code.startsWith("OAK-INTERPRETER-");
}

export function toActionFailure(error: unknown): ActionFailure {
  if (error instanceof OakApiError) {
    if (error.problem.code === "OAK-EXPECTED-VERSION") {
      return { kind: "conflict", problem: error.problem };
    }
    if (isModelProblem(error.problem.code)) {
      return { kind: "model", problem: error.problem };
    }
    return { kind: "problem", problem: error.problem };
  }
  return { kind: "unreachable" };
}

export function ProblemAlert({
  failure,
  onReload,
  onInterpretWithoutModel,
}: {
  readonly failure: ActionFailure;
  readonly onReload: () => void;
  readonly onInterpretWithoutModel?: () => void;
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
  if (failure.kind === "model") {
    return (
      <div className="problem" role="alert">
        <p className="problem-title">
          The model could not interpret this brief.
        </p>
        <p>{failure.problem.detail}</p>
        <p>
          Nothing was recorded. You can interpret this brief without the model,
          or change the model settings and try again.
        </p>
        {onInterpretWithoutModel !== undefined && (
          <button type="button" onClick={onInterpretWithoutModel}>
            Interpret without the model
          </button>
        )}{" "}
        <Link to="/settings/models">Open model settings</Link>
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
