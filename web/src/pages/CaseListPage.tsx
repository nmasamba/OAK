// SPDX-License-Identifier: Apache-2.0
import {
  useEffect,
  useState,
  type ChangeEvent,
  type DragEvent,
  type FormEvent,
} from "react";

import {
  createDesignCase,
  getModels,
  listDesignCases,
  type JsonObject,
  type ModelStatusResponse,
} from "../generated/api";
import { rememberInterpretMode } from "../interpretMode";
import { journeyLabel, journeyProgress } from "../journey";
import { ModeChooser, ModeDetail, type InterpretMode } from "../ModeSelect";
import { currentModelToken } from "../modelToken";
import { ProblemAlert, toActionFailure, type ActionFailure } from "../problems";
import { useRouter } from "../router";
import { ageOf, asString, newIdempotencyKey } from "../support";
import { Chip, Icon, Keycap, Tile } from "../ui";

type ListState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly items: readonly JsonObject[] }
  | { readonly kind: "failed"; readonly failure: ActionFailure };

/** A brief read from a file. Its text is held here and never shown on the page. */
interface Attachment {
  readonly name: string;
  readonly size: number;
  readonly text: string;
}

const BRIEF_KINDS = /\.(md|txt|yaml|yml|json)$/i;
const BRIEF_LIMIT = 256 * 1024;

function formatSize(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

export function CaseListPage() {
  const { navigate } = useRouter();
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [originalName, setOriginalName] = useState("brief.md");
  const [content, setContent] = useState("");
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createFailure, setCreateFailure] = useState<ActionFailure | null>(
    null,
  );

  // The three ways a brief can be read. What the status document says about each needs
  // the capability token; without it the chooser still shows the choice and the title
  // says why the model modes are not available here.
  const [mode, setMode] = useState<InterpretMode>("deterministic");
  const [models, setModels] = useState<ModelStatusResponse | null>(null);
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
    listDesignCases()
      .then((response) => setState({ kind: "ready", items: response.items }))
      .catch((error: unknown) =>
        setState({ kind: "failed", failure: toActionFailure(error) }),
      );
  };

  useEffect(load, []);

  const attach = async (file: File) => {
    setRefusal(null);
    if (!BRIEF_KINDS.test(file.name)) {
      setRefusal(`${file.name} is not Markdown, text, YAML or JSON.`);
      return;
    }
    if (file.size > BRIEF_LIMIT) {
      setRefusal("Over 256 KiB. Nothing was read.");
      return;
    }
    const text = await file.text();
    setAttachment({ name: file.name, size: file.size, text });
    setOriginalName(file.name);
  };

  const onPick = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file !== undefined) {
      void attach(file);
    }
  };

  const onDrop = (event: DragEvent<HTMLFormElement>) => {
    event.preventDefault();
    setOver(false);
    const file = event.dataTransfer.files[0];
    if (file !== undefined) {
      void attach(file);
    }
  };

  const removeAttachment = () => {
    setAttachment(null);
    setOriginalName("brief.md");
  };

  const onCreate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCreating(true);
    setCreateFailure(null);
    createDesignCase(
      {
        original_name: originalName,
        content: attachment === null ? content : attachment.text,
      },
      { idempotencyKey: newIdempotencyKey("create-case") },
    )
      .then((response) => {
        const caseId = asString(response.case["id"]);
        if (caseId !== null) {
          rememberInterpretMode(caseId, mode);
          navigate(`/cases/${encodeURIComponent(caseId)}`);
        }
      })
      .catch((error: unknown) => setCreateFailure(toActionFailure(error)))
      .finally(() => setCreating(false));
  };

  const dropState = over
    ? "over"
    : attachment !== null
      ? "accepted"
      : refusal !== null
        ? "refused"
        : "idle";

  return (
    <div className="home">
      <h1 id="page-heading" className="home-title">
        What do you want to build?
      </h1>

      <form
        className="composer"
        aria-label="New case"
        data-drop={dropState}
        onSubmit={onCreate}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
      >
        {attachment === null ? (
          <>
            <label htmlFor="brief-prompt" className="composer-label">
              Brief prompt
            </label>
            <textarea
              id="brief-prompt"
              name="brief-prompt"
              className="composer-prompt"
              value={content}
              onChange={(event) => setContent(event.target.value)}
              rows={3}
              placeholder="Describe it in your own words…"
              required
              spellCheck={false}
            />
          </>
        ) : (
          <p className="composer-label">Brief prompt</p>
        )}

        <div className="composer-chips">
          {attachment !== null ? (
            <Chip
              tone="brass"
              icon="file"
              mono
              onRemove={removeAttachment}
              removeLabel={`Remove ${attachment.name}`}
              title="Attached. Its text is sent, not shown."
            >
              {attachment.name} · {formatSize(attachment.size)}
            </Chip>
          ) : (
            <span className="chip chip-mono composer-name-chip">
              <Icon name="file" />
              <label htmlFor="brief-name" className="visually-hidden">
                Brief file name
              </label>
              <input
                id="brief-name"
                name="brief-name"
                className="composer-name"
                value={originalName}
                onChange={(event) => setOriginalName(event.target.value)}
                required
                maxLength={240}
                spellCheck={false}
                title="The file name the brief is stored under"
              />
            </span>
          )}
          <span role="alert" className="composer-refusal">
            {refusal === null ? null : (
              <Chip tone="bad" icon="warning">
                {refusal}
              </Chip>
            )}
          </span>
        </div>

        <div className="composer-row">
          <label className="ico" title="Attach a brief">
            <Icon name="attach" size={22} />
            <span className="visually-hidden">Attach a brief</span>
            <input
              type="file"
              accept=".md,.txt,.yaml,.yml,.json"
              className="visually-hidden"
              onChange={onPick}
            />
          </label>
          <span className="spacer" />
          <ModeChooser
            id="brief-mode"
            value={mode}
            onChange={setMode}
            status={models}
            tokenPresent={tokenPresent}
          />
          <Keycap
            type="submit"
            className="keycap-round"
            icon="up"
            aria-label="Create case"
            busy={creating}
          />
        </div>
        <ModeDetail value={mode} status={models} tokenPresent={tokenPresent} />
        <div aria-live="polite">
          {createFailure !== null && (
            <ProblemAlert failure={createFailure} onReload={load} />
          )}
        </div>
      </form>

      <section aria-labelledby="case-list-heading" className="recent">
        <h2 id="case-list-heading">Design cases</h2>
        <div aria-live="polite">
          {state.kind === "loading" && <p>Loading cases…</p>}
          {state.kind === "failed" && (
            <ProblemAlert failure={state.failure} onReload={load} />
          )}
          {state.kind === "ready" && state.items.length === 0 && (
            <p>No cases yet.</p>
          )}
        </div>
        {state.kind === "ready" && state.items.length > 0 && (
          <ul className="tiles">
            {state.items.map((item) => {
              const id = asString(item["id"]) ?? "";
              const status = asString(item["status"]);
              const updated = asString(item["updated_at"]);
              return (
                <li key={id}>
                  <Tile
                    to={`/cases/${encodeURIComponent(id)}`}
                    title={asString(item["title"]) ?? id}
                    status={status ?? "unknown"}
                    progress={journeyProgress(status)}
                    stepLabel={journeyLabel(status)}
                    meta={updated === null ? undefined : ageOf(updated)}
                  />
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
