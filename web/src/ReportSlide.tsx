// SPDX-License-Identifier: Apache-2.0
/**
 * One section of a recorded architecture report, drawn from the report document as it
 * was stored. Nothing here composes words or numbers: every value, label and title is
 * the document's own. A status is its shape and its word; every picture sits beside the
 * table that lists the same; a note a model proposed sits under its own label.
 */
import { claimClassForSource } from "./claims";
import { TopologyDiagram } from "./pages/BundlePage";
import type { TopologyLayout } from "./topology";
import type { JsonObject } from "./generated/api";
import { asArray, asNumber, asObject, asString } from "./support";
import { CopyPlate, Led, ProvenanceMark, RangeBar, type LedState } from "./ui";

const LED_FOR_STATUS: Readonly<Record<string, LedState>> = {
  pass: "ok",
  satisfied: "ok",
  clear: "ok",
  current: "current",
  selected: "current",
  frontier: "ok",
  fail: "failed",
  infeasible: "failed",
  revoked: "revoked",
  blocked: "failed",
  expired: "expired",
  unknown: "unknown",
  required: "absent",
  absent: "absent",
  dominated: "absent",
  not_applicable: "absent",
};

function objects(value: unknown): readonly JsonObject[] {
  return asArray(value)
    .map(asObject)
    .filter((entry): entry is JsonObject => entry !== null);
}

function Mark({ mark }: { readonly mark: JsonObject | null }) {
  if (mark === null) {
    return null;
  }
  return (
    <ProvenanceMark
      claimClass={claimClassForSource(asString(mark["class"]))}
      word={asString(mark["word"]) ?? "Unknown"}
      className="report-mark"
    />
  );
}

/** One value of the report: text, a list, a quantity, a status or an unknown. */
export function ReportValue({
  value,
  display = "full",
}: {
  readonly value: JsonObject;
  readonly display?: string;
}) {
  const kind = asString(value["type"]);
  if (kind === "text") {
    return (
      <>
        <span>{asString(value["text"])}</span>
        <Mark mark={asObject(value["mark"])} />
      </>
    );
  }
  if (kind === "list") {
    const items = asArray(value["items"]).map((item) => String(item));
    return (
      <>
        {items.length === 0 ? (
          <span>none</span>
        ) : (
          <ul className="report-list">
            {items.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        )}
        <Mark mark={asObject(value["mark"])} />
      </>
    );
  }
  if (kind === "quantity") {
    const shown =
      display === "short" ? asString(value["short"]) : asString(value["text"]);
    const basis = asString(value["basis"]);
    return (
      <>
        <span className="mono">{shown}</span>
        {basis === null ||
        basis === "counted" ||
        basis === "declared" ? null : (
          <span className="report-basis">{basis}</span>
        )}
      </>
    );
  }
  if (kind === "status") {
    const status = asString(value["status"]) ?? "unknown";
    const reason = asString(value["reason"]);
    return (
      <>
        <Led
          state={LED_FOR_STATUS[status] ?? "unknown"}
          word={asString(value["word"]) ?? status}
        />
        {reason === null ? null : (
          <span className="report-reason">{reason}</span>
        )}
      </>
    );
  }
  return (
    <>
      <Led state="unknown" word="unknown" />
      <span className="report-reason">{asString(value["reason"])}</span>
    </>
  );
}

function Facts({ block }: { readonly block: JsonObject }) {
  const heading = asString(block["heading"]);
  return (
    <div className="report-facts-block">
      {heading === null ? null : <h3>{heading}</h3>}
      <dl className="report-facts">
        {objects(block["items"]).map((item, index) => (
          <div key={index}>
            <dt>{asString(item["label"])}</dt>
            <dd>
              <ReportValue value={asObject(item["value"]) ?? {}} />
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Table({ block }: { readonly block: JsonObject }) {
  const caption = asString(block["caption"]) ?? "";
  const display = asString(block["display"]) ?? "full";
  const heading = asString(block["heading"]);
  const columns = asArray(block["columns"]).map((column) => String(column));
  return (
    <div className="report-table-block">
      {heading === null ? null : <h3>{heading}</h3>}
      <div
        className="table-scroll"
        tabIndex={0}
        role="region"
        aria-label={caption}
      >
        <table className="report-table">
          <caption>{caption}</caption>
          <thead>
            <tr>
              {columns.map((column) => (
                <th scope="col" key={column}>
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {objects(block["rows"]).map((row, rowIndex) => (
              <tr key={rowIndex}>
                {objects(row["cells"]).map((cell, cellIndex) =>
                  cellIndex === 0 ? (
                    <th scope="row" key={cellIndex}>
                      <ReportValue value={cell} display={display} />
                    </th>
                  ) : (
                    <td key={cellIndex}>
                      <ReportValue value={cell} display={display} />
                    </td>
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** The topology the report recorded, drawn by the workspace's own diagram component. */
function Diagram({ block }: { readonly block: JsonObject }) {
  const layout: TopologyLayout = {
    nodes: objects(block["nodes"]).map((node) => ({
      id: asString(node["id"]) ?? "",
      role: asString(node["role"]) ?? "",
      component: asString(node["component"]),
      x: asNumber(node["x"]) ?? 0,
      y: asNumber(node["y"]) ?? 0,
    })),
    edges: objects(block["edges"]).map((edge) => ({
      from: asString(edge["from"]) ?? "",
      to: asString(edge["to"]) ?? "",
      label: asString(edge["label"]) ?? "",
      x1: asNumber(edge["x1"]) ?? 0,
      y1: asNumber(edge["y1"]) ?? 0,
      x2: asNumber(edge["x2"]) ?? 0,
      y2: asNumber(edge["y2"]) ?? 0,
    })),
    width: asNumber(block["width"]) ?? 0,
    height: asNumber(block["height"]) ?? 0,
    description: asString(block["description"]) ?? "",
  };
  return (
    <figure className="report-diagram">
      <div className="topology-scroll">
        <TopologyDiagram layout={layout} id="report-topology" />
      </div>
      <figcaption>{layout.description}</figcaption>
    </figure>
  );
}

/** Ranges on a shared scale per objective; the table beside it carries the numbers. */
function Chart({ block }: { readonly block: JsonObject }) {
  return (
    <figure className="report-chart">
      <figcaption>{asString(block["description"])}</figcaption>
      {objects(block["series"]).map((series) => {
        const bars = objects(series["bars"]);
        const numbers = bars.flatMap((bar) => {
          const value = asObject(bar["value"]) ?? {};
          return [value["lower"], value["upper"], value["value"]]
            .map(asNumber)
            .filter((number): number is number => number !== null);
        });
        const max = Math.max(1, ...numbers);
        const min = Math.min(0, ...numbers);
        return (
          <div className="report-series" key={asString(series["objective"])}>
            <p className="report-series-title">
              {asString(series["objective"])} · {asString(series["unit"])}
            </p>
            {bars.map((bar) => {
              const value = asObject(bar["value"]) ?? {};
              return (
                <RangeBar
                  key={asString(bar["label"])}
                  label={asString(bar["label"]) ?? ""}
                  low={asNumber(value["lower"]) ?? asNumber(value["value"])}
                  high={asNumber(value["upper"]) ?? asNumber(value["value"])}
                  point={asNumber(value["value"])}
                  min={min}
                  max={max}
                />
              );
            })}
          </div>
        );
      })}
    </figure>
  );
}

function Block({ block }: { readonly block: JsonObject }) {
  const kind = asString(block["kind"]);
  if (kind === "facts") {
    return <Facts block={block} />;
  }
  if (kind === "table") {
    return <Table block={block} />;
  }
  if (kind === "quote") {
    return (
      <figure className="report-quote">
        <figcaption className="report-label">
          {asString(block["label"])}
        </figcaption>
        <blockquote>{asString(block["text"])}</blockquote>
        <p className="report-attribution">{asString(block["attribution"])}</p>
      </figure>
    );
  }
  if (kind === "callout") {
    return (
      <p className="report-callout">
        <span className="report-label">{asString(block["label"])}</span>
        <strong>{asString(block["text"])}</strong>
      </p>
    );
  }
  if (kind === "paragraph") {
    return <p>{asString(block["text"])}</p>;
  }
  if (kind === "diagram") {
    return <Diagram block={block} />;
  }
  if (kind === "chart") {
    return <Chart block={block} />;
  }
  if (kind === "commands") {
    const lines = asArray(block["lines"]).map((line) => String(line));
    return (
      <div className="report-commands">
        {lines.length === 0 ? null : (
          <CopyPlate command={lines.join("\n")} label="Copy the next steps" />
        )}
        <p className="report-reason">{asString(block["note"])}</p>
      </div>
    );
  }
  if (kind === "not_yet") {
    const hint = asString(block["hint"]);
    return (
      <div className="report-not-yet" role="note">
        <Led state="unknown" word="Not yet" />
        <p>
          {asString(block["what"])}. Next step: {asString(block["step"])}.
        </p>
        {hint === null ? null : <code>{hint}</code>}
      </div>
    );
  }
  return null;
}

export function ReportSlide({ section }: { readonly section: JsonObject }) {
  const number = asString(section["number"]) ?? "";
  const appendix = asString(section["kind"]) === "appendix";
  const detail = asArray(section["detail_in"]).map((item) => String(item));
  const note = asObject(section["note"]);
  return (
    <>
      <p className="slide-marker mono">
        {appendix ? `Appendix ${number}` : `Section ${number}`}
      </p>
      <h2 id="slide-title" className="slide-title">
        {asString(section["title"])}
      </h2>
      <p className="slide-subtitle">{asString(section["subtitle"])}</p>
      {detail.length === 0 ? null : (
        <p className="slide-detail">
          Detail in appendix {detail.join(" and ")}.
        </p>
      )}
      {note === null ? null : (
        <aside className="slide-note" aria-label="Proposed by model">
          <p className="report-label">
            {asString(note["label"])} · {asString(note["model"])}
          </p>
          <p>{asString(note["text"])}</p>
        </aside>
      )}
      {objects(section["blocks"]).map((block, index) => (
        <Block block={block} key={index} />
      ))}
    </>
  );
}
