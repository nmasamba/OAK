// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";

import { Moment } from "./CaseRail";
import {
  getJsonArtifact,
  getOperation,
  researchCatalogue,
  researchPlan,
  reviewResearchItem,
  type ArtifactReference,
  type JsonObject,
  type OperationResponse,
  type ResearchPlanResponse,
} from "./generated/api";
import { currentModelToken } from "./modelToken";
import { ProblemAlert, toActionFailure, type ActionFailure } from "./problems";
import {
  RESEARCH_REVIEW_REFS,
  RESEARCH_SNAPSHOT_REF,
  TIER_WORDS,
  VERDICT_WORDS,
  dateWord,
  effectiveVerdict,
  evidenceWord,
  kindWord,
  sourceWord,
} from "./research";
import { Link } from "./router";
import {
  asArray,
  asNumber,
  asObject,
  asReference,
  asString,
  etagFor,
  newIdempotencyKey,
} from "./support";
import { Chip, Keycap } from "./ui";

const TERMINAL_STATES = new Set(["succeeded", "failed", "cancelled"]);
const POLL_INTERVAL_MILLISECONDS = 1500;

/** The problem a failed research operation recorded, as the page shows every refusal. */
function operationFailure(operation: OperationResponse): ActionFailure {
  const problem = asObject(operation.problem);
  if (problem === null) {
    return { kind: "unreachable" };
  }
  return {
    kind: "problem",
    problem: {
      type: asString(problem["type"]) ?? "about:blank",
      title: asString(problem["title"]) ?? "Research did not finish",
      status: asNumber(problem["status"]) ?? 500,
      code: asString(problem["code"]) ?? "OAK-RESEARCH-FAILED",
      detail: asString(problem["detail"]) ?? "",
      correlation_id: asString(problem["correlation_id"]),
      retriable: problem["retriable"] === true,
      errors: [],
    },
  };
}

function slugOf(id: string): string {
  return id.replace(/[^A-Za-z0-9_-]+/g, "-");
}

/**
 * The Research moment of a case (ADR-0018). At `ready_for_candidates` it asks "Look for
 * newer options?" and shows, verbatim, what one research run would send and to whom;
 * the run needs the capability token and a consent that names exactly that. Once the
 * case holds a snapshot it shows what came back: found, passed and needing review, each
 * item with the evidence class of every claim, and a recorded review for an unvetted
 * item. The run is watched in place and the result rises here; after a change, focus
 * moves to it and it is announced. Nothing here selects, approves or installs anything.
 */
export function ResearchMoment({
  caseId,
  caseDocument,
  disabled,
  onChanged,
}: {
  readonly caseId: string;
  readonly caseDocument: JsonObject;
  /** Another action is in flight on the page. */
  readonly disabled: boolean;
  /** The case changed on the server; the page refreshes in place. */
  readonly onChanged: () => Promise<unknown>;
}) {
  const status = asString(caseDocument["status"]) ?? "";
  const version = asString(caseDocument["version"]) ?? "";
  const extensions = asObject(caseDocument["extensions"]) ?? {};
  const snapshotRef = asReference(extensions[RESEARCH_SNAPSHOT_REF]);
  const reviewRefs = asArray(extensions[RESEARCH_REVIEW_REFS])
    .map(asReference)
    .filter((entry): entry is ArtifactReference => entry !== null);
  const reviewKey = reviewRefs.map((entry) => entry.digest).join(",");
  const atDesign = status === "ready_for_candidates";
  const tokenPresent = currentModelToken() !== null;

  const [plan, setPlan] = useState<ResearchPlanResponse | null>(null);
  const [planFailure, setPlanFailure] = useState<ActionFailure | null>(null);
  const [snapshot, setSnapshot] = useState<JsonObject | null>(null);
  const [reviews, setReviews] = useState<readonly JsonObject[]>([]);
  const [operation, setOperation] = useState<OperationResponse | null>(null);
  const [failure, setFailure] = useState<ActionFailure | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [rationales, setRationales] = useState<Record<string, string>>({});
  const [validation, setValidation] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState<string | null>(null);
  const summary = useRef<HTMLParagraphElement>(null);
  const focusResults = useRef(false);
  const focusItem = useRef<string | null>(null);

  // The plan while there is nothing to show; the snapshot once the case holds one.
  useEffect(() => {
    let disposed = false;
    if (snapshotRef !== null) {
      getJsonArtifact(caseId, snapshotRef)
        .then((document) => {
          if (!disposed) {
            setSnapshot(document);
            setPlan(null);
          }
        })
        .catch((error: unknown) => {
          if (!disposed) {
            setFailure(toActionFailure(error));
          }
        });
    } else if (atDesign) {
      setSnapshot(null);
      researchPlan(caseId)
        .then((response) => {
          if (!disposed) {
            setPlan(response);
            setPlanFailure(null);
          }
        })
        .catch((error: unknown) => {
          if (!disposed) {
            setPlan(null);
            setPlanFailure(toActionFailure(error));
          }
        });
    }
    return () => {
      disposed = true;
    };
  }, [caseId, snapshotRef?.id, snapshotRef?.digest, atDesign]);

  useEffect(() => {
    let disposed = false;
    if (reviewRefs.length === 0) {
      setReviews([]);
      return;
    }
    Promise.all(
      reviewRefs.map((reference) => getJsonArtifact(caseId, reference)),
    )
      .then((documents) => {
        if (!disposed) {
          setReviews(documents);
        }
      })
      .catch(() => undefined);
    return () => {
      disposed = true;
    };
  }, [caseId, reviewKey]);

  // The run is watched here, in place: no navigation and no loading state.
  useEffect(() => {
    if (operation === null || TERMINAL_STATES.has(operation.state)) {
      return;
    }
    let disposed = false;
    const timer = window.setTimeout(() => {
      getOperation(operation.operation_id)
        .then((next) => {
          if (disposed) {
            return;
          }
          setOperation(next);
          if (next.state === "succeeded") {
            focusResults.current = true;
            setAnnouncement("Research finished.");
            void onChanged();
          } else if (next.state === "failed" || next.state === "cancelled") {
            setFailure(operationFailure(next));
          }
        })
        .catch((error: unknown) => {
          if (!disposed) {
            setFailure(toActionFailure(error));
          }
        });
    }, POLL_INTERVAL_MILLISECONDS);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [operation]);

  // After a change, focus moves to the result (Sprint 13's refuted A-2, A-4 and A-5).
  useEffect(() => {
    if (snapshot !== null && focusResults.current) {
      focusResults.current = false;
      summary.current?.focus();
    }
  }, [snapshot]);
  useEffect(() => {
    const id = focusItem.current;
    if (id === null) {
      return;
    }
    focusItem.current = null;
    document.getElementById(`research-item-${slugOf(id)}`)?.focus();
  }, [reviews]);

  const onRun = () => {
    const token = currentModelToken();
    if (plan === null || token === null) {
      return;
    }
    setPending("research");
    setFailure(null);
    setValidation(null);
    researchCatalogue(
      caseId,
      { hosts: plan.hosts, terms_digest: plan.terms_digest },
      token,
      { idempotencyKey: newIdempotencyKey("research"), etag: etagFor(version) },
    )
      .then((started) => setOperation(started))
      .catch((error: unknown) => setFailure(toActionFailure(error)))
      .finally(() => setPending(null));
  };

  const onReview = (item: JsonObject, decision: "accept" | "reject") => {
    const itemId = asString(item["id"]);
    if (itemId === null) {
      return;
    }
    const sourceId = asString(item["source_id"]) ?? itemId;
    const rationale = (rationales[itemId] ?? "").trim();
    if (rationale === "") {
      setValidation(
        `${sourceId} needs a rationale before a decision is recorded.`,
      );
      return;
    }
    setPending(`review-${itemId}`);
    setFailure(null);
    setValidation(null);
    reviewResearchItem(
      caseId,
      { item_id: itemId, decision, rationale },
      { idempotencyKey: newIdempotencyKey("review"), etag: etagFor(version) },
    )
      .then((response) => {
        setReviews((current) => [
          ...current.filter((entry) => asString(entry["item_id"]) !== itemId),
          response.review,
        ]);
        setAnnouncement(
          `Review recorded: ${sourceId} ${
            decision === "accept" ? "accepted for comparison" : "rejected"
          }.`,
        );
        focusItem.current = itemId;
        return onChanged();
      })
      .catch((error: unknown) => setFailure(toActionFailure(error)))
      .finally(() => setPending(null));
  };

  const running = operation !== null && !TERMINAL_STATES.has(operation.state);
  const notices = (
    <div aria-live="polite" className="research-notices">
      {announcement !== null && (
        <p role="status" className="timeline-meta">
          {announcement}
        </p>
      )}
      {validation !== null && (
        <p className="problem" role="alert">
          {validation}
        </p>
      )}
      {failure !== null && (
        <ProblemAlert failure={failure} onReload={() => void onChanged()} />
      )}
    </div>
  );

  if (snapshot === null) {
    if (!atDesign) {
      return null;
    }
    return (
      <Moment fresh>
        <p>Look for newer options?</p>
        {plan === null ? (
          planFailure !== null ? (
            <p className="timeline-meta">
              Research is not available here
              {planFailure.kind === "unreachable"
                ? "."
                : `: ${planFailure.problem.detail}`}
            </p>
          ) : (
            <p role="status" className="timeline-meta">
              Reading what research would send…
            </p>
          )
        ) : (
          <section
            aria-labelledby="research-consent-heading"
            className="card card-inset research-consent"
          >
            <h2 id="research-consent-heading">What research would send</h2>
            {plan.hosts.length === 0 ? (
              <p>
                No host: the fixture source answers from files on this machine
                (source mode <span className="mono">{plan.source_mode}</span>
                ).
              </p>
            ) : (
              <>
                <p>
                  Anonymous requests to these hosts, carrying the terms below
                  and nothing else:
                </p>
                <ul className="chip-row" aria-label="Hosts">
                  {plan.hosts.map((host) => (
                    <li key={host}>
                      <Chip small mono icon="online">
                        {host}
                      </Chip>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <p className="timeline-meta" id="research-terms-label">
              Terms, verbatim
            </p>
            <pre
              className="value research-terms"
              aria-labelledby="research-terms-label"
            >
              {JSON.stringify(
                asObject(plan.terms["sent"]) ?? plan.terms,
                null,
                1,
              )}
            </pre>
            <details>
              <summary>Filters applied on this machine only</summary>
              <pre className="value research-terms">
                {JSON.stringify(asObject(plan.terms["local"]) ?? {}, null, 1)}
              </pre>
            </details>
            <p className="timeline-meta">
              Terms digest <span className="mono">{plan.terms_digest}</span>
            </p>
            <div className="moment-row">
              <Keycap
                tone="quiet"
                icon="search"
                onClick={onRun}
                busy={pending === "research" || running}
                busyLabel="Researching…"
                disabled={
                  disabled || pending !== null || !tokenPresent || !plan.allowed
                }
              >
                Run research
              </Keycap>
              {!tokenPresent && (
                <span className="timeline-meta">
                  Needs the model-configuration token:{" "}
                  <Link to="/settings">paste it in Settings</Link>.
                </span>
              )}
            </div>
            {running && (
              <p role="status" className="timeline-meta">
                Asking the sources… this runs once, within its budget.
              </p>
            )}
          </section>
        )}
        {notices}
      </Moment>
    );
  }

  const items = asArray(snapshot["items"])
    .map(asObject)
    .filter((entry): entry is JsonObject => entry !== null);
  const verdicts = items.map((item) => effectiveVerdict(item, reviews));
  const found = items.length;
  const passed = verdicts.filter((entry) => entry.verdict === "passed").length;
  const needs = verdicts.filter(
    (entry) => entry.verdict === "needs_review",
  ).length;
  const sourceMode = asString(snapshot["source_mode"]);
  const budget = asObject(snapshot["budget"]) ?? {};
  const requestsUsed = asNumber(budget["requests_used"]);
  const requestsMax = asNumber(budget["requests_max"]);

  return (
    <Moment fresh={atDesign}>
      <p ref={summary} tabIndex={-1} className="research-summary">
        Research done {dateWord(asString(snapshot["occurred_at"]))}
        {sourceMode === "fixture" ? " from the fixture source" : ""}
        {requestsUsed !== null && requestsMax !== null
          ? `, ${requestsUsed} of ${requestsMax} requests`
          : ""}
        .
      </p>
      <div className="research">
        <ul className="chip-row" aria-label="Research results">
          <li>
            <Chip small icon="search">
              {found} found
            </Chip>
          </li>
          <li>
            <Chip small tone="ok" icon="check">
              {passed} passed
            </Chip>
          </li>
          <li>
            <Chip
              small
              tone={needs > 0 ? "unknown" : "neutral"}
              icon={needs > 0 ? "warning" : "check"}
            >
              {needs} {needs === 1 ? "needs" : "need"} your review
            </Chip>
          </li>
        </ul>
        <ul className="research-items" aria-label="Researched items">
          {items.map((item, index) => {
            const id = asString(item["id"]) ?? `item-${index}`;
            const sourceId = asString(item["source_id"]) ?? id;
            const effective = verdicts[index] ?? {
              verdict: "failed",
              reviewed: false,
            };
            const tier = asString(item["tier"]);
            const reasons = asArray(item["reasons"])
              .map(asString)
              .filter((entry): entry is string => entry !== null);
            const claims = asArray(item["claims"])
              .map(asObject)
              .filter((entry): entry is JsonObject => entry !== null);
            const canReview =
              atDesign &&
              effective.verdict === "needs_review" &&
              !effective.reviewed;
            const verdictWord = effective.reviewed
              ? effective.verdict === "passed"
                ? "Accepted by you"
                : "Rejected by you"
              : (VERDICT_WORDS[effective.verdict] ?? effective.verdict);
            const tone =
              effective.verdict === "passed"
                ? "ok"
                : effective.verdict === "needs_review"
                  ? "unknown"
                  : "bad";
            const icon =
              effective.verdict === "passed"
                ? "check"
                : effective.verdict === "needs_review"
                  ? "warning"
                  : "cross";
            const slug = slugOf(id);
            return (
              <li
                key={id}
                id={`research-item-${slug}`}
                tabIndex={-1}
                className="research-item"
                aria-label={sourceId}
              >
                <p className="research-item-head">
                  <span className="mono">{sourceId}</span>
                  <Chip small tone={tone} icon={icon}>
                    {verdictWord}
                  </Chip>
                </p>
                <p className="timeline-meta">
                  {kindWord(asString(item["kind"]))} ·{" "}
                  {sourceWord(asString(item["source"]))} ·{" "}
                  {tier === null ? "Unknown tier" : (TIER_WORDS[tier] ?? tier)}{" "}
                  · {dateWord(asString(item["created_or_released_at"]))}
                </p>
                {reasons.length > 0 && (
                  <p className="timeline-meta">
                    {reasons.map((reason) => (
                      <code key={reason} className="pointer research-reason">
                        {reason}
                      </code>
                    ))}
                  </p>
                )}
                <details>
                  <summary>Claims</summary>
                  <table>
                    <caption className="visually-hidden">
                      What the source says about {sourceId}, each claim with its
                      evidence class
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">Field</th>
                        <th scope="col">Value</th>
                        <th scope="col">Evidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {claims.map((claim, claimIndex) => {
                        const unit = asString(claim["unit"]);
                        return (
                          <tr key={claimIndex}>
                            <th scope="row">
                              {(asString(claim["field"]) ?? "").replaceAll(
                                "_",
                                " ",
                              )}
                            </th>
                            <td className="mono">
                              {String(claim["value"] ?? "")}
                              {unit === null ? "" : ` ${unit}`}
                            </td>
                            <td>
                              {evidenceWord(asString(claim["evidence_class"]))}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </details>
                {canReview && (
                  <div className="field">
                    <label htmlFor={`rationale-${slug}`}>
                      Rationale for {sourceId}
                    </label>
                    <textarea
                      id={`rationale-${slug}`}
                      rows={2}
                      value={rationales[id] ?? ""}
                      onChange={(event) =>
                        setRationales((current) => ({
                          ...current,
                          [id]: event.target.value,
                        }))
                      }
                    />
                    <div className="actions">
                      <Keycap
                        tone="quiet"
                        icon="check"
                        onClick={() => onReview(item, "accept")}
                        busy={pending === `review-${id}`}
                        busyLabel="Recording…"
                        disabled={disabled || pending !== null}
                      >
                        Accept for comparison
                      </Keycap>
                      <Keycap
                        tone="quiet"
                        icon="cross"
                        onClick={() => onReview(item, "reject")}
                        disabled={disabled || pending !== null}
                      >
                        Reject
                      </Keycap>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
        {notices}
      </div>
    </Moment>
  );
}
