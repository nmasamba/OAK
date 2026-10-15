// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState, type DragEvent, type KeyboardEvent } from "react";

import { CaseRail, Moment } from "../CaseRail";
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
  asReference,
  asString,
  etagFor,
  newIdempotencyKey,
} from "../support";
import {
  Chip,
  Icon,
  Keycap,
  RangeBar,
  candidateLabel,
  formatQuantity,
  type IconName,
} from "../ui";

type PageState =
  | { readonly kind: "loading" }
  | {
      readonly kind: "ready";
      readonly caseDocument: JsonObject;
      readonly candidates: readonly JsonObject[];
    }
  | { readonly kind: "failed"; readonly failure: ActionFailure };

type View = "cards" | "table";

/** The objectives the cards draw as bars, with the word and glyph for each. */
const BAR_OBJECTIVES: readonly {
  readonly name: string;
  readonly word: string;
  readonly icon: IconName;
}[] = [
  { name: "quality", word: "Quality", icon: "star" },
  { name: "latency_p95", word: "Latency", icon: "clock" },
  { name: "energy", word: "Energy", icon: "bolt" },
];

const BENCH_OBJECTIVES: readonly {
  readonly name: string;
  readonly word: string;
  readonly icon: IconName;
}[] = [
  ...BAR_OBJECTIVES,
  { name: "monthly_cost", word: "Monthly cost", icon: "coin" },
];

const UNITS: Readonly<Record<string, string>> = {
  milliseconds: "ms",
  "Wh/request": "Wh",
  "USD/month": "USD/mo",
  normalized_fixture_score: "",
  components: "",
};

function unitWord(unit: string | null): string {
  return unit === null ? "" : (UNITS[unit] ?? unit);
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

/** One scale per objective across every candidate, so the bars compare. */
function scales(
  candidates: readonly JsonObject[],
): Readonly<Record<string, { readonly min: number; readonly max: number }>> {
  const result: Record<string, { min: number; max: number }> = {};
  for (const candidate of candidates) {
    for (const objective of asArray(candidate["objectives"])) {
      const entry = asObject(objective);
      const name = entry === null ? null : asString(entry["name"]);
      if (entry === null || name === null) {
        continue;
      }
      for (const key of ["lower", "upper", "value"]) {
        const value = asNumber(entry[key]);
        if (value === null) {
          continue;
        }
        const current = result[name] ?? { min: value, max: value };
        result[name] = {
          min: Math.min(current.min, value),
          max: Math.max(current.max, value),
        };
      }
    }
  }
  return result;
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
  const unit = unitWord(asString(objective["unit"]));
  return (
    <td>
      <span className="objective-value">{formatQuantity(value)}</span>
      <span className="timeline-meta">
        {" "}
        {unit}
        {lower !== null && upper !== null && (
          <>
            {" "}
            ({formatQuantity(lower)}–{formatQuantity(upper)})
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
                <Chip
                  small
                  tone={result === "pass" ? "ok" : "bad"}
                  icon={result === "pass" ? "check" : "cross"}
                >
                  {result}
                </Chip>
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

// An explanation entry is a constraint outcome — constraint_id, reason and, for a satisfied
// one, requirement_ids — so it is listed by those fields, never stringified whole.
function ExplanationList({
  labelId,
  label,
  entries,
}: {
  readonly labelId: string;
  readonly label: string;
  readonly entries: unknown;
}) {
  const items = asArray(entries)
    .map(asObject)
    .filter((entry): entry is JsonObject => entry !== null);
  if (items.length === 0) {
    return (
      <p className="timeline-meta explanation-label">{label}: none listed</p>
    );
  }
  return (
    <>
      <p className="timeline-meta explanation-label" id={labelId}>
        {label}
      </p>
      <ul aria-labelledby={labelId} className="explanation">
        {items.map((item, index) => {
          const reason = asString(item["reason"]);
          const requirementIds = asArray(item["requirement_ids"])
            .map(asString)
            .filter((entry): entry is string => entry !== null);
          return (
            <li key={index}>
              <code className="pointer">
                {asString(item["constraint_id"]) ?? "unnamed constraint"}
              </code>
              {reason !== null && <> — {reason}</>}
              {requirementIds.length > 0 && (
                <span className="timeline-meta explanation-requirements">
                  Requirements: {requirementIds.join(", ")}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}

/** The topology as a glyph: one box per node, joined in a row. Decoration only. */
function TopologyGlyph({
  candidate,
  infeasible,
}: {
  readonly candidate: JsonObject;
  readonly infeasible: boolean;
}) {
  const nodes = asArray((asObject(candidate["topology"]) ?? {})["nodes"]);
  const count = Math.max(1, Math.min(nodes.length, 5));
  return (
    <div
      className={`glyph${infeasible ? " glyph-infeasible" : ""}`}
      aria-hidden="true"
    >
      {Array.from({ length: count }, (_, index) => (
        <span key={index} className="glyph-node">
          {index < count - 1 ? <span className="glyph-edge" /> : null}
        </span>
      ))}
    </div>
  );
}

function sign(value: number): string {
  return value > 0 ? `+${formatQuantity(value)}` : formatQuantity(value);
}

export function CandidatesPage({ caseId }: { readonly caseId: string }) {
  const { navigate } = useRouter();
  const [state, setState] = useState<PageState>({ kind: "loading" });
  const [failure, setFailure] = useState<ActionFailure | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [rationales, setRationales] = useState<Record<string, string>>({});
  const [validation, setValidation] = useState<string | null>(null);
  const [view, setView] = useState<View>("cards");
  const [bench, setBench] = useState<readonly string[]>([]);
  const [dragging, setDragging] = useState<string | null>(null);
  const [overBench, setOverBench] = useState(false);

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
  const scale = scales(candidates);
  const selectable = status === "candidates_ready";
  const chosenId =
    asReference(caseDocument["selected_candidate_ref"])?.id ?? null;
  const feasible = candidates.filter(
    (candidate) => asString(candidate["status"]) !== "infeasible",
  ).length;
  const href = (suffix: string) =>
    `/cases/${encodeURIComponent(caseId)}${suffix}`;

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
      setValidation(`${candidateId} needs a selection rationale.`);
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
      .then(() => navigate(href("/decision")))
      .catch((error: unknown) => setFailure(toActionFailure(error)))
      .finally(() => setPending(null));
  };

  // The bench holds two designs side by side. A grip toggles a design on or off it;
  // with the grip focused, the arrow keys move a benched design left or right.
  const toggleBench = (id: string) => {
    setBench((current) =>
      current.includes(id)
        ? current.filter((entry) => entry !== id)
        : [...current.slice(-1), id],
    );
  };
  const moveOnBench = (id: string, direction: -1 | 1) => {
    setBench((current) => {
      const index = current.indexOf(id);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= current.length) {
        return current;
      }
      const next = [...current];
      const other = next[target];
      if (other === undefined) {
        return current;
      }
      next[target] = id;
      next[index] = other;
      return next;
    });
  };
  const onGripKey = (id: string, event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      moveOnBench(id, -1);
    } else if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      moveOnBench(id, 1);
    }
  };
  const onDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    setOverBench(false);
    const id = event.dataTransfer.getData("text/plain");
    if (id !== "" && !bench.includes(id)) {
      toggleBench(id);
    }
    setDragging(null);
  };
  const benched = bench
    .map((id) =>
      candidates.find((candidate) => asString(candidate["id"]) === id),
    )
    .filter((candidate): candidate is JsonObject => candidate !== undefined);
  const [left, right] = benched;

  return (
    <div className="convo">
      <div className="thread">
        <h1 id="page-heading">{title}</h1>
        <Moment fresh>
          <div className="moment-row">
            <p>
              {candidates.length} design{candidates.length === 1 ? "" : "s"}.{" "}
              {feasible} fit.
            </p>
            <span className="spacer" />
            <div role="group" aria-label="View" className="view-group">
              <button
                type="button"
                className="ico"
                aria-label="Cards"
                aria-pressed={view === "cards"}
                onClick={() => setView("cards")}
              >
                <Icon name="cards" size={18} />
              </button>
              <button
                type="button"
                className="ico"
                aria-label="Table"
                aria-pressed={view === "table"}
                onClick={() => setView("table")}
              >
                <Icon name="table" size={18} />
              </button>
            </div>
          </div>
        </Moment>

        <h2 id="comparison-heading" className="designs-heading">
          {candidates.length} candidate architecture
          {candidates.length === 1 ? "" : "s"}
        </h2>

        {view === "table" ? (
          <div
            className="table-scroll card"
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
                  const rejections = asArray(
                    candidate["rejection_reasons"],
                  ).map((entry) => String(entry));
                  return (
                    <tr key={id}>
                      <th scope="row">
                        <code className="mono">{id}</code>
                      </th>
                      <td>{candidateLabel(candidate)}</td>
                      <td>
                        <Chip
                          small
                          tone={candidateStatus === "infeasible" ? "bad" : "ok"}
                          icon={
                            candidateStatus === "infeasible" ? "cross" : "check"
                          }
                        >
                          {candidateStatus}
                        </Chip>
                        {rejections.length > 0 && (
                          <p className="timeline-meta">
                            {rejections.join("; ")}
                          </p>
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
        ) : null}

        <div className={`designs${view === "table" ? " designs-details" : ""}`}>
          {candidates.map((candidate) => {
            const id = asString(candidate["id"]) ?? "";
            const candidateStatus = asString(candidate["status"]) ?? "";
            const infeasible = candidateStatus === "infeasible";
            const onBench = bench.includes(id);
            const chosen = chosenId === id;
            const rejections = asArray(candidate["rejection_reasons"]).map(
              (entry) => String(entry),
            );
            const topology = asObject(candidate["topology"]) ?? {};
            const nodes = asArray(topology["nodes"])
              .map(asObject)
              .filter((entry): entry is JsonObject => entry !== null);
            const extensions = asObject(candidate["extensions"]) ?? {};
            const explanation =
              asObject(extensions["oak.community/explanation"]) ?? {};
            const pareto = asObject(candidate["pareto"]) ?? {};
            const tone = infeasible
              ? "design-infeasible"
              : chosen
                ? "design-chosen"
                : onBench
                  ? "design-benched"
                  : "";
            return (
              <section
                key={id}
                aria-labelledby={`candidate-${id}-heading`}
                className={`design card card-lift ${tone}${dragging === id ? " card-dragging" : ""}`}
                draggable={!infeasible}
                onDragStart={(event) => {
                  event.dataTransfer.setData("text/plain", id);
                  event.dataTransfer.effectAllowed = "move";
                  setDragging(id);
                }}
                onDragEnd={() => setDragging(null)}
              >
                <div className="design-head">
                  <h2 id={`candidate-${id}-heading`} className="design-title">
                    <span className="mono design-id">{id}</span>
                    <span className="design-name">
                      {candidateLabel(candidate)}
                    </span>
                  </h2>
                  {infeasible ? (
                    <Chip small tone="bad" icon="cross">
                      {candidateStatus}
                    </Chip>
                  ) : (
                    <button
                      type="button"
                      className="grip"
                      aria-label={`Drag ${id} to the bench`}
                      aria-pressed={onBench}
                      title="Space picks up or drops; arrows move it on the bench"
                      onClick={() => toggleBench(id)}
                      onKeyDown={(event) => onGripKey(id, event)}
                    >
                      <Icon name="grip" size={18} />
                    </button>
                  )}
                </div>
                <TopologyGlyph candidate={candidate} infeasible={infeasible} />
                {infeasible ? (
                  <p className="design-reason">
                    {rejections.length > 0
                      ? rejections.join(" ")
                      : "Infeasible."}
                  </p>
                ) : (
                  <div className="design-bars">
                    {BAR_OBJECTIVES.map(({ name, word }) => {
                      const objective = objectiveFor(candidate, name);
                      const range = scale[name] ?? { min: 0, max: 1 };
                      return (
                        <RangeBar
                          key={name}
                          label={word}
                          low={
                            objective === null
                              ? null
                              : asNumber(objective["lower"])
                          }
                          high={
                            objective === null
                              ? null
                              : asNumber(objective["upper"])
                          }
                          point={
                            objective === null
                              ? null
                              : asNumber(objective["value"])
                          }
                          min={range.min}
                          max={range.max}
                          unit={unitWord(
                            objective === null
                              ? null
                              : asString(objective["unit"]),
                          )}
                          tone={chosen ? "brass" : "ok"}
                        />
                      );
                    })}
                  </div>
                )}
                {chosen ? (
                  <Chip small tone="brass" icon="check">
                    Selected
                  </Chip>
                ) : null}
                <div className="design-explanation">
                  <ExplanationList
                    labelId={`candidate-${id}-satisfied`}
                    label="Satisfied requirements"
                    entries={explanation["satisfied_requirements"]}
                  />
                  <ExplanationList
                    labelId={`candidate-${id}-uncertainties`}
                    label="Uncertainties"
                    entries={explanation["uncertainties"]}
                  />
                </div>
                <details>
                  <summary>Nodes, constraints and sensitivity</summary>
                  <ul className="explanation">
                    {nodes.map((node) => {
                      const nodeId = asString(node["id"]) ?? "";
                      return (
                        <li key={nodeId}>
                          <code className="pointer">{nodeId}</code> —{" "}
                          {asString(node["role"])} (
                          {asString(node["component_ref"]) ?? "no component"})
                        </li>
                      );
                    })}
                  </ul>
                  <ConstraintTable candidate={candidate} />
                  <p className="timeline-meta">
                    {asString(pareto["sensitivity_summary"]) ??
                      "No sensitivity summary."}
                  </p>
                </details>
                <details>
                  <summary>Raw candidate document</summary>
                  <pre className="value">
                    {JSON.stringify(candidate, null, 1)}
                  </pre>
                </details>
                <div className="actions">
                  <Keycap
                    tone="quiet"
                    onClick={() => onEvaluate(id)}
                    busy={pending === `evaluate-${id}`}
                    busyLabel="Requesting…"
                    disabled={pending !== null || !selectable}
                  >
                    Evaluate against the contract
                  </Keycap>
                </div>
                {selectable && !infeasible && (
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
                    <Keycap
                      tone="quiet"
                      icon="check"
                      onClick={() => onSelect(id)}
                      busy={pending === `select-${id}`}
                      busyLabel="Recording…"
                      disabled={pending !== null}
                    >
                      Select {id}
                    </Keycap>
                  </div>
                )}
              </section>
            );
          })}
        </div>

        <section
          aria-label="The bench"
          className={`bench${overBench ? " bench-over" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            setOverBench(true);
          }}
          onDragLeave={() => setOverBench(false)}
          onDrop={onDrop}
        >
          {benched.length === 0 ? (
            <p className="bench-empty">Drop two designs here to compare.</p>
          ) : (
            <>
              <ul className="chip-row" aria-label="On the bench">
                {benched.map((candidate, index) => {
                  const id = asString(candidate["id"]) ?? "";
                  return (
                    <li key={id} className="bench-item">
                      <Chip
                        tone={index === 0 ? "info" : "brass"}
                        onRemove={() => toggleBench(id)}
                        removeLabel={`Take ${id} off the bench`}
                      >
                        {candidateLabel(candidate)}
                      </Chip>
                      {index === 0 && benched.length > 1 ? (
                        <Icon name="send" label="compared with" />
                      ) : null}
                    </li>
                  );
                })}
              </ul>
              {left !== undefined && right !== undefined ? (
                <dl className="bench-deltas">
                  {BENCH_OBJECTIVES.map(({ name, word, icon }) => {
                    const a = asNumber(objectiveFor(left, name)?.["value"]);
                    const b = asNumber(objectiveFor(right, name)?.["value"]);
                    const unit = unitWord(
                      asString(objectiveFor(right, name)?.["unit"] ?? null),
                    );
                    return (
                      <div key={name} title={word}>
                        <dt>
                          <Icon name={icon} label={word} />
                        </dt>
                        <dd className="mono">
                          {a === null || b === null
                            ? "unknown"
                            : `${sign(b - a)}${unit === "" ? "" : ` ${unit}`}`}
                        </dd>
                      </div>
                    );
                  })}
                </dl>
              ) : (
                <p className="bench-empty">One more to compare.</p>
              )}
            </>
          )}
        </section>

        {chosenId !== null ? (
          <Moment>
            <p>
              {candidateLabel(
                candidates.find(
                  (candidate) => asString(candidate["id"]) === chosenId,
                ) ?? {},
              )}{" "}
              is chosen.{" "}
              <Link to={href("/decision")}>
                See the decision and assurance plan
              </Link>
            </p>
          </Moment>
        ) : null}

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

        <p className="thread-aside">
          <Link to={href("")}>Back to the case</Link>
        </p>
      </div>
      <CaseRail caseId={caseId} caseDocument={caseDocument} />
    </div>
  );
}
