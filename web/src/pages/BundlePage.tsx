// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

import { CaseRail, Moment } from "../CaseRail";
import { semanticDiff, type DiffRow } from "../diff";
import {
  compileBundle,
  exportDesignCase,
  getDesignCase,
  getJsonArtifact,
  listArtifacts,
  type ArtifactReference,
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
  NODE_HEIGHT,
  NODE_WIDTH,
  layoutTopology,
  type TopologyLayout,
} from "../topology";
import {
  Chip,
  CopyPlate,
  Icon,
  Keycap,
  Led,
  candidateLabel,
  formatQuantity,
  type IconName,
  type LedState,
} from "../ui";

type PageState =
  | { readonly kind: "loading" }
  | {
      readonly kind: "ready";
      readonly caseDocument: JsonObject;
      readonly bundle: JsonObject | null;
      readonly runnerPlan: JsonObject | null;
      readonly candidate: JsonObject | null;
      readonly artifactIndex: readonly JsonObject[];
      readonly approvals: Readonly<Record<string, JsonObject>>;
    }
  | { readonly kind: "failed"; readonly failure: ActionFailure };

/** The commands the copy plate carries. They run only where the user pastes them. */
const INSTALL_STEPS = [
  "oak sign",
  "oak approve architecture",
  "oak approve apply",
  "oak dispatch apply",
  "oak-runner run-once",
  "oak ingest",
].join("\n");

const PREDICTIONS: readonly {
  readonly name: string;
  readonly word: string;
  readonly icon: IconName;
}[] = [
  { name: "quality", word: "Quality", icon: "star" },
  { name: "latency_p95", word: "Latency", icon: "clock" },
  { name: "energy", word: "Energy", icon: "bolt" },
  { name: "monthly_cost", word: "Monthly cost", icon: "coin" },
];

function formatPrediction(name: string, value: number | null): string {
  if (value === null) {
    return "unknown";
  }
  switch (name) {
    case "latency_p95":
      return value >= 1000
        ? `${formatQuantity(value / 1000)} s`
        : `${formatQuantity(value)} ms`;
    case "energy":
      return `${formatQuantity(value)} Wh`;
    case "monthly_cost":
      return `$${formatQuantity(value)}/mo`;
    default:
      return formatQuantity(value);
  }
}

function approvalCondition(
  approval: JsonObject | undefined,
  now: number,
): LedState {
  if (approval === undefined) {
    return "absent";
  }
  if (approval["revoked"] === true) {
    return "revoked";
  }
  const expires = asString(approval["expires_at"]);
  if (expires !== null && Date.parse(expires) <= now) {
    return "expired";
  }
  return "current";
}

function FileViewer({
  caseId,
  reference,
  label,
}: {
  readonly caseId: string;
  readonly reference: ArtifactReference;
  readonly label: string;
}) {
  const [content, setContent] = useState<JsonObject | null>(null);
  const [failed, setFailed] = useState(false);

  const onToggle = (open: boolean) => {
    if (open && content === null && !failed) {
      getJsonArtifact(caseId, reference)
        .then(setContent)
        .catch(() => setFailed(true));
    }
  };

  return (
    <details onToggle={(event) => onToggle(event.currentTarget.open)}>
      <summary>
        {label} <code className="pointer">{reference.id}</code>
      </summary>
      <p className="timeline-meta">
        version {reference.version} · {reference.digest}
      </p>
      {failed && (
        <p className="problem" role="alert">
          This artifact could not be loaded.
        </p>
      )}
      {content !== null && (
        <pre className="value">{JSON.stringify(content, null, 1)}</pre>
      )}
    </details>
  );
}

/** The topology drawn. Its accessible name is the sentence the layout wrote. */
export function TopologyDiagram({
  layout,
  zoom = 1,
  id = "topology-diagram",
}: {
  readonly layout: TopologyLayout;
  readonly zoom?: number;
  readonly id?: string;
}) {
  const marker = `${id}-arrow`;
  return (
    <svg
      id={id}
      role="img"
      aria-label={layout.description}
      className="topology"
      width={Math.round(layout.width * zoom)}
      height={Math.round(layout.height * zoom)}
      viewBox={`0 0 ${layout.width} ${layout.height}`}
    >
      <defs>
        <marker
          id={marker}
          orient="auto"
          markerWidth="6"
          markerHeight="6"
          refX="5"
          refY="3"
        >
          <path d="M0 0 L6 3 L0 6 Z" className="topology-arrow" />
        </marker>
      </defs>
      {layout.edges.map((edge, index) => (
        <g key={`${edge.from}-${edge.to}-${index}`} className="topology-link">
          <line
            x1={edge.x1}
            y1={edge.y1}
            x2={edge.x2}
            y2={edge.y2}
            className="topology-edge"
            markerEnd={`url(#${marker})`}
          />
          {edge.label === "" ? null : (
            <text
              x={(edge.x1 + edge.x2) / 2}
              y={Math.min(edge.y1, edge.y2) - 8}
              textAnchor="middle"
              className="topology-edge-label"
            >
              {edge.label}
            </text>
          )}
        </g>
      ))}
      {layout.nodes.map((node) => (
        <g
          key={node.id}
          transform={`translate(${node.x} ${node.y})`}
          className={`topology-node${node.component === null ? " topology-node-external" : ""}`}
        >
          <rect width={NODE_WIDTH} height={NODE_HEIGHT} rx="12" />
          <text x="14" y="30" className="topology-role">
            {node.role}
          </text>
          <text x="14" y="52" className="topology-component">
            {node.component ?? "outside the design"}
          </text>
        </g>
      ))}
    </svg>
  );
}

function TopologyTable({ layout }: { readonly layout: TopologyLayout }) {
  return (
    <div className="topology-tables">
      <table>
        <caption className="visually-hidden">Nodes of the topology</caption>
        <thead>
          <tr>
            <th scope="col">Node</th>
            <th scope="col">Role</th>
            <th scope="col">Component</th>
          </tr>
        </thead>
        <tbody>
          {layout.nodes.map((node) => (
            <tr key={node.id}>
              <th scope="row">
                <code className="pointer">{node.id}</code>
              </th>
              <td>{node.role}</td>
              <td>
                {node.component === null ? (
                  "outside the design"
                ) : (
                  <code className="pointer">{node.component}</code>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <table>
        <caption className="visually-hidden">Edges of the topology</caption>
        <thead>
          <tr>
            <th scope="col">From</th>
            <th scope="col">To</th>
            <th scope="col">Interface</th>
          </tr>
        </thead>
        <tbody>
          {layout.edges.map((edge, index) => (
            <tr key={index}>
              <th scope="row">
                <code className="pointer">{edge.from}</code>
              </th>
              <td>
                <code className="pointer">{edge.to}</code>
              </td>
              <td>{edge.label === "" ? "—" : edge.label}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function BundlePage({ caseId }: { readonly caseId: string }) {
  const { navigate } = useRouter();
  const [state, setState] = useState<PageState>({ kind: "loading" });
  const [failure, setFailure] = useState<ActionFailure | null>(null);
  const [target, setTarget] = useState("");
  const [validation, setValidation] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [diffRows, setDiffRows] = useState<readonly DiffRow[] | null>(null);
  const [diffLabel, setDiffLabel] = useState<string | null>(null);
  const [view, setView] = useState<"diagram" | "table">("diagram");
  const [zoom, setZoom] = useState(1);

  const load = () => {
    setState({ kind: "loading" });
    setFailure(null);
    setDiffRows(null);
    getDesignCase(caseId)
      .then(async (response) => {
        const caseDocument = response.case;
        const bundleReference = asReference(
          caseDocument["deployment_bundle_ref"],
        );
        const runnerReference = asReference(caseDocument["runner_plan_ref"]);
        const candidateReference = asReference(
          caseDocument["selected_candidate_ref"],
        );
        const [bundle, runnerPlan, candidate, artifactIndex] =
          await Promise.all([
            bundleReference === null
              ? Promise.resolve(null)
              : getJsonArtifact(caseId, bundleReference),
            runnerReference === null
              ? Promise.resolve(null)
              : getJsonArtifact(caseId, runnerReference),
            candidateReference === null
              ? Promise.resolve(null)
              : getJsonArtifact(caseId, candidateReference),
            listArtifacts(caseId).then((listed) => listed.items),
          ]);
        // Read each recorded approval, so a revoked or expired one is shown as such
        // rather than as merely "recorded".
        const approvalRefs =
          asObject(
            (asObject(caseDocument["extensions"]) ?? {})[
              "oak.community/approval_refs"
            ],
          ) ?? {};
        const approvals: Record<string, JsonObject> = {};
        await Promise.all(
          Object.entries(approvalRefs).map(async ([action, value]) => {
            const reference = asReference(value);
            if (reference !== null) {
              approvals[action] = await getJsonArtifact(caseId, reference);
            }
          }),
        );
        setState({
          kind: "ready",
          caseDocument,
          bundle,
          runnerPlan,
          candidate,
          artifactIndex,
          approvals,
        });
      })
      .catch((error: unknown) =>
        setState({ kind: "failed", failure: toActionFailure(error) }),
      );
  };

  useEffect(load, [caseId]);

  if (state.kind === "loading") {
    return (
      <p aria-live="polite" role="status">
        Loading bundle…
      </p>
    );
  }
  if (state.kind === "failed") {
    return <ProblemAlert failure={state.failure} onReload={load} />;
  }

  const caseDocument = state.caseDocument;
  const bundle = state.bundle;
  const runnerPlan = state.runnerPlan;
  const candidate = state.candidate;
  const version = asString(caseDocument["version"]) ?? "";
  const status = asString(caseDocument["status"]) ?? "";
  const title = asString(caseDocument["title"]) ?? caseId;
  const href = (suffix: string) =>
    `/cases/${encodeURIComponent(caseId)}${suffix}`;
  // What the case actually carries, never a fixed claim of absence: signing, approval,
  // dispatch and observation happen only on the local command line, and this page
  // reports them without offering any of them.
  const caseExtensions = asObject(caseDocument["extensions"]) ?? {};
  const now = Date.now();
  const recordedApprovals = Object.keys(state.approvals)
    .sort()
    .map(
      (action) =>
        `${action} (${approvalCondition(state.approvals[action], now)})`,
    );
  const runnerResults = asArray(
    caseExtensions["oak.community/runner_result_refs"],
  ).length;
  const observations = asArray(
    caseExtensions["oak.community/observation_refs"],
  ).length;
  const signed =
    caseExtensions["oak.community/plan_signature_ref"] !== undefined;
  const lights: readonly {
    readonly need: string;
    readonly state: LedState;
    readonly title: string;
  }[] = [
    {
      need: "sign",
      state: signed ? "current" : "absent",
      title: `Plan signature: ${signed ? "present" : "absent"}`,
    },
    {
      need: "design",
      state: approvalCondition(state.approvals["architecture"], now),
      title: `Architecture approval: ${approvalCondition(state.approvals["architecture"], now)}`,
    },
    {
      need: "install",
      state: approvalCondition(state.approvals["apply"], now),
      title: `Apply approval: ${approvalCondition(state.approvals["apply"], now)}`,
    },
  ];
  const layout =
    candidate === null ? null : layoutTopology(candidate["topology"]);

  const onCompile = () => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(target);
    } catch {
      setValidation("The target profile must be valid JSON.");
      return;
    }
    if (
      typeof parsed !== "object" ||
      parsed === null ||
      Array.isArray(parsed)
    ) {
      setValidation("The target profile must be a JSON object.");
      return;
    }
    const selected = asReference(caseDocument["selected_candidate_ref"]);
    if (selected === null) {
      setValidation("Select a candidate first.");
      return;
    }
    setValidation(null);
    setPending(true);
    setFailure(null);
    compileBundle(
      caseId,
      { candidate_id: selected.id, target: parsed as JsonObject },
      {
        idempotencyKey: newIdempotencyKey("compile"),
        etag: etagFor(version),
      },
    )
      .then((operation) =>
        navigate(`/operations/${encodeURIComponent(operation.operation_id)}`),
      )
      .catch((error: unknown) => setFailure(toActionFailure(error)))
      .finally(() => setPending(false));
  };

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

  const semanticVersions = state.artifactIndex
    .filter((entry) => (asString(entry["id"]) ?? "").startsWith("semantic."))
    .map(asReference)
    .filter((entry): entry is ArtifactReference => entry !== null)
    .sort((left, right) => left.version.localeCompare(right.version));

  const onDiff = async () => {
    if (semanticVersions.length < 2) {
      return;
    }
    const previous = semanticVersions[
      semanticVersions.length - 2
    ] as ArtifactReference;
    const current = semanticVersions[
      semanticVersions.length - 1
    ] as ArtifactReference;
    try {
      const [before, after] = await Promise.all([
        getJsonArtifact(caseId, previous),
        getJsonArtifact(caseId, current),
      ]);
      setDiffRows(semanticDiff(before, after));
      setDiffLabel(
        `${previous.id}@${previous.version} → ${current.id}@${current.version}`,
      );
    } catch (error: unknown) {
      setFailure(toActionFailure(error));
    }
  };

  const bundleRef = asReference(caseDocument["deployment_bundle_ref"]);
  const runnerRef = asReference(caseDocument["runner_plan_ref"]);

  return (
    <div className="convo">
      <div className="thread">
        <h1 id="page-heading">{title}</h1>

        {bundle === null ? (
          <Moment fresh>
            {status !== "assurance_planned" ? (
              <p>Select a design and plan assurance first.</p>
            ) : (
              <>
                <p>Compile it for a target.</p>
                <div className="field">
                  <label htmlFor="target-profile">Target profile (JSON)</label>
                  <textarea
                    id="target-profile"
                    rows={8}
                    value={target}
                    onChange={(event) => setTarget(event.target.value)}
                    spellCheck={false}
                    title="The repository fixture is examples/targets/local-fixture.yaml. Compilation validates the target and never contacts it."
                  />
                </div>
                <div className="moment-row">
                  <Keycap
                    onClick={onCompile}
                    busy={pending}
                    busyLabel="Requesting…"
                    icon="box"
                  >
                    Compile the bundle
                  </Keycap>
                </div>
              </>
            )}
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
          </Moment>
        ) : (
          <>
            <Moment fresh>
              <div className="moment-row">
                <p>
                  Compiled. Here is{" "}
                  {candidate === null
                    ? "the design"
                    : candidateLabel(candidate)}
                  .
                </p>
                <Chip small tone="ok" mono>
                  {status}
                </Chip>
              </div>
            </Moment>

            {layout !== null && (
              <section aria-label="Topology" className="card topology-card">
                <div className="moment-row">
                  <div role="group" aria-label="View" className="view-group">
                    <button
                      type="button"
                      className="ico"
                      aria-label="Diagram"
                      aria-pressed={view === "diagram"}
                      onClick={() => setView("diagram")}
                    >
                      <Icon name="diagram" size={18} />
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
                  <span className="spacer" />
                  {view === "diagram" ? (
                    <>
                      <button
                        type="button"
                        className="zoom"
                        aria-label="Zoom out"
                        onClick={() =>
                          setZoom((current) => Math.max(0.5, current - 0.25))
                        }
                      >
                        −
                      </button>
                      <button
                        type="button"
                        className="zoom"
                        aria-label="Zoom in"
                        onClick={() =>
                          setZoom((current) => Math.min(2, current + 0.25))
                        }
                      >
                        +
                      </button>
                    </>
                  ) : null}
                </div>
                {view === "diagram" ? (
                  <div className="topology-scroll">
                    <TopologyDiagram layout={layout} zoom={zoom} />
                  </div>
                ) : (
                  <TopologyTable layout={layout} />
                )}
                <ul className="chip-row" aria-label="Predictions">
                  {PREDICTIONS.map(({ name, word, icon }) => {
                    const objective = asArray(candidate?.["objectives"])
                      .map(asObject)
                      .find(
                        (entry) =>
                          entry !== null && asString(entry["name"]) === name,
                      );
                    if (objective === undefined || objective === null) {
                      return null;
                    }
                    const value = asNumber(objective["value"]);
                    const lower = asNumber(objective["lower"]);
                    const upper = asNumber(objective["upper"]);
                    return (
                      <li key={name}>
                        <Chip
                          mono
                          title={`${word} ${formatQuantity(value)}, range ${formatQuantity(lower)} to ${formatQuantity(upper)}`}
                        >
                          <Icon
                            name={icon}
                            label={word}
                            className="chip-glyph"
                          />
                          {formatPrediction(name, value)}
                        </Chip>
                      </li>
                    );
                  })}
                </ul>
              </section>
            )}

            <section aria-labelledby="separation-heading" className="card">
              <h2 id="separation-heading">Plan, approval, and apply</h2>
              <dl>
                <div>
                  <dt>Plan</dt>
                  <dd>
                    <span className="badge">
                      {asString(runnerPlan?.["status"] ?? bundle["status"]) ??
                        "draft"}
                    </span>{" "}
                    {signed
                      ? "compiled, signed on the local command line"
                      : "compiled, unsigned"}
                  </dd>
                </div>
                <div>
                  <dt>Approval</dt>
                  <dd>
                    {recordedApprovals.length > 0
                      ? `recorded on the local command line: ${recordedApprovals.join(", ")}`
                      : `none recorded — requires ${
                          asArray(
                            (asObject(bundle["approval_policy"]) ?? {})[
                              "required_roles"
                            ],
                          )
                            .map((entry) => String(entry))
                            .join(" and ") || "configured roles"
                        }`}
                  </dd>
                </div>
                <div>
                  <dt>Apply</dt>
                  <dd>
                    not available here — the web workspace holds no runner
                    execution authority; install with{" "}
                    <code>oak dispatch apply</code> and a runner on the local
                    command line
                  </dd>
                </div>
                {(runnerResults > 0 || observations > 0) && (
                  <div>
                    <dt>Runner results</dt>
                    <dd>
                      {runnerResults} signed runner result
                      {runnerResults === 1 ? "" : "s"} and {observations}{" "}
                      observation record{observations === 1 ? "" : "s"},
                      recorded through the local command line; this page cannot
                      install, approve or observe.
                    </dd>
                  </div>
                )}
              </dl>
              {asArray(
                (asObject(bundle["compatibility"]) ?? {})[
                  "known_incompatibilities"
                ],
              ).length > 0 ? (
                <p className="hint">
                  {asArray(
                    (asObject(bundle["compatibility"]) ?? {})[
                      "known_incompatibilities"
                    ],
                  )
                    .map((entry) => String(entry))
                    .join(" ")}
                </p>
              ) : null}
            </section>

            <section aria-labelledby="lock-heading" className="card">
              <h2 id="lock-heading">Component lock</h2>
              <div className="table-scroll">
                <table>
                  <caption className="visually-hidden">
                    Locked components with versions, digests, and licence
                    decisions
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Component</th>
                      <th scope="col">Version</th>
                      <th scope="col">Licence</th>
                      <th scope="col">Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {asArray(bundle["component_lock"])
                      .map(asObject)
                      .filter((entry): entry is JsonObject => entry !== null)
                      .map((component) => {
                        const id = asString(component["manifest_id"]) ?? "";
                        return (
                          <tr key={id}>
                            <th scope="row">
                              <code className="pointer">{id}</code>
                              <span className="case-id">
                                {asString(component["digest"])}
                              </span>
                            </th>
                            <td>{asString(component["version"])}</td>
                            <td>
                              <span className="badge">
                                {asString(component["licence_decision"])}
                              </span>
                            </td>
                            <td>{asString(component["source"])}</td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            </section>

            <section aria-labelledby="files-heading" className="card">
              <h2 id="files-heading">Bundle files</h2>
              {bundleRef !== null && (
                <FileViewer
                  caseId={caseId}
                  reference={bundleRef}
                  label="Deployment bundle"
                />
              )}
              {runnerRef !== null && (
                <FileViewer
                  caseId={caseId}
                  reference={runnerRef}
                  label="Draft runner plan (typed; its signature and approvals are separate artifacts)"
                />
              )}
              {asArray(bundle["artifacts"])
                .map(asReference)
                .filter((entry): entry is ArtifactReference => entry !== null)
                .map((reference) => (
                  <FileViewer
                    key={reference.id}
                    caseId={caseId}
                    reference={reference}
                    label="Review artifact"
                  />
                ))}
            </section>

            <section aria-labelledby="diff-heading" className="card">
              <h2 id="diff-heading">Semantic diff</h2>
              {semanticVersions.length < 2 ? (
                <p>One compiled manifest; nothing earlier to compare.</p>
              ) : (
                <div className="actions">
                  <Keycap tone="quiet" onClick={() => void onDiff()}>
                    Compare the two most recent semantic manifests
                  </Keycap>
                </div>
              )}
              {diffRows !== null && (
                <>
                  <p className="timeline-meta">{diffLabel}</p>
                  {diffRows.length === 0 ? (
                    <p>The two manifests are semantically identical.</p>
                  ) : (
                    <div
                      className="table-scroll"
                      tabIndex={0}
                      role="region"
                      aria-label="Semantic diff table"
                    >
                      <table>
                        <caption className="visually-hidden">
                          Semantic differences between manifest versions
                        </caption>
                        <thead>
                          <tr>
                            <th scope="col">Field</th>
                            <th scope="col">Change</th>
                            <th scope="col">Before</th>
                            <th scope="col">After</th>
                          </tr>
                        </thead>
                        <tbody>
                          {diffRows.map((row) => (
                            <tr key={row.pointer}>
                              <th scope="row">
                                <code className="pointer">{row.pointer}</code>
                              </th>
                              <td>
                                <span className="badge">{row.kind}</span>
                              </td>
                              <td>
                                <pre className="value">{row.before ?? "—"}</pre>
                              </td>
                              <td>
                                <pre className="value">{row.after ?? "—"}</pre>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </section>
            <div aria-live="polite">
              {failure !== null && (
                <ProblemAlert failure={failure} onReload={load} />
              )}
            </div>
          </>
        )}

        <p className="thread-aside">
          <Link to={href("/decision")}>Decision and assurance</Link> ·{" "}
          <Link to={href("")}>Back to the case</Link>
        </p>
      </div>

      <div className="rail-stack">
        {bundle !== null && (
          <aside aria-label="Take it and install" className="dock">
            <h2 className="dock-heading">Take it</h2>
            <Keycap icon="download" onClick={onExport} className="dock-all">
              Everything
            </Keycap>
            <hr className="dock-rule" />
            <h2 className="dock-heading">Install</h2>
            <ul aria-label="Install needs" className="dock-lights">
              {lights.map((light) => (
                <li key={light.need} title={light.title}>
                  <Led
                    state={light.state}
                    word={`${light.need} · ${light.state}`}
                  />
                </li>
              ))}
            </ul>
            <CopyPlate
              command={INSTALL_STEPS}
              label="Copy install steps"
              className="dock-plate"
            />
            <p className="dock-note">
              Signed in your terminal. The web never installs.
            </p>
          </aside>
        )}
        <CaseRail caseId={caseId} caseDocument={caseDocument} />
      </div>
    </div>
  );
}
