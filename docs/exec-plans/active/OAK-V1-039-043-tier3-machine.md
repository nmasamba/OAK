<!-- SPDX-License-Identifier: Apache-2.0 -->

# OAK-V1-039–043: Tier 3, Batch B — the machine: hardware scanning, then native installation

**Directed by the owner on 2026-11-02.** Tier 3 of the owner's 2026-10-23 ranking was moved
ahead of 1.0 on 2026-10-29 and cut into three batches by `TIER-3-PROMPT.md` in the original
spec repo. Batch A merged on 2026-11-02 as PR #42 (`2608f24`). The owner then asked for
`main`'s CI to be made green and for Batch B to start. This plan is Batch B: hardware
scanning first, because the scan proposes the target the install goes onto, then native
installation. It bumps no version, cuts no tag, writes no decision record, signs nothing
and publishes nothing.

## Status

- Owner/agent: owner-directed coding agent
- Started: 2026-11-02
- Last updated: 2026-11-03 (M6, the closing review's fixes; the rehearsal and the consent sign-off wait for the owner)
- State: in-progress: code complete and open as PR #44 (https://github.com/nmasamba/OAK/pull/44); the llama.cpp rehearsal waits for the owner's approval of its downloads, and the consent text for the owner's sign-off
- Claimed tasks: `OAK-V1-039`–`OAK-V1-043`

One plan covers five task IDs: one for hardware scanning, three for native installation
(the records and the profile; the adapter and its operations; the platforms, the uninstall
and the documentation), as the prompt cuts it, and one for the review, the gates and the
PR. They continue the release-readiness series; `OAK-V1-038` is the image-build fix that
made `main` green again after Batch A.

**Where the branch starts.** The prompt says to branch from `origin/main` once its CI is
green. After PR #42 merged it was not: the arm64 job failed twice, once on two different
API image builds and once on a package the snapshot archive refused. `OAK-V1-038` fixes
both on `fix/image-package-index` (PR #43). This branch, `tier3-machine`, starts from that
fix (`7e96ed7`), so its CI is not red for a reason it does not own. Its PR, #44, targets
`main`; until the owner merges PR #43 it also shows #43's commits.

## Outcome

After this plan:

1. **OAK can tell what machine a design is for** (`OAK-V1-039`). One scanner reads the CPU
   model and cores, the memory, and each GPU's vendor, model, memory and runtime (Metal,
   CUDA or ROCm) through fixed argument vectors over five tools (`sysctl` and
   `system_profiler` on macOS; `lscpu`, `nvidia-smi` and `rocm-smi` on Linux), parsing
   machine-readable output only and reporting `unknown` with a reason whenever a tool is
   absent. Apple silicon's memory is reported as unified; confirmed, the GPU's memory is the
   system memory it shares, never an invented figure. The
   scan also says whether Docker and uv are present and recommends installing whichever is
   missing (the owner's addition), and never installs anything. The runner's `inventory`
   operation and a local `oak scan` command share the module. The result enters the case
   as a **proposal the user confirms**, the way an interpretation proposal does; the
   confirmed values feed `spec.hardware`, so `constraint.hardware`, the estimators and
   research's hardware class read them through the paths that already exist. REST and MCP
   accept a scan result as a proposal, because the scan runs where the hardware is and the
   API host is never the target; the web workspace shows the proposal and its confirmation
   as a moment on the case page. The raw inventory never leaves the machine, and the
   scanner writes no serial number, GPU UUID, host name or user name into the proposal.
2. **The records allow a native install, and say exactly what it relaxes** (`OAK-V1-040`).
   ADR-0019, beside ADR-0017, decides it; the target profile gains a `native` execution
   mode that maps each component to a typed harness kind the adapter knows, with typed
   parameters and nothing else; a consent document, a recorded and signed approval naming
   each relaxed control and its risk, comes before the install approval; the security
   invariants' "downloaded executable selection" rule is amended explicitly, naming the
   controls that make this mode acceptable; the register and the threat model say what
   remains.
3. **The runner installs the chosen architecture natively, proves it runs, and stops it**
   (`OAK-V1-041`). A native process adapter beside the container one downloads each
   artifact through a deliberately allowed network module that reaches only the hosts the
   acknowledged profile names, verifies its SHA-256 and size before anything executes,
   unpacks it without following a link or leaving its directory, starts it from the
   harness kind's argument template bound to loopback, smoke-tests it through its health
   probe, and **stops it**: per the owner, the point is to get a suitable AI system
   installed, and the user starts it when they want it. Uninstall removes exactly what the
   install created. Every step is journalled before and after; the runner refuses to stop
   or remove anything it does not own.
4. **Native installation runs on three platforms and leaves nothing behind**
   (`OAK-V1-042`). A stand-in harness lets the native journey run in `make check`, offline,
   on all three CI jobs, so `check-macos-arm64` proves a runner path for the first time; the
   uninstall is proven with a canary file beside the install that must survive; an example
   profile for llama.cpp's server and one small Hugging Face model is rehearsed by hand on
   the owner's machine with its digests recorded; `oak observe` works for a native
   installation; `platforms.md`, `operations.md`, `signed-runner.md`, the README and the
   manual gain the native path.
5. **Review, gates and PR** (`OAK-V1-043`).

## Context and invariants

- **Assumptions.** The development machine is an Apple silicon Mac with Docker Desktop;
  `sysctl` and `system_profiler` are present there, and CI's Linux runners have `lscpu`
  and no GPU. The NVIDIA and AMD paths are proven by recorded fixtures only, and
  `platforms.md` says so. The reference case holds no scan and no native profile, so no
  reference digest moves in this batch. `main`'s CI is green again once PR #43 merges;
  until then this branch carries its fix.
- **Invariants.** No production readiness claim. No authority bypass: dispatch, signing,
  approvals, enrollment and the runner's own verification stay in front of every
  install; research and the scan approve nothing; MCP gains only what the prompt names (a
  scan result as a proposal). The runner executes only executables on its code-level
  allowlist (today `docker`; this batch adds the five scan tools, and a native harness's
  own verified artifact under the rules ADR-0019 sets), with fixed argument vectors, a
  sanitized environment, timeouts and output limits, never a shell, a `PATH` the plan
  names, or a path a document names. No `command`, `shell`, `executable` or `argv` field
  in any canonical document; the argument template lives in the adapter, per harness
  kind. The import boundaries hold (`tools/check_boundaries.py`,
  `tests/integration/test_offline_boundary.py`); the download module is a deliberate,
  tested widening. `make check` stays offline: the stand-in is local. **Data
  minimization:** only the confirmed profile enters the case. **Byte stability:** the
  reference digests and the report golden do not move. **Fail closed:** an absent tool is
  `unknown`, never a guess; an artifact whose digest or size differs is never executed; a
  consent that names a different installation or omits a relaxed control refuses the
  install. `make check` is judged by counting `make: ***` lines, never two at once, with
  `OAK_TEST_DATABASE_URL` on the throwaway PostgreSQL on `127.0.0.1:15433`. The owner's
  `oak-community` Compose stack (5173, 8080) and its database (15432) are never touched.
  `docs/error-codes.md` is regenerated after every `src/` edit. No vendor attribution in
  commits or the PR. Any download of a real harness or model for the rehearsal waits for
  the owner's approval of each file by name, source and size.
- **Recipes** (`skills.md`): Runner safety and Security review (M1, M4, M5); Contract change
  (M2, M3); Domain use case and Interface adapter (M2); Workspace UI (M2, M5); Controlled
  installation and observation (M4, M5); Dependency and release (M5's CI jobs);
  Documentation and ADR throughout.
- **Files that matter.** `src/oak/runner/adapters.py` (`ALLOWLISTED_EXECUTABLES`, the
  executable resolution and sanitized environment, `collect_inventory`, the container
  install with `_create`, `_require_isolation` and `_require_owned`),
  `src/oak/runner/execution.py` and `journal.py`, `schemas/runner-plan.schema.json` (the
  closed operation and evidence enums), `schemas/target-profile.schema.json`
  (`execution`), `examples/targets/`, `schemas/system-intent.schema.json` (`hardware`),
  `src/oak/contracts/intent_paths.py`, `src/oak/compiler/interpretation.py` (what the
  brief fills in `spec.hardware`), `src/oak/compiler/candidates.py`
  (`_hardware_constraint`), `src/oak/compiler/research_terms.py` (`classify_hardware`),
  `src/oak/application/design_case.py` (`confirm`, the proposal pattern),
  `src/oak/bootstrap.py`, `src/oak/interfaces/cli/main.py` and `remote.py`,
  `src/oak/interfaces/api/app.py`, the MCP tools, the web case page, `tools/check_boundaries.py`,
  `tests/integration/test_offline_boundary.py`, `docs/security/residual-risk.md`
  (`RR-043`), the original spec repo's `docs/build/security-invariants.md` and
  `docs/threat-model.md` (`TM-09`, `TM-16`) and ADR-0017, `docs/platforms.md`,
  `tests/expected-skips.json`, `.github/workflows/ci.yml`.

## Scope

### In

- B1 as `TIER-3-PROMPT.md` states it, with the owner's addition: the scan reports whether
  Docker and uv are present (Docker's daemon reachable or not) and recommends installing
  what is missing, with the official installation pages, and never installs it.
- B2's three parts as the prompt states them, with the owner's answers: three platforms
  (macOS on Apple silicon, Linux x86_64, Linux aarch64), only ADR-0017's container isolation
  set relaxed, the stand-in plus a hand-rehearsed example, and **no supervision**: the
  install stops the process after its smoke test, and the user starts it.

### Out

- A real harness as a component in the curated catalogue: on the owner's to-do list for
  after 1.0 (kickoff, Q4c), registered in `sprints.md`.
- Keeping a native process alive: no `launchd` agent, no `systemd --user` unit, no
  detached process left running (kickoff, Q4d).
- Installing a prerequisite (Docker, uv) for the user; installing through a package
  manager (pip, apt, Homebrew); Windows; Intel macOS; GPU passthrough to containers;
  a non-local target.
- Batch C. Any version bump, tag, decision record, signature, GitHub Release, PyPI upload
  or registry push.

## Contract and data changes

Planned at kickoff; each milestone records what shipped, as `docs/compatibility.md` will.

- `OAK-V1-039`: a new closed schema for the hardware proposal and the confirmed profile
  (the fields above and nothing else; free text bounded and pattern-limited so that
  identifiers cannot be carried); a new artifact kind for the confirmed profile, registered
  as `CONTRIBUTING.md` requires; new audit events for a proposal recorded and a profile
  confirmed (additive enum values); new REST operations and one MCP tool that accept a
  scan result as a proposal; a new local CLI command `oak scan`; the runner's `inventory`
  evidence gains the scan's fields (additive); the runner's executable allowlist gains the
  five tools. Confirming a profile revises the intent's `spec.hardware` through the
  existing successor rules.
- `OAK-V1-040`: `target-profile.schema.json` gains a `native` acknowledgement and a typed
  `native_components` list (harness kind, artifact source, SHA-256, size, listen port,
  health probe); a consent document and its schema, recorded as a signed approval for its
  own action; ADR-0019. No operation kind is added: `apply`, `verify`, `rollback` and
  `destroy` keep their names and the profile selects the adapter.
- `OAK-V1-041`: none beyond the evidence the native adapter writes under the existing
  evidence kinds.
- `OAK-V1-042`: a shipped stand-in native profile under `examples/targets/` and the example
  profile for a real harness; CI and expected-skips changes.

## Milestones

### M0 — Kickoff (`OAK-V1-039`–`043` claimed)

- Work: branch `tier3-machine` from the image fix (`7e96ed7`); this plan; the rows claimed
  in `STATUS.md`; both repositories' status corrected for PR #42's merge and PR #43's fix;
  the owner's Q4 and Q5 answers recorded; the real catalogue component registered as a
  post-1.0 item.
- Proof: `make validate` here; the original spec repo's validator.
- Rollback: revert the kickoff commit.

### M1 — The scanner (`OAK-V1-039`, part 1)

- Work: pure parsers and the profile builder in `oak.domain` (no I/O), driven by recorded
  fixtures of each tool's real output with the tool's version; the executor in
  `oak.runner` (the allowlist widened by the five names, fixed argument vectors, the
  sanitized environment, a bound on `system_profiler`'s time and every tool's output);
  the prerequisite check; `collect_inventory` replaced by the scanner in the runner's
  `inventory` operation; `oak scan` locally through `bootstrap`, printing the proposal and
  the recommendations; `security-invariants.md` § Runner execution and the register
  record the widening in ADR-0015's terms.
- Proof: fixtures for each tool on each path (Apple silicon, Linux without a GPU, NVIDIA,
  AMD, a tool absent, a tool timing out, output too large, output with a serial number or
  UUID that must not survive); the scan run for real on this Mac and on CI's three jobs;
  mutation checks on each guard.

### M2 — The proposal enters the case (`OAK-V1-039`, part 2)

- Work: the proposal and profile schema and artifact kind; recording a proposal and
  confirming it (local CLI, REST, MCP), the confirmation revising `spec.hardware` with
  provenance that names the scan; the web moment; `compatibility.md`, `interfaces.md`,
  `operations.md`, the manual.
- Proof: a confirmed profile with no accelerator and one with a 24 GiB GPU produce the
  constraint results the rules already define, and research's hardware class follows;
  an unconfirmed proposal changes nothing; a proposal carrying a forbidden field is
  refused by the schema; the reference digests do not move; the browser suite shows the
  moment.

### M3 — The native records (`OAK-V1-040`)

- Work: ADR-0019 in the original spec repo and its mirror here; the `native` mode and its
  typed harness kinds in the target profile; the consent document, its schema and its
  approval action; the security invariants' amendment; `RR-043` updated and new register
  entries; `TM-09` and `TM-16`; the consent text drafted for the owner's sign-off (Q4e).
- Proof: schema and contract tests; a profile carrying a command-like field is refused;
  the original spec repo's validator.

### M4 — The native adapter (`OAK-V1-041`)

- Work: the download module (the third allowed network importer, HTTPS to the
  profile's hosts and `file:` for the stand-in, with its own test), verification, safe
  unpacking, start from the harness kind's template on loopback with the platform's
  resource limits recorded, the smoke test, stop, uninstall, the ownership marker and
  refusal, the consent verified by the runner, journalling before and after each step.
- Proof: unit and integration tests on each refusal (a digest or size mismatch, an
  archive member escaping its directory or naming a link, a foreign process, a consent for
  another installation, a host the profile does not name); mutation checks.

### M5 — Platforms, uninstall and documentation (`OAK-V1-042`)

- Work: the stand-in harness and profile; the native journey in `make check` and on all
  three CI jobs; the canary uninstall test; `platforms.md` rows moved only for what each
  job runs; `tests/expected-skips.json`; `oak observe` for a native installation; the
  example profile for llama.cpp's server and a small model, rehearsed by hand on the
  owner's machine after the owner approves each download; `operations.md`,
  `signed-runner.md`, the README's "What gets installed", the manual and its PDF.
- Proof: CI green on all three jobs over several runs; the rehearsal's digests recorded.

### M6 — Review, gates and PR (`OAK-V1-043`)

- Work: an independent adversarial review of the finished diff, every finding verified
  before it is acted on; the documentation sweep in both repositories; the readiness
  list's "what 1.0 promises"; `make check` with the test database; `make audit`; the
  browser suite on a throwaway project; the manual's PDF; the plan to `completed/`; the
  PR, with CI green over several runs.
- Proof: zero `make: ***` lines; CI green.

## Verification

Each item has a test on its failure path as well as its happy path, mutation-checked where
it is a new guard. Full gates at the end: `make check` with `OAK_TEST_DATABASE_URL` on the
migrated PostgreSQL 17.6 (port 15433), `make audit`, `make web-e2e-isolated`, the
reference case compiled on `origin/main` and on this branch and compared (no difference),
and the PR's CI over several runs.

## Security, privacy and authority review

By milestone, to be filled as each lands:

- **M1, the scanner.** Each new executable is named in the allowlist with a fixed argument
  vector; nothing a document or a plan says reaches an argument; a tool's output is parsed
  as data, bounded in size, and only allowlisted fields survive it. Two findings while
  building it: `system_profiler`'s "mini" level, documented as having no personal
  information, still lists each display's serial number, so the parser reads the GPU's own
  fields and nothing nested; and a GPU is visible only through its vendor's tool, so on
  Linux "no GPU" would be a guess unless both vendors' tools answered, and the scan says
  unknown instead. uv is never run; the scan only looks it up.
- **M2, the proposal.** Only the confirmed profile enters the case, and its schema cannot
  carry an identifier of the machine or its user: the schema is closed, an extra field is
  refused before anything is recorded, and every string is bounded and pattern-limited. A
  client can still send a false scan, as a brief can state false hardware; that is why
  nothing reaches the intent until a user confirms it, and why MCP can propose but not
  confirm. The web never scans: the browser is never the machine a design is for.
- **M3–M5, native installation.** What relaxes is ADR-0017's container isolation set and
  nothing else; what stays is the signed plan bound to bundle and target, the two approvals
  and the consent, typed operations without a shell, verified downloads, and a tested
  uninstall.

## Operational and rollback plan

Each milestone is one commit and can be reverted alone. Operator-visible changes are listed
in the changelog as they land. Nothing stored changes shape: the new documents are new
kinds, and an existing case or profile reads as before.

## Progress

- [x] 2026-11-02 M0 (`OAK-V1-039`–`043` claimed). The owner answered Q4 and Q5 together, as
  recorded under Decisions. Branch `tier3-machine` starts from `fix/image-package-index`
  (`512b12e`, PR #43), because `main`'s CI was red after PR #42. Claimed in `STATUS.md`
  (the phase, the active plan, the next task, five rows); the changelog opens Batch B's
  section; the original spec repo's `STATUS.md`, `IMPLEMENT.md`, `docs/roadmap.md`,
  `sprints.md` (the kickoff answers, and the real catalogue component in the post-1.0
  backlog) and `CHANGELOG.md` updated, its version moved to `0.4.0-draft.22`, its
  validator passing. `make validate` green here.
- [x] 2026-11-02 M1 (`OAK-V1-039`, part 1). `src/oak/domain/hardware.py`: pure parsers for
  `sysctl -n` (four named values), `system_profiler -json -detailLevel mini
  SPDisplaysDataType` (the GPU entries only, never the displays listed under them),
  `lscpu -J` (flat and nested layouts; cores per socket or per cluster), `nvidia-smi`'s CSV
  and `rocm-smi`'s JSON (keys compared without case), a bounded model-name rule, the
  proposal builder with an `unknown` entry per field and reason, the mapping into
  `spec.hardware` (`intent_hardware`: no `vram_gib` for unified memory) and the
  recommendations for a missing Docker or uv. `src/oak/runner/hardware.py`: one fixed
  argument vector per tool, 30 s for `system_profiler` and 10 s otherwise, output at the
  executor's 64 KiB bound, Docker's daemon asked for its version, uv looked up and never
  run. `ALLOWLISTED_EXECUTABLES` gains the five tools. The runner's `inventory` evidence
  gains `hardware` (a `scanner` callable threads from `execute_dispatch`, so a test can
  inject one); `bootstrap.scan_hardware()` and the local `oak scan` (human or JSON, records
  nothing). Fixtures under `tests/fixtures/hardware/` with a README naming each one's
  provenance: this Mac's `sysctl` and `system_profiler` (macOS 26.3.1, the display serial
  replaced), a container's `lscpu` (util-linux 2.41), and constructed nested `lscpu`,
  NVIDIA and AMD files. Tests: 27 unit cases (`tests/unit/test_hardware_scan.py`), the CLI
  (`tests/unit/test_scan_command.py`), the real scan on the host
  (`tests/integration/test_hardware_scan_host.py`, which CI runs on all three jobs), the
  inventory evidence in `tests/integration/test_signed_runner.py`; nine mutation checks,
  each killed (a parser keeping the displays, `rocm-smi` read for its serial, "no GPU" on
  one vendor's answer, NVIDIA's no-device exit read as a failure, the model bound loosened,
  over-long output parsed, an absent tool executed, uv run, unified memory turned into
  `vram_gib`). Documents: `RR-055`, the capability matrix, `platforms.md` (the scan's paths,
  NVIDIA and AMD by fixture only), the changelog, and the original spec repo's
  `docs/build/security-invariants.md` § Runner execution. Every runner suite, `make
  validate`, `format-check`, `lint` and `typecheck` green.
- [x] 2026-11-02 M2 (`OAK-V1-039`, part 2). `schemas/hardware-proposal.schema.json` (`0.1.0`,
  closed; its example, `EXAMPLE_BY_SCHEMA`, the schemas README) and the artifact kind
  `hardware_proposal` (`KIND_SCHEMA`, `JSON_MEDIA_KIND`, the manifest's kind enum); the audit
  events `hardware_proposed` and `hardware_confirmed`. `DesignCaseService.propose_hardware`
  records a scan result as the case's proposal (the case extension
  `oak.community/hardware_proposal_ref`; no intent value changes) and `confirm_hardware`
  confirms the pending one into `spec.hardware`: each value `measured`, one provenance
  record per scalar as the intent's invariant requires, the proposal as evidence, the intent
  extension `oak.community/hardware_scan`, a field's question resolved when it was measured
  and the section's when every hardware value was. The control plane, REST
  (`:propose-hardware`, `:confirm-hardware`, listed as unreleased), MCP
  (`oak_hardware_propose`, the interface contract and its pinned tool list updated), the
  remote client and `oak scan --propose` / `--confirm` locally and with `--server`; the
  web client's `confirmHardware` (guard G2 extended) and the case page's `HardwareMoment`
  (pending proposal with **Confirm hardware**, the confirmed machine, or the command to
  scan). New codes `OAK-HARDWARE-PROPOSAL`, `OAK-HARDWARE-STATE`, `OAK-HARDWARE-EMPTY`, with
  quick-table rows. Tests: `tests/integration/test_hardware_case.py` (nine cases: no intent
  change until confirmed; the hardware question and no other answered; a value the scan
  did not measure keeps the section open; the confirmed profile reaching
  `constraint.hardware`, `unknown` before and `fail` after for the component that needs
  `fixture-gpu`, with research's class `cpu-medium` for no GPU and `accelerator-medium`
  for a 24 GiB one; only the pending proposal, once; no identifier or extra field; refused
  after candidates; an empty scan refused), `tests/integration/test_hardware_interfaces.py`
  (the local CLI, MCP proposing and REST confirming on one control plane, REST's refusal,
  the remote CLI against a live loopback API) and the browser spec
  `web/e2e/hardware.spec.ts` (the moment, its accessibility, the confirmation); eight
  mutation checks, each killed. Documents: `compatibility.md` (schema, REST, CLI, MCP,
  runner evidence), `interfaces.md` (two rows), `operations.md` (the machine a design is
  for), the changelog, and the original spec repo's `docs/build/interface-contract.md`.
  `make validate`, `format-check`, `lint`, `typecheck` and `test` green. Gates on the M2
  tree in a detached worktree: the browser suite 34 passed (the hardware spec among them),
  the two manual captures skipped; `make check` with the throwaway PostgreSQL first failed
  on `openapi/oak.openapi.json` left out of the commit, then passed once it was committed
  (`0be56fe`).
- [x] 2026-11-02 M3 (`OAK-V1-040`). ADR-0019 in the original spec repo
  (`docs/adr/0019-native-installation-with-recorded-consent.md`, indexed) and its mirror
  here (indexed in `docs/adr/README.md`). `target-profile.schema.json` (still `0.2.0`): the
  acknowledgement `native-non-production-user-consented`, the typed `native_components`
  (harness kind `oak_stand_in` or `llama_cpp_server`; artifacts with role, source, SHA-256,
  size and format; a listen port from 1024; a health-probe path), required with that
  acknowledgement, and `allowed_download_hosts`. `schemas/native-consent.schema.json`
  (`0.1.0`), its example and registration, and the consent text
  `catalogue/consent/native-installation.yaml` (six relaxed controls, five retained), in
  `draft` for the owner's sign-off. The original spec repo's
  `docs/build/security-invariants.md` permits downloaded executable selection to this
  adapter alone, under named controls; its threat model's `TM-09` and `TM-16` gain the
  native path. `RR-056` and `RR-057` join the register, `RR-043` names its scope, and the
  register's count (57) follows in both repositories' `STATUS.md`. `compatibility.md`, the
  changelog. `make validate` and `make test` green; the existing profiles still validate.
- [x] 2026-11-02 M4 (`OAK-V1-041`). The domain contract in
  `src/oak/domain/runner_adapters.py`: `adapter.local-native` `0.1.0`, its closed parameter
  schema and digests in the three registries, the harness-shape rule shared by the compiler
  and the runner, the consent's reference, problems and binding. `src/oak/runner/native_network.py`
  (HTTPS to acknowledged hosts, redirects checked, no proxy, size bounded as it arrives; the
  loopback probe) and `src/oak/runner/stand_in/http_server.py` join the offline boundary's
  allowed importers. `src/oak/runner/native.py`: the installation directory and its marker,
  fetch or copy, digest check, safe unpacking, the start from each harness kind's template
  under three ceilings, the probe, the stop, removal by marker. The compiler emits one
  native `apply`, `rollback` and `destroy` naming the consent text, with the profile's hosts
  as `apply`'s network destinations, and `preflight.installation` and `preflight.network`
  judge a native profile. The consent text is read by `LocalConsentText`
  (`src/oak/adapters/catalogue/consent.py`) through `bootstrap`. The release service
  records `native_consent` after `architecture` and before `apply`, only for a native plan,
  only with the digest of the text installed now and named by the plan, and stores that
  text as a `native_consent` artifact with the approval; `apply` needs it, and dispatch
  attaches and checks it. The runner checks the native installation against its own profile
  and the consent's binding; the executor picks the adapter by id and refuses a native
  operation on a runner without the native adapter before touching anything; the runner
  main builds it under `native/` in its home. `oak approve native_consent` shows the text
  and its digest without `--consent`. `oak architecture`, `oak gitops` and the report's
  approvals table know the third approval. `examples/targets/local-native-stand-in.yaml`.
  Tests: 31 adapter and network unit cases (among them a real child measuring its own
  limits), the consent text's pin, the native architecture view,
  `tests/integration/test_native_consent.py` (13: order, digest, a changed text, other
  controls, revocation, three attachments, the runner's refusals of a missing consent, a
  consent to something else, parameters its profile does not acknowledge, a host it does not
  list), `tests/integration/test_native_install.py` (4, through the real runner: installed,
  checked and stopped with nothing listening; destroy with canaries beside it; a failed check
  rolled back; a foreign directory kept), and the e2e journey through the installed `oak`
  and `oak-runner` with no Docker, which `make check` runs on all three CI jobs; thirteen
  mutation checks, each killed. Documents: `signed-runner.md` (the verification order, the
  journey, what the native adapter does), `compatibility.md`, the error reference and its
  quick table, the changelog. Unit, contract and integration suites green (1,468 and 623
  passed), lint, format, types and boundaries green.
- [x] 2026-11-02 M4 gate. `make check` on `9947591` in the detached gate worktree, with the
  throwaway PostgreSQL: no failing target; unit and contract 1,468 passed, integration 623,
  end to end 47 (the native journey among them).
- [ ] 2026-11-02 M5 (`OAK-V1-042`), all but the rehearsal. The native journey runs in
  `make check` through the installed entrypoints with no Docker, so all three CI jobs prove
  it; nothing joins `tests/expected-skips.json`. After an install the runner prints the
  folder and that nothing is running, and `START.txt` there gives each component's command.
  The ADR's resource ceilings are applied in the child and recorded (M4's decision).
  `oak observe` reads a native installation (`observation-record.schema.json`:
  `native-user-consented`, rows named by `installation_id`, exactly one of the two names).
  `GET /v1/native-consent` serves the text and its reference (`503 OAK-NATIVE-CONSENT` on a
  server without it); the bundle page shows a consent light, the text in a disclosure, a
  notice if the text changed after the compile, and the steps with the plan's digest
  (`web/e2e/native.spec.ts`). Archive links inside a release are copied, never created; a
  refused redirect names a plain host. `examples/targets/local-native-llama-cpp.yaml`
  (build `b11721` of 2026-10-18, at least two weeks old as pins here are; Qwen2.5-0.5B-Instruct
  Q4_K_M at commit `9217f5d`), its sizes and digests read from GitHub's and Hugging Face's
  metadata and its redirect hosts from header-only requests, with no file downloaded; a test
  compiles it. The real CLI journey was run on this Mac for the manual. Documents:
  `operations.md`, `platforms.md`, the README, `interfaces.md`, `compatibility.md`, the
  manual (a scan step in chapter 3, the native install in chapter 6, the uninstall and the
  colophon) and its PDF. Nine mutation checks, each killed after two tests were tightened
  (a completion claiming a complete check of fewer nodes; a link that climbs out to a file
  that exists). Unit and contract 1,485 passed; `make validate` green. Open: the rehearsal,
  which waits for the owner's approval of each download.
- [x] 2026-11-02 M5 gates on `f7b200c`, in the detached gate worktree. `make check` with the
  throwaway PostgreSQL: no failing target; unit and contract 1,486 passed, integration 627,
  end to end 47. `make web-e2e-isolated` on a throwaway Compose project: 35 passed (the
  native spec among them), the two manual captures skipped as expected; the project, its
  volumes and its images removed afterwards.
- [x] 2026-11-03 M6 (`OAK-V1-043`), the closing review. Two independent reviewers read the
  finished diff, one on the native installation's security and one on correctness
  elsewhere; their fourteen findings all held and are fixed (see Self-review), each code fix
  with a test, and twenty-one mutation checks of those fixes each killed. The consent text
  changed again before the owner's sign-off (a program built to leave its process group can
  outlive the stop), and its pin with it. Unit and contract 1,504 passed; integration and
  end to end 683 passed, 4 skipped, with the throwaway PostgreSQL.
- [x] 2026-11-03 M6 gates. `make check` on `27f836c` failed once, on the macOS race recorded
  under Discoveries; fixed in `93df6e3`. `make check` on `93df6e3` in the detached gate
  worktree, with the throwaway PostgreSQL: no failing target; unit and contract 1,504
  passed, integration 636, end to end 47.

## Decisions

- 2026-11-02 Kickoff. **The owner's answers**, asked together with options and a
  recommendation each, as the prompt requires:
  - **Q5, hardware scanning:** "Both, five tools (Recommended) - and also recommend
    installing prerequisites such as Docker and uv if not installed". The scan runs from one
    module in the runner's `inventory` operation and a local command; the tools are
    `sysctl` and `system_profiler` on macOS and `lscpu`, `nvidia-smi` and `rocm-smi` on
    Linux; and the scan recommends Docker and uv when they are missing, without installing
    them.
  - **Q4(a) and (b), platforms and what relaxes:** "Three platforms (Recommended)": macOS on
    Apple silicon, Linux x86_64 and Linux aarch64. The question stated that only ADR-0017's
    container isolation set relaxes and that everything protecting the user from a poisoned
    bundle stays; the owner chose the recommendation as stated.
  - **Q4(c), what the native profile installs:** "Stand-in plus example, but real catalogue
    component should go on the to-do list after v1 launch". The real component is
    registered in `sprints.md` as a post-1.0 item.
  - **Q4(d), keeping the process alive:** "After the install process is complete, the
    service should shut down until launched again by the user. The point is to get a
    suitable AI system installed for the user, and no more". So the install starts the
    process only to smoke-test it, then stops it; no unit file is written and nothing is
    left running; the runner tells the user how to start it.
  - **Q4(e), the consent text:** drafted in M3 and brought to the owner for sign-off.
- 2026-11-02 M2. **A proposal enters a case between interpretation and candidate
  generation, and only the latest one can be confirmed, once.** Candidates are designed
  for the hardware they were generated against, so a scan after them would describe a
  machine the designs never saw (`OAK-HARDWARE-STATE`); a newer scan replaces the pending
  one. The runner's `inventory` carries the same proposal in its evidence, but a dispatch
  comes after compilation, so its scan can serve a later case (REST takes
  `scanned_by: runner_inventory`), not the one dispatched.
- 2026-11-02 M2. **Confirmed values are `measured`, an existing provenance source**, one
  record per scalar as every intent value has; no enum changes. The section question
  (`/spec/hardware`, which interpretation asks) is resolved only when every hardware value
  rests on the proposal, because a value the brief stated and the scan did not measure
  still needs the user's word.
- 2026-11-02 M2. **`recorded_at`, not `scanned_at`.** The server knows when a proposal
  entered the case, not when the client's scan ran, so the document says only that.
- 2026-11-02 M3. **The consent is a signed approval for its own action, `native_consent`.**
  ADR-0017's `architecture` approval is the precedent: an extension binding what it
  approves, checked by the runner on its own. The consent binds the consent document's
  digest, the relaxed controls by id and the installation digest; the runner compares the
  ids with the controls its native adapter relaxes, so a consent text that names fewer
  controls than the code relaxes cannot authorize an install. The approval's action enum
  gains the value with the code that verifies it, in M4.
- 2026-11-02 M3. **The relaxed controls are ADR-0017's isolation set, one id each**:
  `network_isolation`, `read_only_root`, `no_capabilities`, `unprivileged_user`,
  `resource_ceilings` and `loopback_port` (a container published no port; a native process
  listens on 127.0.0.1 while it runs). The text in `catalogue/consent/native-installation.yaml`
  is a draft: the owner signs it off (Q4e) and its `status` becomes `approved`.
- 2026-11-02 M3. **The stand-in installs from inside OAK.** Its artifact source is
  `oak-stand-in:<name>`, a file shipped in OAK's own package and verified by digest like any
  download, run by the runner's own interpreter: so `make check` stays offline, CI's three
  jobs prove the native path without Docker, and macOS's signing rules for downloaded
  binaries do not decide whether CI passes.
- 2026-11-02 M4. **Three ceilings, and the rest unlimited by design.** ADR-0019 said the
  platform's limits apply "as far as it offers them". The adapter sets, in the child before
  it executes, no core files, at most 4,096 open files and no written file over 2 GiB, each
  only ever lower than the runner's own; it does not limit memory (macOS does not enforce an
  address-space limit, and a model server maps its model), CPU time (a server loading on
  many threads would be killed) or the process count (it counts every process the user
  runs). The evidence records both lists, and the ADR (both copies), the consent text and
  `signed-runner.md` say exactly this; the draft consent text had implied more.
- 2026-11-02 M4. **The consent is local, like every approval.** Approvals are recorded only
  by the local CLI, so `native_consent` adds no REST route or MCP tool; `oak architecture`,
  which REST also serves, shows the consent's state beside the other two.
- 2026-11-02 M4. **The consent text's pin moves with the draft.** Its digest is in every
  native plan and consent, so `tests/unit/test_native_consent_text.py` pins it per version:
  after the owner's sign-off, an edit means a new version and a new pin.
- 2026-11-02 M5. **The web reads the consent text through a read-only endpoint.**
  ADR-0019 says the web shows the text before the install approval; approvals stay on the
  local command line, so the web shows the text, the consent's state and the steps with the
  plan's digest, through `GET /v1/native-consent`, and records nothing.
- 2026-11-02 M5. **A link inside a release archive is unpacked as a copy.** llama.cpp now
  ships `.tar.gz` builds, and tar keeps the links a CMake build makes between a library's
  versioned names; refusing every link would refuse the release. Copying the file a link
  names inside the archive keeps the rule that nothing unpacked is a link, so no later
  member can be written through one; a link that leaves the archive, names nothing in it,
  or loops is still refused.
- 2026-11-02 M5. **How to start an installed component is a file in the installation, not a
  record.** The owner's Q4d answer leaves nothing running, so the user needs the commands;
  they name paths in the user's home, so they go in `START.txt` beside the marker, and the
  evidence says only that the file exists and nothing runs.
- 2026-11-02 M5. **The llama.cpp example pins a build at least two weeks old**, as the
  repository pins its actions; llama.cpp's binaries are now prerelease builds, and its
  `v0.8.0` release carries none.
- 2026-11-02 M2. **The manual's scan section lands in M5**, with the native path, so the
  manual's PDF is rebuilt once.
- 2026-11-02 Kickoff. **The branch starts from the image fix, not from `main`.** `main`'s
  CI was red after PR #42's merge for a reason `OAK-V1-038` fixes; starting there keeps this
  batch's CI about this batch.

## Discoveries and follow-ups

- 2026-11-02 M1. `system_profiler -detailLevel mini` lists each display's serial number
  under the GPU that drives it (`_spdisplays_display-serial-number`); the fixture carries a
  synthetic one and a test proves it never reaches a proposal.
- 2026-11-02 M1. `lscpu -J` from util-linux 2.41 in a Debian container is flat, prints `-`
  for an unknown model name and for sockets on Arm, and counts cores per cluster; the
  nested layout of other releases is read by walking every child.
- 2026-11-02 M1. Adding `RR-055` moves the register past the 54 entries both repositories
  cite. `tests/contract/test_configuration_reference.py` pins the "stable-id entries" count
  in `STATUS.md` to the register, so each new entry moves the live citations at once
  (`STATUS.md` here and the original spec repo's); the readiness list in the completed
  readiness plan follows at M6. The kickoff commit also cited ADR-0019 in `STATUS.md`
  before the record existed, which `tests/contract/test_adr_references.py` refuses; the
  row now says "a new decision record" until M3 writes it. Both were caught by CI, not
  locally: run `make test` before every push, not only the milestone's own tests.
- 2026-11-02 M4. `oak architecture` read every `apply` as a container install, so a native
  plan would have been described as "compiled before the topology installer"; it now has a
  native branch, keyed on the plan's adapter. The CLI's JSON output sorts keys, so a test of
  the approvals' order reads a set. The integration suite's fixture plan carries no adapter
  block, so the view uses `plan_apply_adapter`, which tolerates one missing.
- 2026-11-02 M4, for M5. The web's bundle page shows the architecture and apply approvals;
  for a native plan it should show the consent's state and the consent text beside them, as
  ADR-0019 says. `oak observe` on a native installation is M5's. Both done in M5.
- 2026-11-02 M5. Hugging Face redirects a model download to a regional CDN host
  (`us.aws.cdn.hf.co` from here), so a profile written in one region can be refused in
  another; the refusal now names the host. GitHub redirects release assets to
  `release-assets.githubusercontent.com`. The adapter's `START.txt` and the runner's message
  name the stand-in's file `download`, which the runner's interpreter runs as a script.
- 2026-11-03 M6. macOS answers `EPERM`, not `ESRCH`, to a signal for a process group
  whose remaining members are all zombies waiting for their new parent (launchd) to reap
  them. The gate caught it: the first version of the hardened stop treated that `EPERM` as a
  failure (`OAK-NATIVE-IO`) or as "still running" (`OAK-NATIVE-STOP`), about four times in
  six on this Mac. The stop now suppresses `EPERM` when signalling and keeps waiting, up to
  two seconds, for the group to be gone; twenty repetitions of the race then ended as they
  should.
- 2026-11-02 M5. The manual's PDF could not be inspected here (no PDF renderer on this Mac,
  and the browser pane shows local files only as a static snapshot); its HTML source, from
  which Chromium prints it, follows the chapter's existing patterns.

## Self-review

The closing review (M6) ran two independent reviewers over the finished diff, as the token
economy allows for finished code: one on the native installation's security, one on
correctness everywhere else. Each finding was checked against the code before it was fixed;
all fourteen held. Each code fix has a test that fails without it (twenty-one mutation
checks, each killed).

| # | Finding | Where | Severity | Fix and proof |
|---|---|---|---|---|
| S1 | A component that answered once and died, or another listener on its port, passed its check | `runner/native.py` `_wait_ready` | Medium | Only the component, still running after answering twice, passes; the port must be free first (`OAK-NATIVE-START`); two tests |
| S2 | The stop signalled the group only while its first process lived, never killed a child left behind or one ignoring `SIGTERM`, and recorded "stopped" unchecked; `SIGTERM` to the runner mid-check skipped the stop | `runner/native.py` `_stop` | Medium | `SIGTERM`, then `SIGKILL` to the whole group every time; stopped only when the group is gone (`OAK-NATIVE-STOP`); `SIGTERM`/`SIGHUP` handlers during the check; three tests, one in a child process |
| S3 | A real model could not install inside a five-minute lease, and downloads ignored the lease | `release.py`, `compiler/planning.py`, `native_network.fetch` | Medium | A native plan admits, and its `apply` dispatch gets, an hour; a download stops when the lease ends; a file two components share downloads once; four tests |
| S4 | A re-apply ran an unpacked tree it never re-verified | `runner/native.py` `_obtain` | Medium/low | Every `apply` unpacks afresh from the re-verified bytes; a test |
| S5 | Non-OAK errors escaped without compensation; a failed marker write or removal could leave a directory without its marker; a host the IDNA codec refuses crashed the fetch | `runner/native.py`, `native_network.py`, the target profile schema | Low | `OAK-NATIVE-IO` with compensation; created under a temporary name and renamed with its marker; removed through a rename; hosts are plain DNS names; four tests |
| C1 | The same scan proposed again after the case moved on replayed an old version, so `oak scan --confirm` failed for ever | `application/design_case.py`, CLI remote path | Medium | Derived keys cover the case version, locally and remotely; a test |
| C2 | Confirming an Apple silicon scan switched off the weight-floor check and lowered the research hardware class; a GPU with unknown memory kept the brief's figure | `domain/hardware.intent_hardware`, `confirm_hardware` | Medium | Unified memory gives `vram_gib` the system memory; re-measured accelerators replace GPU memory and drivers, an unknown figure is cleared; two tests |
| C3 | The case-scoped error mapping had moved from `architecture` to the consent read | `application/control_plane.py` | Low | Restored; a structural test pins every case-scoped method |
| C4 | Memory reported unknown beside the runtime's figure on macOS | `domain/hardware.build_proposal` | Low | The memory unknown is dropped when a figure exists; a test |
| C5 | An Arm machine with two kinds of core counted one cluster | `domain/hardware.parse_lscpu` | Low | Cores summed over every model group, names joined; a constructed fixture and a test |
| C6 | A case id of 125 characters or more made every proposal id too long | `application/design_case._hardware_proposal_id` | Low | The case part is shortened to fit 160; a test |
| C7 | A native plan's report said "two approvals" until a consent existed | `application/report/composer.py` | Low | Read from the bundle's installation preflight, already a report input; a composer test |
| C8 | Docs claimed no proposal field can carry an identifier; a client's own proposal can | CHANGELOG, `operations.md`, the schema's description | Low (docs) | Reworded to what the code guarantees |
| C9 | `RR-055`'s environment, the manual's consent output and scan note, and `compatibility.md`'s REST list were incomplete | docs | Low (docs) | Corrected |

The consent text changed twice in the batch, both before the owner's sign-off: the
resource ceilings (M4) and that a program built to leave its process group can outlive the
stop (S2). Its pin moved with it; `RR-056` and ADR-0019 say the same.
