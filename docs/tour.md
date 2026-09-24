<!-- SPDX-License-Identifier: Apache-2.0 -->

# A guided tour: one design, five ways in

OAK can be driven from a browser, from the command line (the CLI), over plain HTTP (the
REST API), and by an AI assistant. This tour shows that they are all the same thing
underneath. You will run the example design once entirely offline, with the local CLI.
Then you'll take
**one** server-side case through the other four ways in, one step at a time, and finish
by checking that both runs compiled exactly the same design.

It takes about twenty minutes. Every command and every output below comes from a real run
against OAK Community `0.8.0`.

| Part | Where it happens | What it shows |
|---|---|---|
| [1. Warm-up](#part-1--warm-up-the-whole-journey-offline) | The local CLI, with no server | The whole journey, and the design fingerprint to compare against later |
| [2. The relay](#part-2--the-relay-one-case-through-four-interfaces) | The browser, `curl`, the remote CLI and an AI assistant over MCP | One case handed from interface to interface |
| [3. How MCP works](#part-3--how-the-mcp-server-works) | — | What an assistant actually sends, and what it may never do |
| [4. REST in brief](#part-4--rest-in-brief) | — | Headers, versions and slow jobs, for your own scripts |

## Before you start

- **The Docker stack is running** (see the [README](../README.md#the-docker-way-the-browser-workspace)),
  and `curl http://127.0.0.1:8080/version` reports `0.8.0`.
- **The command line is set up** with `uv sync --frozen` (see the
  [README](../README.md#the-source-way-the-command-line)).
- **Run everything from the root of your checkout**, the `OAK` folder that holds
  `compose.yaml`.
- **`jq` is installed.** It's a small tool for reading and trimming JSON, and the
  commands below use it to keep long replies short. Recent macOS versions include it, and
  on Linux it's usually one package away (for example `sudo apt install jq`).
- **The server hasn't seen this example yet.** A case's id comes from the brief, so the
  example can be started only once per server. A second attempt is refused with
  `409 OAK-EXPECTED-VERSION`. If you've already used it, see
  [Starting over](#starting-over).

## Part 1 — Warm-up: the whole journey offline

The local CLI keeps a case in an ordinary folder and needs no server at all. Run the
complete example in a scratch folder:

```bash
uv run oak init tour-offline && cd tour-offline
uv run oak design ../examples/briefs/public-manual-qa.yaml
uv run oak confirm --answers ../examples/briefs/public-manual-qa-answers.yaml
uv run oak candidates
uv run oak evaluate candidate-03
printf 'Balanced trade-off between quality, cost, and operability.\n' > decision.md
uv run oak select candidate-03 --rationale-file decision.md
uv run oak assure candidate-03 --output ./assurance
uv run oak plan candidate-03 --target ../examples/targets/local-fixture.yaml --output ./bundle
uv run oak export --output ../tour-offline-export
cd ..
```

```text
Design case design-case.public-manual-qa@0.1.1 is needs_confirmation with 5 questions
Recorded design-case.public-manual-qa@0.1.2 as ready_for_candidates
ID            VARIANT                    STATUS      FRONTIER  REJECTIONS
candidate-00  simpler_baseline           feasible    true      0
candidate-01  minimum_sufficient         feasible    true      0
candidate-03  balanced_enterprise        feasible    true      0
candidate-04  high_assurance_sovereign   infeasible  false     1
Evaluation evaluation-result.candidate-03 is pass
Selected candidate-03 in decision.candidate-03
Wrote assurance.candidate-03 to assurance
Compiled bundle.candidate-03.target.local-fixture to bundle; no target action was invoked
Exported design-case.public-manual-qa@0.1.7 to ../tour-offline-export
```

Each `@0.1.x` is the case's version. Every step creates a new version rather than editing
the old one. Now note the **fingerprint of the compiled design**. It's the SHA-256 digest
of the semantic manifest, the file that records what the design *means*:

```bash
jq -r '.artifact_index[] | select(.id | startswith("semantic.")) | .digest' tour-offline-export/manifest.json
```

```text
sha256:2ef34758128e13038d26b82847589b2b0ec2c5f25ba6ba56982a520a92a34d63
```

Keep it for the end of Part 2. The server hasn't been involved at all, and this case lives
only in `tour-offline/`.

## Part 2 — The relay: one case through four interfaces

This time the case lives on the server, where the browser, `curl`, the remote CLI and an
AI assistant can all see it. Each step uses a different way in.

### Step 1 — Create and interpret the case in the browser

Open <http://127.0.0.1:5173>. Under **Describe what you want to build**:

1. tick **I have a structured YAML or JSON brief instead**;
2. set **Brief file name** to `public-manual-qa.yaml`;
3. paste the contents of [`examples/briefs/public-manual-qa.yaml`](../examples/briefs/public-manual-qa.yaml)
   into **Brief content**;
4. click **Create case**. The case page opens with status `draft` and version `0.1.0`;
5. leave the reading mode on **Deterministic** and click **Interpret brief**.

The status becomes `needs_confirmation`, version `0.1.1`, with **5** open questions. The
audit timeline at the bottom already shows `case_created` and `brief_interpreted`. The
[manual](manual/OAK-Community-Manual.pdf) has screenshots of these screens.

### Step 2 — Read the questions with `curl`

The REST API is plain HTTP, so anything that can make a web request can use it:

```bash
curl -s http://127.0.0.1:8080/v1/design-cases/design-case.public-manual-qa \
  | jq '.case.unresolved_questions[] | {id, question, reason}'
```

```json
{
  "id": "question.model-hardware",
  "question": "Which approved model licence and measured target hardware apply?",
  "reason": "Model eligibility and measured capacity can make generated-answer variants infeasible."
}
{
  "id": "question.production-use",
  "question": "Confirm whether production data is permitted for this design case.",
  "reason": "This changes the data boundary, controls, and deployment eligibility."
}
```

…and three more: action autonomy, data classification, and document volume. Every
question says why it matters.

### Step 3 — Answer them from the remote CLI

The `oak` command gains `--server` and does the same job against the server's copy of
the case. In remote mode you always name the case:

```bash
uv run oak --server http://127.0.0.1:8080 questions design-case.public-manual-qa
uv run oak --server http://127.0.0.1:8080 confirm design-case.public-manual-qa \
  --answers examples/briefs/public-manual-qa-answers.yaml
```

```text
question.model-hardware: Which approved model licence and measured target hardware apply? [open]
question.production-use: Confirm whether production data is permitted for this design case. [open]
question.action-autonomy: Confirm the maximum action autonomy permitted for this system. [open]
question.data-classification: Confirm the highest data classification used by this design. [open]
question.data-volume: What document volume and update cadence must the design support? [open]
Recorded design-case.public-manual-qa@0.1.2 as ready_for_candidates
```

The last line is exactly what the local CLI printed in Part 1, because the same code does
the work.

### Step 4 — An AI assistant generates and evaluates the options

Now play the part of an AI assistant. An assistant talks to OAK's MCP server by sending
lines of JSON to it and reading the replies. This helper does exactly that for one
request: it starts the server inside the `api` container, sends the mandatory `initialize`
greeting and then your request, and prints the reply:

```bash
oak_mcp() {
  printf '%s\n' \
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}' \
    "$1" | docker compose exec -T api oak-mcp | tail -n 1
}
```

Ask for the options. Every tool that changes an existing case needs two extra arguments.
The first is `expected_version`, the version you last saw, so OAK refuses rather than
overwrites if someone else got there first. The second is `idempotency_key`, a unique
label that makes a retried request harmless:

```bash
OP=$(oak_mcp '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"oak_candidates_generate","arguments":{"case_id":"design-case.public-manual-qa","expected_version":"0.1.2","idempotency_key":"agent-generate-0001"}}}' \
  | jq -r '.result.structuredContent.operation_id')
echo "$OP"
```

Generating options is a slow job, so the reply is a ticket (an **operation**, whose id
starts `operation.`) rather than the result. A background `worker` picks it up. Wait a
moment, then check on it:

```bash
oak_mcp '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"oak_operation_get","arguments":{"operation_id":"'"$OP"'"}}}' \
  | jq -c '.result.structuredContent | {state, result: .result.status}'
```

```json
{"state":"succeeded","result":"candidates_ready"}
```

List the options, including the one that was ruled out and why:

```bash
oak_mcp '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"oak_candidates_list","arguments":{"case_id":"design-case.public-manual-qa"}}}' \
  | jq -r '.result.structuredContent.items[] | [.id, .status, (.rejection_reasons | join("; "))] | @tsv'
```

```text
candidate-00	feasible
candidate-01	feasible
candidate-03	feasible
candidate-04	infeasible	constraint.hardware: Required accelerator compatibility is unconfirmed.
```

Then evaluate `candidate-03`, which is another slow job, at the version the case has now
reached (`0.1.3`):

```bash
OP=$(oak_mcp '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"oak_candidate_evaluate","arguments":{"case_id":"design-case.public-manual-qa","candidate_id":"candidate-03","expected_version":"0.1.3","idempotency_key":"agent-evaluate-0001"}}}' \
  | jq -r '.result.structuredContent.operation_id')
sleep 2
oak_mcp '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"oak_operation_get","arguments":{"operation_id":"'"$OP"'"}}}' \
  | jq -c '.result.structuredContent | {state, evaluation: .result.evaluation.id, outcome: .result.evaluation.status, case_version: .result.case.version}'
```

```json
{"state":"succeeded","evaluation":"evaluation-result.candidate-03","outcome":"pass","case_version":"0.1.4"}
```

A real assistant does all of this for you, including the waiting. You'd ask it something
like "generate the options for the manual-QA case and evaluate the balanced one", and it
would choose these tools itself.

### Step 5 — You choose the design (the assistant can't)

Choosing a design is a decision that someone has to own, so there is **no MCP tool for
it**. If an assistant tries anyway:

```bash
oak_mcp '{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"oak_candidate_select","arguments":{"case_id":"design-case.public-manual-qa","candidate_id":"candidate-03"}}}'
```

```json
{"error": {"code": -32602, "data": {"code": "OAK-TOOL-UNKNOWN"}, "message": "tool is not available"}, "id": 7, "jsonrpc": "2.0"}
```

So a person decides. Back in the browser, open the case, click **Open the full
comparison**, type a rationale under `candidate-03`, for example *Balanced trade-off
between quality, cost, and operability.*, and click **Select candidate-03**. The decision
page shows your choice, who made it and when, and why each alternative lost. The case is
now at `0.1.5`, `candidate_selected`.

The CLI can make the same decision if you prefer. This reuses the rationale file from
Part 1:

```bash
uv run oak --server http://127.0.0.1:8080 select candidate-03 \
  --case design-case.public-manual-qa --rationale-file tour-offline/decision.md
```

### Step 6 — The assistant finishes the plan

With the decision made, the assistant may carry on. It creates the assurance plan, and
then compiles the bundle against the example target. The **target profile** describes
the machine the plan is for: its processor, memory, network and which operations are
allowed on it. It goes in as JSON, converted here from the YAML file with the Python
that OAK installed:

```bash
oak_mcp '{"jsonrpc":"2.0","id":8,"method":"tools/call","params":{"name":"oak_assurance_plan_create","arguments":{"case_id":"design-case.public-manual-qa","candidate_id":"candidate-03","expected_version":"0.1.5","idempotency_key":"agent-assure-00001"}}}' \
  | jq -c '.result.structuredContent | {plan: .assurance_plan.id, status: .case.status, version: .case.version}'

TARGET=$(uv run python -c 'import json, sys, yaml; print(json.dumps(yaml.safe_load(open(sys.argv[1]))))' examples/targets/local-fixture.yaml)
OP=$(oak_mcp '{"jsonrpc":"2.0","id":9,"method":"tools/call","params":{"name":"oak_bundle_compile","arguments":{"case_id":"design-case.public-manual-qa","candidate_id":"candidate-03","target":'"$TARGET"',"expected_version":"0.1.6","idempotency_key":"agent-compile-00001"}}}' \
  | jq -r '.result.structuredContent.operation_id')
sleep 2
oak_mcp '{"jsonrpc":"2.0","id":10,"method":"tools/call","params":{"name":"oak_operation_get","arguments":{"operation_id":"'"$OP"'"}}}' \
  | jq -c '.result.structuredContent | {state, status: .result.case.status, version: .result.case.version, runner_plan: .result.runner_plan.status}'
```

```json
{"plan":"assurance.candidate-03","status":"assurance_planned","version":"0.1.6"}
{"state":"succeeded","status":"bundle_compiled","version":"0.1.7","runner_plan":"draft"}
```

The runner plan is a `draft`. Compiling never runs anything, and nothing that reaches OAK
over MCP can sign, approve or dispatch it.

### Step 7 — Check the result

**The audit trail** records every step, with the way in that each one came through:

```bash
curl -s http://127.0.0.1:8080/v1/design-cases/design-case.public-manual-qa/audit \
  | jq -r '.items[] | "\(.sequence)  \(.event_type)  via \(.interface_origin)  -> \(.case_version)"'
```

```text
1  case_created  via api  -> 0.1.0
2  brief_interpreted  via api  -> 0.1.1
3  claims_confirmed  via api  -> 0.1.2
4  candidates_generated  via mcp  -> 0.1.3
5  candidate_evaluated  via mcp  -> 0.1.4
6  candidate_selected  via api  -> 0.1.5
7  assurance_planned  via mcp  -> 0.1.6
8  bundle_compiled  via mcp  -> 0.1.7
```

The browser and the remote CLI both work through the REST API, so their steps say `api`.
The assistant's steps say `mcp`. The same timeline appears at the bottom of the case page
in the browser.

**The fingerprint.** Export the server's case with the remote CLI, check it with the
validator (which needs no server), and compare the fingerprint with Part 1:

```bash
uv run oak --server http://127.0.0.1:8080 export design-case.public-manual-qa --output ./tour-relay-export
uv run oak validate export ./tour-relay-export
jq -r '.artifact_index[] | select(.id | startswith("semantic.")) | .digest' tour-relay-export/manifest.json
```

```text
Exported design-case.public-manual-qa@0.1.7 to tour-relay-export
Export is valid: design-case.public-manual-qa@0.1.7 (bundle_compiled)
sha256:2ef34758128e13038d26b82847589b2b0ec2c5f25ba6ba56982a520a92a34d63
```

**It's the same fingerprint as the offline run.** Four ways in on the server and one
offline, a database instead of a folder, a container instead of your laptop, and the
compiled design is byte-for-byte identical. That's what "deterministic" buys you: anyone
can re-run a design and check they get the same answer.

Not *every* file matches. The decision record, for example, contains the time it was made
and who made it, so its own digest differs between the two runs. The semantic manifest
leaves those out on purpose, which is what makes it comparable.

## Part 3 — How the MCP server works

[MCP (the Model Context Protocol)](https://modelcontextprotocol.io) is a standard way for
an AI assistant to use outside tools. Here's what happens when an assistant uses OAK:

1. **The assistant starts `oak-mcp` as a helper program** and keeps it running for the
   conversation. Under Docker, the command is `docker compose exec -T api oak-mcp`, which
   runs inside the `api` container and so shares its database. From a source checkout,
   `oak-mcp` (or `oak mcp serve`) needs `OAK_DATABASE_URL` pointing at a PostgreSQL
   database, as the API does.
2. **They talk in lines of JSON** over the helper's standard input and output, using
   JSON-RPC 2.0, a simple standard for sending numbered requests and matching replies as
   JSON. First comes `initialize`, which agrees on a protocol version (`2025-06-18` or
   `2025-03-26`). Then comes `tools/list`, which returns the menu of tools. Each tool has a
   description and a schema, a strict description of which arguments it accepts.
3. **The assistant calls tools** with `tools/call`. Every call is checked against the
   tool's schema before anything happens, and then handed to the same application code
   the browser and the CLI use.
4. **Refusals come back as data, not crashes.** If OAK says no, for example because of a
   stale version or a missing answer, the reply has `"isError": true` and a stable `OAK-*`
   code the assistant can act on. An unknown tool or malformed arguments get a
   protocol-level error instead.

### The eleven tools

| Tool | What it does | Changes the case? |
|---|---|---|
| `oak_design_case_create` | Creates a case from brief text (stored as untrusted data) | yes |
| `oak_design_case_get` | Reads a case and OAK's structured reading of its brief (the "intent") | no |
| `oak_design_case_interpret` | Interprets the brief. Deterministic unless `interpreter` says `online` or `local` | yes |
| `oak_questions_list` | Lists the open questions | no |
| `oak_claims_confirm` | Records answers. It needs a named `actor` | yes |
| `oak_candidates_generate` | Starts generating options (a slow job) | yes |
| `oak_candidates_list` | Lists options with their rejection reasons | no |
| `oak_candidate_evaluate` | Starts evaluating one option (a slow job) | yes |
| `oak_assurance_plan_create` | Creates the assurance plan for the chosen option | yes |
| `oak_bundle_compile` | Starts compiling the bundle for a target profile (a slow job; nothing is executed) | yes |
| `oak_operation_get` | Checks on a slow job | no |

A contract test pins this exact list, so a new tool can't slip in unnoticed.

### What an assistant can't do through OAK

None of the following exists as a tool, for two different reasons:

- **Ruled out for good.** An assistant can never sign or approve a plan, dispatch
  anything to the runner, read files, run commands, look up secrets such as passwords or
  keys, or change your AI-model settings. The [capability matrix](interfaces.md#capability-matrix)
  marks each of these "never" for MCP. The ban on command, file, secret, approval and
  runner tools is written into the [compatibility policy](compatibility.md) for every
  future version.
- **Left to a person on purpose.** Choosing a design is a decision someone must own, so
  selection isn't offered over MCP. It stays available in the browser, the CLI and the
  REST API.

Two more guard rails:

- **It acts as the local user.** Every tool accepts an `actor`, which is required when
  recording answers. Anything other than the configured local user is refused with
  `"isError": true` and the message `OAK-ACTOR-DENIED: local actor is not authorized`.
- **It won't spend your money by accident.** Interpretation defaults to
  `deterministic`. An assistant has to ask for `"interpreter": "online"` explicitly
  before a brief is sent to Hugging Face on your stored token.

### Connecting a real assistant

Most AI assistants and code editors that support MCP take a JSON entry like this one. Use
the full path to your checkout, and keep the Docker stack running:

```json
{
  "mcpServers": {
    "oak": {
      "command": "docker",
      "args": ["compose", "-f", "/full/path/to/OAK/compose.yaml", "exec", "-T", "api", "oak-mcp"]
    }
  }
}
```

- If the assistant can't find `docker`, use the full path that `which docker` prints.
  Assistants often start helpers with a minimal `PATH`, the list of folders that is
  searched for programs.
- Each assistant session starts its own `oak-mcp` process, and one process serves one
  assistant ([`RR-010`](security/residual-risk.md)).
- [interfaces.md](interfaces.md#permission-model) has the complete permission model.

## Part 4 — REST in brief

If you're scripting against the API yourself:

- **Reading** needs nothing special: `GET /v1/design-cases/{id}`, `…/candidates`,
  `…/audit`, `…/artifacts`, `…/export`.
- **Changing** a case needs an `Idempotency-Key` header (at least 16 characters). Anything
  after creation also needs an `If-Match` header holding the version you last saw, in
  quotes: `If-Match: "0.1.2"`. These are standard HTTP headers. A reply that returns the
  changed case carries its new version in an `ETag` header. A stale version is refused
  with HTTP status `409` (Conflict) and the code `OAK-EXPECTED-VERSION`. Re-read the case
  and try again.
- **Slow jobs** (generate, evaluate, compile) return HTTP status `202` (Accepted) with an
  operation. Poll `GET /v1/operations/{operation_id}` until `state` is `succeeded`,
  `failed` or `cancelled`. Only the `worker` container makes progress on them.
- **Identity** comes from the optional `X-OAK-Actor` and `X-OAK-Tenant` headers, which
  default to the local user and tenant. A tenant is a separate space for one
  organisation's data, and Community has just one, called `local`.

Here is the create call, for example:

```bash
jq -n --rawfile c examples/briefs/public-manual-qa.yaml \
  '{original_name: "public-manual-qa.yaml", content: $c}' \
  | curl -s -X POST http://127.0.0.1:8080/v1/design-cases \
      -H 'Content-Type: application/json' \
      -H 'Idempotency-Key: my-first-create-0001' \
      -d @- \
  | jq '{id: .case.id, version: .case.version, status: .case.status}'
```

The committed contract is [`openapi/oak.openapi.json`](../openapi/oak.openapi.json). A
running API also serves a clickable explorer at <http://127.0.0.1:8080/docs>, which is
handy for poking around. It comes from the web framework and isn't part of the versioned
contract.

> **A shell gotcha.** In `zsh`, the default shell on macOS, `"$CASE:confirm"` doesn't mean
> "the variable, then `:confirm`". `zsh` reads `:c` as an instruction to modify the
> variable. Write `"${CASE}:confirm"` with braces, or spell the case id out as this tour
> does.

## Starting over

- **A command-line case** is just a folder. Delete `tour-offline/` and the export folders
  when you're done.
- **The server's cases** can only be removed all at once, together with everything else
  the stack stores: `docker compose down --volumes`. **That deletes every case on the
  server**, and also any Hugging Face token you stored there. Then run
  `docker compose up -d --build` for a clean start.

## Where next

- [The user manual](manual/OAK-Community-Manual.pdf) has screenshots of every workspace
  screen, and covers the signed runner: signing, approving, dispatching, and what each
  refusal means.
- [compiler-flow.md](compiler-flow.md) explains what each stage produces and why it's
  deterministic.
- [interfaces.md](interfaces.md) is the capability matrix: which interface can do what.
- [CONTRIBUTING.md](../CONTRIBUTING.md#where-you-could-help) is a good next stop if the
  tour gave you ideas.
