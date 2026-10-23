// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

import { Moment } from "../CaseRail";
import {
  cancelOperation,
  getOperation,
  type OperationResponse,
} from "../generated/api";
import { ProblemAlert, toActionFailure, type ActionFailure } from "../problems";
import { Link } from "../router";
import { newIdempotencyKey } from "../support";
import { Keycap, Led, type LedState } from "../ui";

const TERMINAL_STATES = new Set(["succeeded", "failed", "cancelled"]);

/** The heading for each operation kind; an unknown kind is capitalised, not hidden. */
const KIND_TITLES: Readonly<Record<string, string>> = {
  generate_candidates: "Generating candidates",
  evaluate_candidate: "Evaluating a candidate",
  compile_bundle: "Compiling the bundle",
  research_catalogue: "Researching newer options",
};

function kindTitle(kind: string): string {
  const known = KIND_TITLES[kind];
  if (known !== undefined) {
    return known;
  }
  const words = kind.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
const POLL_INTERVAL_MILLISECONDS = 1500;

const LIGHTS: Readonly<Record<string, LedState>> = {
  queued: "absent",
  running: "busy",
  succeeded: "ok",
  failed: "failed",
  cancelling: "busy",
  cancelled: "revoked",
};

type OperationState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly operation: OperationResponse }
  | { readonly kind: "failed"; readonly failure: ActionFailure };

export function OperationPage({
  operationId,
}: {
  readonly operationId: string;
}) {
  const [state, setState] = useState<OperationState>({ kind: "loading" });
  const [cancelFailure, setCancelFailure] = useState<ActionFailure | null>(
    null,
  );
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    let disposed = false;
    let timer: number | undefined;

    const poll = () => {
      getOperation(operationId)
        .then((operation) => {
          if (disposed) {
            return;
          }
          setState({ kind: "ready", operation });
          if (!TERMINAL_STATES.has(operation.state)) {
            timer = window.setTimeout(poll, POLL_INTERVAL_MILLISECONDS);
          }
        })
        .catch((error: unknown) => {
          if (!disposed) {
            setState({ kind: "failed", failure: toActionFailure(error) });
          }
        });
    };

    poll();
    return () => {
      disposed = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, [operationId]);

  const onCancel = () => {
    setCancelling(true);
    setCancelFailure(null);
    cancelOperation(operationId, {
      idempotencyKey: newIdempotencyKey("cancel"),
    })
      .then((operation) => setState({ kind: "ready", operation }))
      .catch((error: unknown) => setCancelFailure(toActionFailure(error)))
      .finally(() => setCancelling(false));
  };

  if (state.kind === "loading") {
    return (
      <p aria-live="polite" role="status">
        Loading operation…
      </p>
    );
  }
  if (state.kind === "failed") {
    return (
      <ProblemAlert
        failure={state.failure}
        onReload={() => window.location.reload()}
      />
    );
  }

  const operation = state.operation;
  const terminal = TERMINAL_STATES.has(operation.state);

  return (
    <div className="convo">
      <div className="thread">
        <h1 id="page-heading">{kindTitle(operation.kind)}</h1>
        <p className="case-id">{operation.operation_id}</p>

        <Moment fresh>
          <div className="moment-row" aria-live="polite">
            <Led
              state={LIGHTS[operation.state] ?? "unknown"}
              word={operation.state}
            />
            <span className="mono moment-meta">
              attempt {operation.attempt_count} of {operation.max_attempts}
            </span>
          </div>
          {!terminal && <p role="status">Waiting for the worker to finish…</p>}
          {operation.problem !== null && (
            <div className="problem" role="alert">
              <p className="problem-title">The operation reported a problem.</p>
              <p className="problem-meta">
                {String(operation.problem["error_code"] ?? "unknown code")}
              </p>
            </div>
          )}
          {!terminal && (
            <div className="moment-row">
              <Keycap
                tone="danger"
                icon="cross"
                onClick={onCancel}
                busy={cancelling}
                busyLabel="Requesting…"
              >
                Cancel operation
              </Keycap>
            </div>
          )}
          <div aria-live="polite">
            {cancelFailure !== null && (
              <ProblemAlert
                failure={cancelFailure}
                onReload={() => window.location.reload()}
              />
            )}
          </div>
        </Moment>

        <section
          aria-labelledby="operation-heading"
          className="card card-inset"
        >
          <h2 id="operation-heading">Progress</h2>
          <dl>
            <div>
              <dt>Created</dt>
              <dd className="mono">{operation.created_at}</dd>
            </div>
            <div>
              <dt>Completed</dt>
              <dd className="mono">{operation.completed_at ?? "not yet"}</dd>
            </div>
            <div>
              <dt>Next attempt</dt>
              <dd className="mono">{operation.next_attempt_at}</dd>
            </div>
            <div>
              <dt>Correlation</dt>
              <dd className="mono">{operation.correlation_id}</dd>
            </div>
          </dl>
        </section>

        <p className="thread-aside">
          <Link to={`/cases/${encodeURIComponent(operation.case_id)}`}>
            Back to case {operation.case_id}
          </Link>
        </p>
      </div>
    </div>
  );
}
