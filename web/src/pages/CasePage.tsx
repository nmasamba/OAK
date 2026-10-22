// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

import { CaseRail, Moment } from "../CaseRail";
import {
  discoverModels,
  exportDesignCase,
  generateCandidates,
  getDesignCase,
  getJsonArtifact,
  getModels,
  interpretDesignCase,
  listAuditEvents,
  listCandidates,
  verifyModelCredential,
  type JsonObject,
  type ModelStatusResponse,
} from "../generated/api";
import { recallInterpretMode, rememberInterpretMode } from "../interpretMode";
import { ModeChooser, ModeDetail, type InterpretMode } from "../ModeSelect";
import { currentModelToken } from "../modelToken";
import { ProblemAlert, toActionFailure, type ActionFailure } from "../problems";
import { ResearchMoment } from "../ResearchMoment";
import { Link, useRouter } from "../router";
import {
  asArray,
  asNumber,
  asObject,
  asReference,
  asString,
  etagFor,
  formatBytes,
  newIdempotencyKey,
} from "../support";
import { Chip, Icon, Keycap, candidateLabel } from "../ui";

type CaseState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly caseDocument: JsonObject }
  | { readonly kind: "failed"; readonly failure: ActionFailure };

/** The brief as stored: its original name and size, read from its source record. */
interface BriefSummary {
  readonly name: string;
  readonly size: number | null;
}

const MODE_WORDS: Readonly<Record<InterpretMode, string>> = {
  deterministic: "Deterministic",
  online: "Online AI",
  local: "Local AI",
};

export function CasePage({ caseId }: { readonly caseId: string }) {
  const { navigate } = useRouter();
  const [state, setState] = useState<CaseState>({ kind: "loading" });
  const [candidates, setCandidates] = useState<readonly JsonObject[] | null>(
    null,
  );
  const [auditEvents, setAuditEvents] = useState<readonly JsonObject[]>([]);
  const [brief, setBrief] = useState<BriefSummary | null>(null);
  const [failure, setFailure] = useState<ActionFailure | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [mode, setMode] = useState<InterpretMode>(() =>
    recallInterpretMode(caseId),
  );
  const [models, setModels] = useState<ModelStatusResponse | null>(null);
  const tokenPresent = currentModelToken() !== null;

  const loadModels = () => {
    const token = currentModelToken();
    if (token === null) {
      return Promise.resolve();
    }
    return getModels(token)
      .then((status) => setModels(status))
      .catch(() => setModels(null));
  };

  // Online AI re-checks a stale token verdict and refreshes a stale catalogue before the
  // option is believed, so what it says is current whether the mode was carried in from
  // the intake form or chosen here. Both are free: the verification generates nothing and
  // the catalogue reads are anonymous.
  const refreshForOnline = (status: ModelStatusResponse | null) => {
    const token = currentModelToken();
    if (token === null || status === null) {
      return;
    }
    const online = asObject(status.modes["online"]);
    const verification =
      online === null ? null : asObject(online["verification"]);
    const catalogue = status.discovery["huggingface"];
    const refreshes: Promise<unknown>[] = [];
    if (verification === null || verification["stale"] === true) {
      refreshes.push(verifyModelCredential("huggingface", token));
    }
    if (catalogue === undefined || catalogue.stale) {
      refreshes.push(discoverModels("huggingface", token));
    }
    if (refreshes.length > 0) {
      void Promise.all(refreshes)
        .catch(() => undefined)
        .then(loadModels);
    }
  };

  useEffect(() => {
    void loadModels().then(() => {
      if (recallInterpretMode(caseId) === "online") {
        setModels((current) => {
          refreshForOnline(current);
          return current;
        });
      }
    });
  }, [caseId]);

  const chooseMode = (next: InterpretMode) => {
    setMode(next);
    rememberInterpretMode(caseId, next);
    if (next === "online") {
      refreshForOnline(models);
    }
  };

  const load = () => {
    setState({ kind: "loading" });
    setFailure(null);
    getDesignCase(caseId)
      .then((response) => {
        setState({ kind: "ready", caseDocument: response.case });
        const briefReference = asReference(
          asArray(response.case["brief_refs"])[0],
        );
        // The original name and size live on the source record, not on the brief bytes.
        const sourceRecord = asReference(
          (asObject(response.case["extensions"]) ?? {})[
            "oak.community/source_record_ref"
          ],
        );
        return Promise.all([
          listAuditEvents(caseId).then((trail) => setAuditEvents(trail.items)),
          listCandidates(caseId)
            .then((listed) => setCandidates(listed.items))
            .catch(() => setCandidates(null)),
          briefReference === null
            ? Promise.resolve()
            : sourceRecord === null
              ? Promise.resolve(
                  setBrief({ name: briefReference.id, size: null }),
                )
              : getJsonArtifact(caseId, sourceRecord)
                  .then((record) =>
                    setBrief({
                      name:
                        asString(record["original_name"]) ?? briefReference.id,
                      size: asNumber(record["size_bytes"]),
                    }),
                  )
                  .catch(() =>
                    setBrief({ name: briefReference.id, size: null }),
                  ),
        ]);
      })
      .catch((error: unknown) =>
        setState({ kind: "failed", failure: toActionFailure(error) }),
      );
  };

  useEffect(load, [caseId]);

  // A refresh in place: what the server now says, without passing through the loading
  // state (Sprint 13's refuted A-2 and A-4), so focus and the reader's place survive.
  const refresh = () => {
    setFailure(null);
    return getDesignCase(caseId)
      .then((response) => {
        setState({ kind: "ready", caseDocument: response.case });
        return Promise.all([
          listAuditEvents(caseId).then((trail) => setAuditEvents(trail.items)),
          listCandidates(caseId)
            .then((listed) => setCandidates(listed.items))
            .catch(() => setCandidates(null)),
        ]);
      })
      .catch((error: unknown) => setFailure(toActionFailure(error)));
  };

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
  const hasIntent =
    caseDocument["intent_ref"] !== null &&
    caseDocument["intent_ref"] !== undefined;
  const selected =
    caseDocument["selected_candidate_ref"] !== null &&
    caseDocument["selected_candidate_ref"] !== undefined;
  const bundleStage = [
    "assurance_planned",
    "bundle_compiled",
    "deployment_approved",
    "deployed",
    "observing",
  ].includes(status);
  const href = (suffix: string) =>
    `/cases/${encodeURIComponent(caseId)}${suffix}`;

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

  // The token is sent only when this browser has one; without it the API answers every
  // request that would spend the operator's credential with OAK-MODEL-TOKEN-REQUIRED.
  const interpretWith = (
    interpreter?: "online" | "local" | "deterministic",
  ) => {
    const token = currentModelToken();
    return runAction(
      "interpret",
      () =>
        interpretDesignCase(
          caseId,
          {
            idempotencyKey: newIdempotencyKey("interpret"),
            etag: etagFor(version),
            ...(token === null ? {} : { modelToken: token }),
          },
          interpreter,
        ),
      load,
    );
  };

  const onInterpret = () => interpretWith(mode);

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

  const onExport = () => {
    setFailure(null);
    exportDesignCase(caseId)
      .then((exported) => {
        const blob = new Blob([JSON.stringify(exported)], {
          type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `${caseId}-export.json`;
        anchor.click();
        URL.revokeObjectURL(url);
      })
      .catch((error: unknown) => setFailure(toActionFailure(error)));
  };

  return (
    <div className="convo">
      <div className="thread">
        <h1 id="page-heading">{title}</h1>

        <div className="bubble bubble-user" title="The brief, as stored">
          <Icon name="file" />
          <span className="mono">
            {brief === null ? "brief" : brief.name}
            {brief !== null && brief.size !== null
              ? ` · ${formatBytes(brief.size)}`
              : ""}
          </span>
          {status === "draft" ? (
            <span className="bubble-mode" title={`Read as ${MODE_WORDS[mode]}`}>
              <Icon name={mode} label={MODE_WORDS[mode]} />
            </span>
          ) : null}
        </div>

        {status === "draft" && (
          <Moment fresh>
            <p>Ready when you are.</p>
            <div className="moment-row">
              <ModeChooser
                id="case-mode"
                value={mode}
                onChange={chooseMode}
                status={models}
                tokenPresent={tokenPresent}
                disabled={pendingAction !== null}
              />
              <Keycap
                onClick={onInterpret}
                busy={pendingAction === "interpret"}
                busyLabel="Reading…"
                disabled={pendingAction !== null}
              >
                Interpret brief
              </Keycap>
            </div>
            <ModeDetail
              value={mode}
              status={models}
              tokenPresent={tokenPresent}
            />
          </Moment>
        )}

        {status === "needs_confirmation" && (
          <Moment fresh>
            <p>
              {openQuestions.length} check
              {openQuestions.length === 1 ? "" : "s"} before I design.
            </p>
            <p>
              <Link to={href("/confirm")} className="keycap keycap-brass">
                Answer the {openQuestions.length} ranked question
                {openQuestions.length === 1 ? "" : "s"}
              </Link>{" "}
              after{" "}
              <Link to={href("/review")}>reviewing the interpreted claims</Link>
              .
            </p>
          </Moment>
        )}

        <ResearchMoment
          caseId={caseId}
          caseDocument={caseDocument}
          disabled={pendingAction !== null}
          onChanged={refresh}
        />

        {status === "ready_for_candidates" && (
          <Moment fresh>
            <p>Ready to design.</p>
            <div className="moment-row">
              <Keycap
                onClick={onGenerateCandidates}
                busy={pendingAction === "generate"}
                busyLabel="Requesting…"
                disabled={pendingAction !== null}
              >
                Generate candidates
              </Keycap>
            </div>
          </Moment>
        )}

        {candidates !== null && candidates.length > 0 && (
          <Moment fresh={status === "candidates_ready"}>
            <p>
              {candidates.length} design{candidates.length === 1 ? "" : "s"}.{" "}
              <Link to={href("/candidates")}>Open the full comparison</Link>
              {selected ? (
                <>
                  {" "}
                  ·{" "}
                  <Link to={href("/decision")}>
                    See the decision and assurance plan
                  </Link>
                </>
              ) : null}
            </p>
            <ul className="chip-row" aria-label="Candidates">
              {candidates.map((candidate) => {
                const id = asString(candidate["id"]) ?? "";
                const feasibility =
                  asString(candidate["feasibility"]) ??
                  asString(candidate["status"]) ??
                  "unknown";
                return (
                  <li key={id}>
                    <Chip
                      small
                      tone={feasibility === "feasible" ? "ok" : "bad"}
                      icon={feasibility === "feasible" ? "check" : "cross"}
                    >
                      <span className="mono">{id}</span> ·{" "}
                      {candidateLabel(candidate)} ·{" "}
                      <span className="mono">{feasibility}</span>
                    </Chip>
                  </li>
                );
              })}
            </ul>
          </Moment>
        )}

        {bundleStage && (
          <Moment fresh={status !== "candidates_ready"}>
            <p>
              <Link
                to={href("/bundle")}
                className={
                  status === "assurance_planned" ? "keycap keycap-brass" : ""
                }
              >
                {status === "assurance_planned"
                  ? "Compile the review bundle"
                  : "Review the compiled bundle"}
              </Link>
            </p>
          </Moment>
        )}

        {hasIntent && status !== "needs_confirmation" && (
          <p className="thread-aside">
            <Link to={href("/review")}>Review the brief interpretation</Link>
          </p>
        )}

        <div aria-live="polite">
          {failure !== null && (
            <ProblemAlert
              failure={failure}
              onReload={load}
              onInterpretWithoutModel={() => interpretWith("deterministic")}
            />
          )}
        </div>

        <section aria-labelledby="audit-heading" className="card card-inset">
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
      </div>

      <CaseRail caseId={caseId} caseDocument={caseDocument}>
        <div className="rail-actions">
          <Keycap tone="quiet" icon="download" onClick={onExport}>
            Download the canonical export
          </Keycap>
          <Keycap
            tone="quiet"
            onClick={() => void refresh()}
            disabled={pendingAction !== null}
          >
            Refresh
          </Keycap>
        </div>
      </CaseRail>
    </div>
  );
}
