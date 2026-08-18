// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

import { semanticDiff, type DiffRow } from "../diff";
import {
  compileBundle,
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
  asObject,
  asString,
  etagFor,
  newIdempotencyKey,
} from "../support";

type PageState =
  | { readonly kind: "loading" }
  | {
      readonly kind: "ready";
      readonly caseDocument: JsonObject;
      readonly bundle: JsonObject | null;
      readonly runnerPlan: JsonObject | null;
      readonly artifactIndex: readonly JsonObject[];
    }
  | { readonly kind: "failed"; readonly failure: ActionFailure };

function toReference(value: unknown): ArtifactReference | null {
  const entry = asObject(value);
  if (entry === null) {
    return null;
  }
  const id = asString(entry["id"]);
  const version = asString(entry["version"]);
  const digest = asString(entry["digest"]);
  if (id === null || version === null || digest === null) {
    return null;
  }
  return { id, version, digest };
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

export function BundlePage({ caseId }: { readonly caseId: string }) {
  const { navigate } = useRouter();
  const [state, setState] = useState<PageState>({ kind: "loading" });
  const [failure, setFailure] = useState<ActionFailure | null>(null);
  const [target, setTarget] = useState("");
  const [validation, setValidation] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [diffRows, setDiffRows] = useState<readonly DiffRow[] | null>(null);
  const [diffLabel, setDiffLabel] = useState<string | null>(null);

  const load = () => {
    setState({ kind: "loading" });
    setFailure(null);
    setDiffRows(null);
    getDesignCase(caseId)
      .then(async (response) => {
        const caseDocument = response.case;
        const bundleReference = toReference(
          caseDocument["deployment_bundle_ref"],
        );
        const runnerReference = toReference(caseDocument["runner_plan_ref"]);
        const [bundle, runnerPlan, artifactIndex] = await Promise.all([
          bundleReference === null
            ? Promise.resolve(null)
            : getJsonArtifact(caseId, bundleReference),
          runnerReference === null
            ? Promise.resolve(null)
            : getJsonArtifact(caseId, runnerReference),
          listArtifacts(caseId).then((listed) => listed.items),
        ]);
        setState({
          kind: "ready",
          caseDocument,
          bundle,
          runnerPlan,
          artifactIndex,
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
  const version = asString(caseDocument["version"]) ?? "";
  const status = asString(caseDocument["status"]) ?? "";
  const title = asString(caseDocument["title"]) ?? caseId;

  const onCompile = () => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(target);
    } catch {
      setValidation("The target profile must be a valid JSON document.");
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
    const selected = toReference(caseDocument["selected_candidate_ref"]);
    if (selected === null) {
      setValidation("Select a candidate before compiling a bundle.");
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

  const semanticVersions = state.artifactIndex
    .filter((entry) => (asString(entry["id"]) ?? "").startsWith("semantic."))
    .map(toReference)
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

  return (
    <>
      <p className="eyebrow">Bundle review</p>
      <h1 id="page-heading">{title}</h1>
      <p className="case-id">
        {caseId} · case version {version} · {status}
      </p>

      {bundle === null ? (
        <section aria-labelledby="compile-heading" className="panel">
          <h2 id="compile-heading">Compile a review bundle</h2>
          {status !== "assurance_planned" ? (
            <p>
              This case has no compiled bundle. Compilation becomes available
              once a candidate is selected and its assurance plan exists; the
              current status is <span className="badge">{status}</span>.
            </p>
          ) : (
            <>
              <p className="hint">
                Provide the target profile as JSON (the repository fixture is
                examples/targets/local-fixture.yaml). Compilation validates the
                declared target but never contacts it, and the result is a draft
                review bundle.
              </p>
              <div className="field">
                <label htmlFor="target-profile">Target profile (JSON)</label>
                <textarea
                  id="target-profile"
                  rows={8}
                  value={target}
                  onChange={(event) => setTarget(event.target.value)}
                  spellCheck={false}
                />
              </div>
              <div className="actions">
                <button type="button" onClick={onCompile} disabled={pending}>
                  {pending ? "Requesting compilation…" : "Compile the bundle"}
                </button>
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
        </section>
      ) : (
        <>
          <section aria-labelledby="separation-heading" className="panel">
            <h2 id="separation-heading">Plan, approval, and apply</h2>
            <dl>
              <div>
                <dt>Plan</dt>
                <dd>
                  <span className="badge">
                    {asString(runnerPlan?.["status"] ?? bundle["status"]) ??
                      "draft"}
                  </span>{" "}
                  compiled, unsigned
                </dd>
              </div>
              <div>
                <dt>Approval</dt>
                <dd>
                  none recorded — requires{" "}
                  {asArray(
                    (asObject(bundle["approval_policy"]) ?? {})[
                      "required_roles"
                    ],
                  )
                    .map((entry) => String(entry))
                    .join(" and ") || "configured roles"}
                </dd>
              </div>
              <div>
                <dt>Apply</dt>
                <dd>
                  unavailable in Community — no runner execution authority
                </dd>
              </div>
            </dl>
            <p className="hint">
              {asArray(
                (asObject(bundle["compatibility"]) ?? {})[
                  "known_incompatibilities"
                ],
              )
                .map((entry) => String(entry))
                .join(" ")}
            </p>
          </section>

          <section aria-labelledby="lock-heading" className="panel">
            <h2 id="lock-heading">Component lock</h2>
            <table>
              <caption className="visually-hidden">
                Locked components with versions, digests, and licence decisions
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
          </section>

          <section aria-labelledby="files-heading" className="panel">
            <h2 id="files-heading">Bundle files</h2>
            <FileViewer
              caseId={caseId}
              reference={
                toReference(
                  caseDocument["deployment_bundle_ref"],
                ) as ArtifactReference
              }
              label="Deployment bundle"
            />
            {toReference(caseDocument["runner_plan_ref"]) !== null && (
              <FileViewer
                caseId={caseId}
                reference={
                  toReference(
                    caseDocument["runner_plan_ref"],
                  ) as ArtifactReference
                }
                label="Draft runner plan (typed, read-only, unsigned)"
              />
            )}
            {asArray(bundle["artifacts"])
              .map(toReference)
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

          <section aria-labelledby="diff-heading" className="panel">
            <h2 id="diff-heading">Semantic diff</h2>
            {semanticVersions.length < 2 ? (
              <p>
                Only one compiled semantic manifest exists, so there is no
                earlier version to compare against yet.
              </p>
            ) : (
              <div className="actions">
                <button type="button" onClick={() => void onDiff()}>
                  Compare the two most recent semantic manifests
                </button>
              </div>
            )}
            {diffRows !== null && (
              <>
                <p className="timeline-meta">{diffLabel}</p>
                {diffRows.length === 0 ? (
                  <p>The two manifests are semantically identical.</p>
                ) : (
                  <div className="table-scroll">
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

      <p>
        <Link to={`/cases/${encodeURIComponent(caseId)}/decision`}>
          Decision and assurance
        </Link>{" "}
        ·{" "}
        <Link to={`/cases/${encodeURIComponent(caseId)}`}>
          Back to the case
        </Link>
      </p>
    </>
  );
}
