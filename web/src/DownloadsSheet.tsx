// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import {
  downloadArchitecture,
  downloadVerified,
  extensionFor,
  saveBlob,
  saveText,
  type DownloadState,
} from "./downloads";
import {
  exportDesignCase,
  getJsonArtifact,
  type ArtifactReference,
  type JsonObject,
} from "./generated/api";
import { useRouter } from "./router";
import { asArray, asObject, asReference, asString } from "./support";
import { serialiseDiagram } from "./svgExport";
import { Icon, Keycap, type IconName } from "./ui";

/** One thing to take: a stored artifact, the composed architecture, or the drawn diagram. */
export interface DownloadItem {
  readonly key: string;
  readonly word: string;
  readonly icon: IconName;
  readonly title: string;
  readonly suffix: string;
  readonly run: () => Promise<DownloadState>;
}

const STATE_WORDS: Readonly<Record<DownloadState, string>> = {
  idle: "",
  fetching: "fetching",
  verified: "digest matches",
  saved: "saved",
  mismatch: "digest differs",
  failed: "failed",
};

function short(digest: string): string {
  return `${digest.slice(0, 15)}…`;
}

function storedItem(
  caseId: string,
  key: string,
  word: string,
  icon: IconName,
  reference: ArtifactReference,
  filename: string | null,
  note: string,
): DownloadItem {
  return {
    key,
    word,
    icon,
    title: [filename ?? reference.id, note, short(reference.digest)]
      .filter((part) => part !== "")
      .join(" · "),
    suffix: "",
    run: () => downloadVerified(caseId, reference, filename),
  };
}

/**
 * The files a case can hand over, from the references the case document carries. The
 * brief's original name comes from its source record, read once when the sheet opens.
 */
export function useDownloads(
  caseId: string,
  caseDocument: JsonObject,
): readonly DownloadItem[] {
  const briefReference = asReference(asArray(caseDocument["brief_refs"])[0]);
  // The original name lives on the source record, not on the brief bytes.
  const sourceRecord = asReference(
    (asObject(caseDocument["extensions"]) ?? {})[
      "oak.community/source_record_ref"
    ],
  );
  const { navigate } = useRouter();
  const [briefName, setBriefName] = useState<string | null>(null);
  useEffect(() => {
    if (sourceRecord === null) {
      return;
    }
    getJsonArtifact(caseId, sourceRecord)
      .then((record) => setBriefName(asString(record["original_name"])))
      .catch(() => setBriefName(null));
  }, [caseId, sourceRecord?.id, sourceRecord?.digest]);

  const items: DownloadItem[] = [];
  if (briefReference !== null) {
    items.push(
      storedItem(
        caseId,
        "brief",
        "Brief",
        "file",
        briefReference,
        briefName,
        "as stored, normalised",
      ),
    );
  }
  const intent = asReference(caseDocument["intent_ref"]);
  if (intent !== null) {
    items.push(
      storedItem(caseId, "intent", "Intent", "search", intent, null, ""),
    );
  }
  for (const value of asArray(caseDocument["candidate_refs"])) {
    const reference = asReference(value);
    if (reference !== null) {
      items.push(
        storedItem(
          caseId,
          `candidate-${reference.id}`,
          `Design ${reference.id}`,
          "diagram",
          reference,
          null,
          "",
        ),
      );
    }
  }
  const extensions = asObject(caseDocument["extensions"]) ?? {};
  const decision = asReference(
    extensions["oak.community/selection_decision_ref"],
  );
  if (decision !== null) {
    items.push(
      storedItem(caseId, "decision", "Decision", "check", decision, null, ""),
    );
  }
  const assurance = asReference(caseDocument["assurance_plan_ref"]);
  if (assurance !== null) {
    items.push(
      storedItem(
        caseId,
        "assurance",
        "Assurance",
        "shield",
        assurance,
        null,
        "",
      ),
    );
  }
  const selected = asReference(caseDocument["selected_candidate_ref"]);
  // The recorded report's PDF, checked like every stored file; before one is recorded,
  // the tile opens the Report screen, where recording is a deliberate step.
  const report = asObject(extensions["oak.community/report"]);
  const reportPdf = report === null ? null : asReference(report["pdf_ref"]);
  if (reportPdf !== null) {
    items.push(
      storedItem(
        caseId,
        "report",
        "Report",
        "slides",
        reportPdf,
        reportPdf.id,
        "the recorded PDF",
      ),
    );
  } else if (selected !== null) {
    items.push({
      key: "report",
      word: "Report",
      icon: "slides",
      title: "No report is recorded yet · open the Report screen to record one",
      suffix: "open",
      run: () => {
        navigate(`/cases/${encodeURIComponent(caseId)}/report`);
        return Promise.resolve("idle");
      },
    });
  }
  if (selected !== null) {
    for (const format of ["yaml", "json"] as const) {
      items.push({
        key: `architecture-${format}`,
        word: "Architecture",
        icon: "box",
        title: `${caseId}-architecture.${format} · composed now; its parts carry digests`,
        suffix: `.${format}`,
        run: async () => {
          await downloadArchitecture(caseId, format, selected.id);
          return "saved";
        },
      });
    }
  }
  return items;
}

/** The drawn diagram on this page, when there is one. */
function diagramOnPage(): SVGSVGElement | null {
  const element = document.getElementById("topology-diagram");
  return element instanceof SVGSVGElement ? element : null;
}

export function DownloadTile({
  item,
  state,
  onRun,
}: {
  readonly item: DownloadItem;
  readonly state: DownloadState;
  readonly onRun: () => void;
}) {
  const tone =
    state === "verified" || state === "saved"
      ? "tile-file-ok"
      : state === "mismatch" || state === "failed"
        ? "tile-file-bad"
        : state === "fetching"
          ? "tile-file-busy"
          : "";
  return (
    <button
      type="button"
      className={`tile-file ${tone}`}
      title={item.title}
      onClick={() => {
        if (state !== "fetching") {
          onRun();
        }
      }}
      aria-disabled={state === "fetching" ? true : undefined}
      aria-busy={state === "fetching" ? true : undefined}
    >
      <Icon
        name={state === "fetching" ? "spinner" : item.icon}
        size={28}
        {...(state === "fetching" ? { className: "icon-spin" } : {})}
      />
      <span className="tile-word">{item.word}</span>
      <span className="tile-state mono">
        {state === "idle" ? item.suffix : STATE_WORDS[state]}
      </span>
    </button>
  );
}

/**
 * The downloads sheet: every file of the case, each checked in the browser before it is
 * saved. Opening it reads; nothing here authorises anything. Escape or Close returns
 * focus to the control that opened it.
 */
export function DownloadsSheet({
  caseId,
  caseDocument,
  onClose,
}: {
  readonly caseId: string;
  readonly caseDocument: JsonObject;
  readonly onClose: () => void;
}) {
  const items = useDownloads(caseId, caseDocument);
  const [states, setStates] = useState<Record<string, DownloadState>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const sheet = useRef<HTMLDivElement>(null);
  const diagram = diagramOnPage();

  // Focus is captured and restored once per mount, whatever the caller re-renders.
  useEffect(() => {
    const opener = document.activeElement;
    closeButton.current?.focus();
    return () => {
      if (opener instanceof HTMLElement) {
        opener.focus();
      }
    };
  }, []);

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Tab wraps inside the dialog: the page behind the scrim is not reachable.
  const onTab = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Tab" || sheet.current === null) {
      return;
    }
    const focusable = [
      ...sheet.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], input, [tabindex="0"]',
      ),
    ];
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (first === undefined || last === undefined) {
      return;
    }
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const diagramItem: DownloadItem | null =
    diagram === null
      ? null
      : {
          key: "diagram",
          word: "Diagram",
          icon: "image",
          title: `${caseId}-topology.svg · drawn from the design, at its own size`,
          suffix: ".svg",
          run: () => {
            saveText(
              serialiseDiagram(diagram),
              "image/svg+xml",
              `${caseId}-topology.svg`,
            );
            return Promise.resolve("saved");
          },
        };

  const run = (item: DownloadItem) => {
    setFailure(null);
    setStates((current) => ({ ...current, [item.key]: "fetching" }));
    item
      .run()
      .then((state) =>
        setStates((current) => ({ ...current, [item.key]: state })),
      )
      .catch(() => {
        setStates((current) => ({ ...current, [item.key]: "failed" }));
        setFailure(`${item.word} could not be fetched.`);
      });
  };

  const onEverything = () => {
    setFailure(null);
    exportDesignCase(caseId)
      .then((exported) =>
        saveBlob(
          new Blob([JSON.stringify(exported)], { type: "application/json" }),
          `${caseId}-export.json`,
        ),
      )
      .catch(() => setFailure("The export could not be fetched."));
  };

  return (
    <div className="sheet-scrim" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="sheet-title"
        className="sheet"
        ref={sheet}
        onClick={(event) => event.stopPropagation()}
        onKeyDown={onTab}
      >
        <div className="sheet-head">
          <h2 id="sheet-title">Take it</h2>
          <span className="spacer" />
          <Keycap
            icon="download"
            onClick={onEverything}
            title="The whole case, in the layout oak import reads"
          >
            Everything
          </Keycap>
          <button
            type="button"
            className="sheet-close"
            aria-label="Close"
            onClick={onClose}
            ref={closeButton}
          >
            <Icon name="close" size={18} />
          </button>
        </div>
        <ul aria-label="Files" className="files">
          {items.map((item) => (
            <li key={item.key}>
              <DownloadTile
                item={item}
                state={states[item.key] ?? "idle"}
                onRun={() => run(item)}
              />
            </li>
          ))}
          {diagramItem !== null ? (
            <li>
              <DownloadTile
                item={diagramItem}
                state={states[diagramItem.key] ?? "idle"}
                onRun={() => run(diagramItem)}
              />
            </li>
          ) : null}
        </ul>
        <div aria-live="polite">
          {failure === null ? null : (
            <p className="problem" role="alert">
              {failure}
            </p>
          )}
        </div>
        <p className="sheet-note">
          Stored files are checked in your browser. A download authorises
          nothing.
        </p>
      </div>
    </div>
  );
}
