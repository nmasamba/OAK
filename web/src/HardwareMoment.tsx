// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

import { Moment } from "./CaseRail";
import {
  confirmHardware,
  getJsonArtifact,
  type JsonObject,
} from "./generated/api";
import { ProblemAlert, toActionFailure, type ActionFailure } from "./problems";
import {
  asArray,
  asNumber,
  asObject,
  asReference,
  asString,
  etagFor,
  newIdempotencyKey,
} from "./support";
import { Chip, CopyPlate, Keycap } from "./ui";

const PROPOSAL_REF = "oak.community/hardware_proposal_ref";
const SCAN_RECORD = "oak.community/hardware_scan";
const OPEN_STATES = new Set(["needs_confirmation", "ready_for_candidates"]);
const RUNTIME_WORDS: Readonly<Record<string, string>> = {
  metal: "Metal",
  cuda: "CUDA",
  rocm: "ROCm",
};

function gib(value: unknown): string | null {
  const number = asNumber(value);
  return number === null ? null : `${number} GiB`;
}

/** What a hardware proposal says, one line per part; an unknown part says so. */
export function hardwareLines(proposal: JsonObject): readonly string[] {
  const platform = asObject(proposal["platform"]) ?? {};
  const cpu = asObject(proposal["cpu"]) ?? {};
  const memory = asObject(proposal["memory"]) ?? {};
  const lines: string[] = [];
  const cores = asNumber(cpu["physical_cores"]);
  lines.push(
    `CPU: ${asString(cpu["model"]) ?? "model unknown"}` +
      (cores === null ? "" : `, ${cores} cores`) +
      ` (${asString(platform["architecture"]) ?? "architecture unknown"})`,
  );
  const ram = gib(memory["ram_gib"]);
  lines.push(
    ram === null
      ? "Memory: unknown"
      : `Memory: ${ram}${memory["unified"] === true ? ", shared with the GPU" : ""}`,
  );
  const accelerators = proposal["accelerators"];
  if (accelerators === null) {
    lines.push("GPU: unknown");
  } else if (asArray(accelerators).length === 0) {
    lines.push("GPU: none found");
  }
  for (const entry of asArray(accelerators)) {
    const gpu = asObject(entry) ?? {};
    const runtime = asString(gpu["runtime"]);
    const size =
      gpu["unified_memory"] === true
        ? "unified memory"
        : (gib(gpu["memory_gib"]) ?? "memory unknown");
    lines.push(
      `GPU: ${asString(gpu["model"]) ?? "model unknown"} (${
        runtime === null
          ? "no runtime found"
          : (RUNTIME_WORDS[runtime] ?? runtime)
      }), ${size}`,
    );
  }
  const storage = gib(proposal["storage_gib"]);
  lines.push(storage === null ? "Storage: unknown" : `Storage: ${storage}`);
  return lines;
}

/** Why each unknown part is unknown, in the scan's own words. */
function unknownLines(proposal: JsonObject): readonly string[] {
  return asArray(proposal["unknown"]).flatMap((entry) => {
    const item = asObject(entry);
    const reason = item === null ? null : asString(item["reason"]);
    return reason === null ? [] : [reason];
  });
}

/**
 * The hardware a scan proposed for this case, and its confirmation. The scan runs on the
 * machine the design is for, never in the browser and never on the control plane's host,
 * so this moment only shows what a scan sent and lets the user confirm it.
 */
export function HardwareMoment({
  caseId,
  caseDocument,
  disabled,
  onChanged,
}: {
  readonly caseId: string;
  readonly caseDocument: JsonObject;
  readonly disabled: boolean;
  readonly onChanged: () => Promise<unknown>;
}) {
  const status = asString(caseDocument["status"]) ?? "";
  const version = asString(caseDocument["version"]) ?? "";
  const reference = asReference(
    (asObject(caseDocument["extensions"]) ?? {})[PROPOSAL_REF],
  );
  const intentReference = asReference(caseDocument["intent_ref"]);
  const [proposal, setProposal] = useState<JsonObject | null>(null);
  const [confirmedId, setConfirmedId] = useState<string | null>(null);
  const [confirmedAt, setConfirmedAt] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ActionFailure | null>(null);

  useEffect(() => {
    setProposal(null);
    if (reference !== null) {
      getJsonArtifact(caseId, reference)
        .then(setProposal)
        .catch(() => setProposal(null));
    }
  }, [caseId, reference?.id]);

  useEffect(() => {
    setConfirmedId(null);
    setConfirmedAt(null);
    if (intentReference !== null) {
      getJsonArtifact(caseId, intentReference)
        .then((intent) => {
          const record = asObject(
            (asObject(intent["extensions"]) ?? {})[SCAN_RECORD],
          );
          const confirmed = asReference(record?.["proposal_ref"]);
          setConfirmedId(confirmed === null ? null : confirmed.id);
          setConfirmedAt(asString(record?.["confirmed_at"]));
        })
        .catch(() => setConfirmedId(null));
    }
  }, [caseId, intentReference?.id, intentReference?.version]);

  const pending = reference !== null && reference.id !== confirmedId;
  const open = OPEN_STATES.has(status);
  if (!open && confirmedId === null) {
    return null;
  }

  const onConfirm = () => {
    if (reference === null) {
      return;
    }
    setBusy(true);
    setFailure(null);
    confirmHardware(caseId, reference.id, {
      idempotencyKey: newIdempotencyKey("hardware"),
      etag: etagFor(version),
    })
      .then(() => onChanged())
      .catch((error: unknown) => setFailure(toActionFailure(error)))
      .finally(() => setBusy(false));
  };

  if (pending && open) {
    return (
      <Moment fresh>
        <p>
          <Chip tone="info">proposed</Chip> A scan of the machine this design is
          for:
        </p>
        {proposal === null ? (
          <p className="timeline-meta">Reading the scan…</p>
        ) : (
          <>
            <ul className="hardware-lines">
              {hardwareLines(proposal).map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
            {unknownLines(proposal).length > 0 && (
              <ul className="hardware-unknowns">
                {unknownLines(proposal).map((line) => (
                  <li key={line}>
                    <Chip tone="unknown">unknown</Chip> {line}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
        <div className="moment-row">
          <Keycap
            onClick={onConfirm}
            busy={busy}
            busyLabel="Confirming…"
            disabled={disabled || busy || proposal === null}
          >
            Confirm hardware
          </Keycap>
        </div>
        {failure !== null && (
          <ProblemAlert failure={failure} onReload={() => void onChanged()} />
        )}
      </Moment>
    );
  }

  if (
    confirmedId !== null &&
    proposal !== null &&
    reference?.id === confirmedId
  ) {
    return (
      <Moment>
        <p>
          <Chip tone="ok">confirmed</Chip> Designed for this machine
          {confirmedAt === null
            ? ""
            : ` (scan confirmed ${confirmedAt.slice(0, 10)})`}
          :
        </p>
        <ul className="hardware-lines">
          {hardwareLines(proposal).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </Moment>
    );
  }

  if (!open) {
    return null;
  }
  return (
    <Moment>
      <p>
        Designing for a particular machine? Scan it where it runs, and its
        hardware comes here for you to confirm.
      </p>
      <CopyPlate
        command={`oak --server ${window.location.origin} scan ${caseId} --propose`}
        label="Copy the scan command"
      />
    </Moment>
  );
}
