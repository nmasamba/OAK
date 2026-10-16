// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { CaseRail, Moment } from "../CaseRail";
import { DownloadTile, type DownloadItem } from "../DownloadsSheet";
import { downloadVerified, type DownloadState } from "../downloads";
import {
  getDesignCase,
  getJsonArtifact,
  getModels,
  recordReport,
  type JsonObject,
  type ModelStatusResponse,
} from "../generated/api";
import { ModeChooser, ModeDetail, type InterpretMode } from "../ModeSelect";
import { currentModelToken } from "../modelToken";
import { ProblemAlert, toActionFailure, type ActionFailure } from "../problems";
import { ReportSlide } from "../ReportSlide";
import { Link } from "../router";
import {
  asArray,
  asObject,
  asReference,
  asString,
  etagFor,
  newIdempotencyKey,
} from "../support";
import { Icon, Keycap } from "../ui";

/** The statuses a report can be recorded from: a design must be selected first (K4). */
const RECORDABLE = new Set([
  "candidate_selected",
  "assurance_planned",
  "bundle_compiled",
  "deployment_approved",
  "deployed",
  "observing",
]);

type PageState =
  | { readonly kind: "loading" }
  | {
      readonly kind: "ready";
      readonly caseDocument: JsonObject;
      readonly entry: JsonObject | null;
      readonly report: JsonObject | null;
    }
  | { readonly kind: "failed"; readonly failure: ActionFailure };

/**
 * The architecture report: recorded beside the case by one command, read here one slide
 * at a time, and taken away as the PDF or the report document, each checked against its
 * digest. Recording authorizes nothing; the screen never re-renders a report silently,
 * and when the case has moved on it says so and offers to record again.
 */
export function ReportPage({ caseId }: { readonly caseId: string }) {
  const [state, setState] = useState<PageState>({ kind: "loading" });
  const [failure, setFailure] = useState<ActionFailure | null>(null);
  const [pending, setPending] = useState(false);
  const [slide, setSlide] = useState(0);
  const [mode, setMode] = useState<InterpretMode>("deterministic");
  const [models, setModels] = useState<ModelStatusResponse | null>(null);
  const [tiles, setTiles] = useState<Record<string, DownloadState>>({});
  const slideRegion = useRef<HTMLElement>(null);
  const tokenPresent = currentModelToken() !== null;

  useEffect(() => {
    const token = currentModelToken();
    if (token === null) {
      return;
    }
    getModels(token)
      .then((status) => setModels(status))
      .catch(() => setModels(null));
  }, []);

  const load = () => {
    setState({ kind: "loading" });
    setFailure(null);
    getDesignCase(caseId)
      .then(async (response) => {
        const caseDocument = response.case;
        const extensions = asObject(caseDocument["extensions"]) ?? {};
        const entry = asObject(extensions["oak.community/report"]);
        const documentReference =
          entry === null ? null : asReference(entry["document_ref"]);
        const report =
          documentReference === null
            ? null
            : await getJsonArtifact(caseId, documentReference);
        setState({ kind: "ready", caseDocument, entry, report });
      })
      .catch((error: unknown) =>
        setState({ kind: "failed", failure: toActionFailure(error) }),
      );
  };

  useEffect(load, [caseId]);

  if (state.kind === "loading") {
    return (
      <p aria-live="polite" role="status">
        Loading the report…
      </p>
    );
  }
  if (state.kind === "failed") {
    return <ProblemAlert failure={state.failure} onReload={load} />;
  }

  const { caseDocument, entry, report } = state;
  const version = asString(caseDocument["version"]) ?? "";
  const status = asString(caseDocument["status"]) ?? "";
  const title = asString(caseDocument["title"]) ?? caseId;
  const recordable = RECORDABLE.has(status);
  const recordedInto =
    entry === null ? null : asString(entry["recorded_case_version"]);
  const madeFrom =
    entry === null ? null : asString(entry["made_from_case_version"]);
  const stale = entry !== null && recordedInto !== version;
  const sections = asArray(report?.["sections"])
    .map(asObject)
    .filter((section): section is JsonObject => section !== null);
  const current = sections[Math.min(slide, Math.max(0, sections.length - 1))];
  const href = (suffix: string) =>
    `/cases/${encodeURIComponent(caseId)}${suffix}`;

  const onRecord = () => {
    const token = currentModelToken();
    setPending(true);
    setFailure(null);
    recordReport(
      caseId,
      {
        idempotencyKey: newIdempotencyKey("report"),
        etag: etagFor(version),
        ...(mode !== "deterministic" && token !== null
          ? { modelToken: token }
          : {}),
      },
      mode,
    )
      .then(() => {
        setSlide(0);
        setTiles({});
        load();
      })
      .catch((error: unknown) => setFailure(toActionFailure(error)))
      .finally(() => setPending(false));
  };

  const go = (index: number) => {
    setSlide(Math.max(0, Math.min(sections.length - 1, index)));
  };

  const onSlideKey = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "ArrowRight" || event.key === "PageDown") {
      event.preventDefault();
      go(slide + 1);
    } else if (event.key === "ArrowLeft" || event.key === "PageUp") {
      event.preventDefault();
      go(slide - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      go(0);
    } else if (event.key === "End") {
      event.preventDefault();
      go(sections.length - 1);
    }
  };

  const reportId = report === null ? null : asString(report["id"]);
  const files: DownloadItem[] = [];
  for (const [key, field, word, icon, extension] of [
    ["pdf", "pdf_ref", "PDF", "slides", "pdf"],
    ["json", "document_ref", "JSON", "file", "json"],
  ] as const) {
    const reference = entry === null ? null : asReference(entry[field]);
    if (reference !== null && reportId !== null) {
      files.push({
        key,
        word,
        icon,
        title: `${reportId}.${extension} · ${reference.digest.slice(0, 15)}…`,
        suffix: `.${extension}`,
        run: () =>
          downloadVerified(caseId, reference, `${reportId}.${extension}`),
      });
    }
  }
  const runTile = (item: DownloadItem) => {
    setTiles((states) => ({ ...states, [item.key]: "fetching" }));
    item
      .run()
      .then((result) =>
        setTiles((states) => ({ ...states, [item.key]: result })),
      )
      .catch(() => setTiles((states) => ({ ...states, [item.key]: "failed" })));
  };

  const recordControls = recordable ? (
    <div className="report-record">
      <ModeChooser
        id="report-narrative"
        value={mode}
        onChange={setMode}
        status={models}
        tokenPresent={tokenPresent}
        disabled={pending}
        purpose="report"
      />
      <ModeDetail
        value={mode}
        status={models}
        tokenPresent={tokenPresent}
        purpose="report"
      />
      <Keycap
        icon="slides"
        onClick={onRecord}
        busy={pending}
        busyLabel="Recording…"
      >
        {entry === null ? "Record report" : "Record again"}
      </Keycap>
    </div>
  ) : null;

  return (
    <div className="convo">
      <div className="thread report-thread">
        <h1 id="page-heading">{title}: report</h1>

        {entry === null ? (
          <Moment fresh>
            <p>No report is recorded yet.</p>
            {recordable ? (
              <p className="thread-aside">
                Recording composes the report from this case's records and keeps
                it, with its PDF, beside the case. It authorizes nothing.
              </p>
            ) : (
              <p className="thread-aside">
                A report needs a selected design first.{" "}
                <Link to={href("/candidates")}>Compare the designs</Link>
              </p>
            )}
            {recordControls}
          </Moment>
        ) : stale ? (
          <Moment className="report-stale">
            <p role="status">
              The case has moved on since this report: it was made from version{" "}
              <span className="mono">{madeFrom}</span> and the case is now at
              version <span className="mono">{version}</span>.
            </p>
            {recordControls}
          </Moment>
        ) : (
          <p className="thread-aside">
            Made from case version <span className="mono">{madeFrom}</span> and
            recorded {asString(entry["recorded_at"])}.
          </p>
        )}

        <div aria-live="polite">
          {failure !== null && (
            <ProblemAlert failure={failure} onReload={load} />
          )}
        </div>

        {current === undefined ? null : (
          <>
            <ul aria-label="Report files" className="files report-files">
              {files.map((item) => (
                <li key={item.key}>
                  <DownloadTile
                    item={item}
                    state={tiles[item.key] ?? "idle"}
                    onRun={() => runTile(item)}
                  />
                </li>
              ))}
            </ul>

            <section
              ref={slideRegion}
              className="slide card"
              aria-roledescription="slide"
              aria-labelledby="slide-title"
              tabIndex={0}
              onKeyDown={onSlideKey}
            >
              <ReportSlide section={current} />
            </section>

            <div className="slide-nav" onKeyDown={onSlideKey}>
              <button
                type="button"
                className="slide-step"
                aria-label="Previous slide"
                onClick={() => go(slide - 1)}
                disabled={slide === 0}
              >
                <Icon name="prev" size={20} />
              </button>
              <p className="mono" aria-live="polite">
                Slide {slide + 1} of {sections.length}
              </p>
              <button
                type="button"
                className="slide-step"
                aria-label="Next slide"
                onClick={() => go(slide + 1)}
                disabled={slide === sections.length - 1}
              >
                <Icon name="next" size={20} />
              </button>
            </div>

            <nav aria-label="Report contents" className="report-contents">
              <ol>
                {sections.map((section, index) => (
                  <li key={asString(section["id"]) ?? index}>
                    <button
                      type="button"
                      className="report-contents-item"
                      onClick={() => {
                        go(index);
                        slideRegion.current?.focus();
                      }}
                      {...(index === slide ? { "aria-current": "step" } : {})}
                    >
                      <span className="mono">
                        {asString(section["number"])}
                      </span>{" "}
                      {asString(section["title"])}
                    </button>
                  </li>
                ))}
              </ol>
            </nav>
          </>
        )}

        <p className="thread-aside">
          <Link to={href("/bundle")}>The architecture</Link> ·{" "}
          <Link to={href("")}>Back to the case</Link>
        </p>
      </div>
      <CaseRail caseId={caseId} caseDocument={caseDocument} />
    </div>
  );
}
