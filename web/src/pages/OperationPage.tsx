// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

import {
  cancelOperation,
  getOperation,
  type OperationResponse,
} from "../generated/api";
import { ProblemAlert, toActionFailure, type ActionFailure } from "../problems";
import { Link } from "../router";
import { newIdempotencyKey } from "../support";

const TERMINAL_STATES = new Set(["succeeded", "failed", "cancelled"]);
const POLL_INTERVAL_MILLISECONDS = 1500;

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
    <>
      <p className="eyebrow">Durable operation</p>
      <h1 id="page-heading">{operation.kind.replaceAll("_", " ")}</h1>
      <p className="case-id">{operation.operation_id}</p>

      <section aria-labelledby="operation-heading" className="panel">
        <h2 id="operation-heading">Progress</h2>
        <div aria-live="polite">
          <dl>
            <div>
              <dt>State</dt>
              <dd>
                <span className="badge">{operation.state}</span>
              </dd>
            </div>
            <div>
              <dt>Attempts</dt>
              <dd>
                {operation.attempt_count} of {operation.max_attempts}
              </dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd>{operation.created_at}</dd>
            </div>
            <div>
              <dt>Completed</dt>
              <dd>{operation.completed_at ?? "not yet"}</dd>
            </div>
          </dl>
          {!terminal && <p role="status">Waiting for the worker to finish…</p>}
          {operation.problem !== null && (
            <div className="problem" role="alert">
              <p className="problem-title">The operation reported a problem.</p>
              <p className="problem-meta">
                {String(operation.problem["error_code"] ?? "unknown code")}
              </p>
            </div>
          )}
        </div>
        <div className="actions">
          {!terminal && (
            <button type="button" onClick={onCancel} disabled={cancelling}>
              {cancelling ? "Requesting cancellation…" : "Cancel operation"}
            </button>
          )}
        </div>
        <div aria-live="polite">
          {cancelFailure !== null && (
            <ProblemAlert
              failure={cancelFailure}
              onReload={() => window.location.reload()}
            />
          )}
        </div>
      </section>

      <p>
        <Link to={`/cases/${encodeURIComponent(operation.case_id)}`}>
          Back to case {operation.case_id}
        </Link>
      </p>
    </>
  );
}
