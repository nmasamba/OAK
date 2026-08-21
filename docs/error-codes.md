<!-- SPDX-License-Identifier: Apache-2.0 -->

# Error-code reference

Every `OAK-*` code the source can raise, what it means, and which surfaces it reaches.

**This file is generated.** Run `python scripts/generate_error_reference.py` after
changing a code; `make validate` fails if it is stale. Messages are read out of the raise
sites, so a code whose message is built at runtime shows as *dynamic* rather than being
given an invented description.

## How codes reach you

| Surface | Where the code appears |
|---|---|
| CLI | `CODE: message` on stderr. Exit `0` success, `2` refusal or invalid input, `4` version or idempotency conflict |
| REST | The `code` field of the problem-details body. For a not-found code the `detail` is replaced with an opaque string, so **the code is your only signal** |
| MCP | The `code` field of the tool result's `structuredContent`, with `isError: true`. Not-found codes are opaqued as on REST |
| Runner | `CODE: message` on stderr, exit `70` |

Codes are a public surface governed by [compatibility.md](compatibility.md): new codes may
be added freely, but an existing code may not change meaning or disappear while a
documented flow uses it.

## The ones you are most likely to meet

| Code | What happened | What to do |
|---|---|---|
| `OAK-EXPECTED-VERSION` | The case advanced since you read it | Re-read the case and retry with the current version. A normal concurrency refusal, not a fault |
| `OAK-PRECONDITION-INVALID` | Your `If-Match` header is unusable — weak entity tag, or empty | Send a strong ETag. **Retrying will not help**; this is deliberately not a 409 for that reason |
| `OAK-IDEMPOTENCY-CONFLICT` | An idempotency key was reused with different input | Use a new key, or resend the original input |
| `OAK-IDEMPOTENCY-KEY` | The key is shorter than 16 characters | Lengthen it. Longer keys are fine |
| `OAK-WORKSPACE-NOT-FOUND` | There is no workspace at this location | Check the working directory, or run `oak init` |
| `OAK-ARTIFACT-NOT-FOUND` | The workspace is present; this artifact reference did not match | Check the id, version and digest triple. The workspace is fine |
| `OAK-WORKSPACE-CORRUPT` | The manifest or an indexed object failed verification | Run `python scripts/verify_deployment.py --workspace <dir>`. See [operations.md](operations.md#restore) |
| `OAK-REMOTE-UNSUPPORTED` | A local-only command was run with `--server` | Signing, approval, dispatch, keys, extensions and policy are local-only by design |
| `OAK-REMOTE-UNAVAILABLE` | The control plane could not be reached | Check the URL and that `oak-api` is running |
| `OAK-TENANT-MISMATCH` | A different tenant was requested | Reported as not-found on purpose, so it leaks no existence information |
| `OAK-ACTOR-DENIED` | A different actor was claimed | The local actor is bound by `OAK_LOCAL_ACTOR` |

## Full index

212 codes across 13 families.

### Workspace, artifacts and import/export (22)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-ARTIFACT-COLLISION` | artifact digest collision detected | `src/oak/adapters/persistence/file_workspace.py:482` |
| `OAK-ARTIFACT-DIGEST` | artifact digest is invalid | `src/oak/adapters/persistence/file_workspace.py:717` |
| `OAK-ARTIFACT-IDENTITY` | artifact metadata does not match canonical content | `src/oak/adapters/persistence/file_workspace.py:402` |
| `OAK-ARTIFACT-IMMUTABLE` | an immutable artifact version already has different content | `src/oak/adapters/persistence/file_workspace.py:419` |
| `OAK-ARTIFACT-INVALID` | canonical artifact is not JSON; canonical artifact must be an object (some dynamic) | `src/oak/adapters/persistence/file_workspace.py:383` |
| `OAK-ARTIFACT-KIND` | artifact kind is not supported | `src/oak/adapters/persistence/file_workspace.py:378` |
| `OAK-ARTIFACT-NONCANONICAL` | canonical artifact bytes are not normalized | `src/oak/adapters/persistence/file_workspace.py:406` |
| `OAK-ARTIFACT-NOT-FOUND` | artifact was not found | `src/oak/adapters/persistence/postgresql.py:230` |
| `OAK-ARTIFACT-SIZE` | artifact exceeds the local size limit | `src/oak/adapters/persistence/file_workspace.py:478` |
| `OAK-EXPORT-EXISTS` | export destination already exists | `src/oak/adapters/persistence/file_workspace.py:219` |
| `OAK-EXPORT-OUTPUT` | --output is required; output directory already exists | `src/oak/interfaces/cli/main.py:744` |
| `OAK-EXPORT-SIZE` | canonical export exceeds the size limit | `src/oak/adapters/persistence/postgresql.py:332` |
| `OAK-IMPORT-DIGEST` | an imported object digest does not match; import object digest does not match; import object digest is invalid | `src/oak/adapters/persistence/file_workspace.py:289` |
| `OAK-IMPORT-INVALID` | an imported object size does not match; an indexed import object is missing; canonical export document is invalid; and 12 more | `src/oak/adapters/persistence/file_workspace.py:261` |
| `OAK-IMPORT-SCOPE` | import case and workspace do not match; import tenant does not match command authority; import workspace or tenant does not match destination | `src/oak/adapters/persistence/postgresql.py:352` |
| `OAK-IMPORT-SIZE` | an import object exceeds the size limit; canonical import exceeds the size limit; import manifest exceeds the size limit | `src/oak/adapters/persistence/postgresql.py:367` |
| `OAK-IMPORT-UNSAFE-PATH` | import object store is unsafe; import source must be a regular directory | `src/oak/adapters/persistence/file_workspace.py:250` |
| `OAK-WORKSPACE-CORRUPT` | artifact reference is not canonical JSON; artifact reference is not indexed correctly; canonical artifact is not an object; and 11 more | `src/oak/adapters/persistence/file_workspace.py:141` |
| `OAK-WORKSPACE-EXISTS` | import destination is already initialized; workspace is already initialized | `src/oak/adapters/persistence/file_workspace.py:106` |
| `OAK-WORKSPACE-MUTATION` | mutation is missing its audit event; mutation is missing its case artifact; outbox event identity changed; and 2 more | `src/oak/adapters/persistence/file_workspace.py:334` |
| `OAK-WORKSPACE-NOT-FOUND` | no OAK workspace found; workspace is not initialized; workspace manifest is missing; and 1 more | `src/oak/adapters/persistence/file_workspace.py:135` |
| `OAK-WORKSPACE-UNSAFE-PATH` | workspace root cannot be a symlink | `src/oak/adapters/persistence/file_workspace.py:103` |

### Design case: intake, interpretation, confirmation (33)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-CASE-CONFLICT` | workspace contains a different design case | `src/oak/application/control_plane.py:106` |
| `OAK-CASE-NOT-FOUND` | design case was not found; requested design case is not current; workspace has no design case | `src/oak/application/candidate_planning.py:644` |
| `OAK-CASE-TRANSITION-DENIED` | *dynamic message* | `src/oak/domain/design_case.py:95` |
| `OAK-CASE-VERSION` | case version is not a supported semantic version | `src/oak/domain/design_case.py:46` |
| `OAK-CONFIRM-ANSWERS` | --answers is required | `src/oak/interfaces/cli/main.py:295` |
| `OAK-CONFIRM-CASE` | answers target a different design case | `src/oak/application/design_case.py:353` |
| `OAK-CONFIRM-DECISION` | confirmation decision is unsupported | `src/oak/application/design_case.py:630` |
| `OAK-CONFIRM-DUPLICATE` | each question may be answered once | `src/oak/application/design_case.py:365` |
| `OAK-CONFIRM-MALFORMED` | answers are malformed; confirmation input is not canonical JSON data | `src/oak/application/design_case.py:335` |
| `OAK-CONFIRM-PATH` | confirmation path has no current value; confirmation path is outside intent spec; rejected claim path does not exist | `src/oak/application/design_case.py:635` |
| `OAK-CONFIRM-PROVENANCE` | claim has no provenance to confirm | `src/oak/application/design_case.py:700` |
| `OAK-CONFIRM-QUESTION` | answer references no open question | `src/oak/application/design_case.py:372` |
| `OAK-CONFIRM-STATE` | claims can be confirmed only while the case needs confirmation | `src/oak/application/design_case.py:355` |
| `OAK-CONFIRM-VALUE-MISMATCH` | confirmed value does not match the current canonical claim | `src/oak/application/design_case.py:613` |
| `OAK-INTAKE-ALIAS` | YAML aliases and anchors are not accepted | `src/oak/adapters/intake/local_file.py:117` |
| `OAK-INTAKE-COMPLEXITY` | structured brief is too complex | `src/oak/adapters/intake/local_file.py:164` |
| `OAK-INTAKE-CYCLE` | structured brief contains a cycle | `src/oak/adapters/intake/local_file.py:168` |
| `OAK-INTAKE-EMPTY` | text brief has no usable content | `src/oak/compiler/interpretation.py:52` |
| `OAK-INTAKE-ENCODING` | brief must be valid UTF-8 | `src/oak/adapters/intake/local_file.py:61` |
| `OAK-INTAKE-IDENTITY` | structured brief requires string id, brief_version, and title | `src/oak/adapters/intake/local_file.py:135` |
| `OAK-INTAKE-KEY-TYPE` | structured brief keys must be strings | `src/oak/adapters/intake/local_file.py:172` |
| `OAK-INTAKE-MALFORMED` | structured brief is malformed | `src/oak/adapters/intake/local_file.py:124` |
| `OAK-INTAKE-NUMBER` | structured brief numbers must be finite | `src/oak/adapters/intake/local_file.py:188` |
| `OAK-INTAKE-READ` | brief could not be read | `src/oak/adapters/intake/local_file.py:89` |
| `OAK-INTAKE-SIZE` | *dynamic message* | `src/oak/adapters/intake/local_file.py:101` |
| `OAK-INTAKE-TYPE` | brief file type is not supported | `src/oak/adapters/intake/local_file.py:52` |
| `OAK-INTAKE-UNICODE-CONTROL` | brief contains a prohibited control or formatting character | `src/oak/adapters/intake/local_file.py:150` |
| `OAK-INTAKE-UNICODE-PATH` | brief filename must use NFC Unicode | `src/oak/adapters/intake/local_file.py:49` |
| `OAK-INTAKE-UNSAFE-PATH` | brief filename must not contain a path; brief must be a regular non-symlink file | `src/oak/adapters/intake/local_file.py:36` |
| `OAK-INTAKE-VALUE-TYPE` | structured brief contains a non-JSON value | `src/oak/adapters/intake/local_file.py:190` |
| `OAK-INTENT-NOT-FOUND` | design case has no intent artifact; interpreted design has no intent artifact | `src/oak/application/design_case.py:504` |
| `OAK-INTENT-PROVENANCE` | every populated scalar intent value must have exactly one provenance record | `src/oak/compiler/interpretation.py:606` |
| `OAK-SOURCE-MISSING` | draft case has no source record; intent has no source record | `src/oak/application/design_case.py:225` |

### Candidates, evaluation, selection and planning (21)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-ASSURE-CANDIDATE` | assurance candidate is not selected | `src/oak/application/candidate_planning.py:359` |
| `OAK-ASSURE-OUTPUT` | --output is required | `src/oak/interfaces/cli/main.py:573` |
| `OAK-ASSURE-STATE` | assurance requires candidate_selected state | `src/oak/application/candidate_planning.py:356` |
| `OAK-CANDIDATE-NOT-FOUND` | candidate is not part of this design case | `src/oak/application/candidate_planning.py:611` |
| `OAK-CANDIDATES-STATE` | candidates require a case that is ready for candidates | `src/oak/application/candidate_planning.py:147` |
| `OAK-EVALUATE-STATE` | candidate evaluation requires candidates_ready state | `src/oak/application/candidate_planning.py:222` |
| `OAK-EVALUATION-EXISTS` | candidate already has an immutable evaluation; retry with the original key | `src/oak/application/candidate_planning.py:227` |
| `OAK-EVALUATION-NOT-FOUND` | candidate has no evaluation result | `src/oak/application/candidate_planning.py:592` |
| `OAK-PLAN-CANDIDATE` | plan candidate is not selected | `src/oak/application/candidate_planning.py:429` |
| `OAK-PLAN-INPUT` | --target and --output are required; target profile is malformed | `src/oak/interfaces/cli/main.py:644` |
| `OAK-PLAN-STATE` | plan compilation requires assurance_planned state | `src/oak/application/candidate_planning.py:426` |
| `OAK-SELECT-EVALUATION` | candidate evaluation must pass before selection | `src/oak/application/candidate_planning.py:296` |
| `OAK-SELECT-INFEASIBLE` | an infeasible candidate cannot be selected | `src/oak/application/candidate_planning.py:292` |
| `OAK-SELECT-RATIONALE` | --rationale-file is required; selection rationale is required and bounded | `src/oak/application/candidate_planning.py:268` |
| `OAK-SELECT-STATE` | selection requires candidates_ready state | `src/oak/application/candidate_planning.py:288` |
| `OAK-TARGET-CAPABILITY` | target does not allow every required read-only planning operation | `src/oak/application/candidate_planning.py:416` |
| `OAK-TARGET-EXECUTION` | mutation-capable target profile is missing its execution block | `src/oak/compiler/planning.py:446` |
| `OAK-TARGET-INCOMPATIBLE` | *dynamic message* | `src/oak/compiler/planning.py:67` |
| `OAK-TARGET-INVALID` | target profile failed bounded validation | `src/oak/adapters/targets/local_profile.py:51` |
| `OAK-TARGET-PATH` | target profile must be a regular file | `src/oak/adapters/targets/local_profile.py:24` |
| `OAK-TARGET-TENANT` | target tenant does not match the command authority | `src/oak/application/candidate_planning.py:410` |

### Catalogue (8)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-CATALOGUE-COUNT` | catalogue contains too many documents | `src/oak/adapters/catalogue/local_catalogue.py:37` |
| `OAK-CATALOGUE-DUPLICATE` | architecture pattern ID is duplicated; architecture pattern variant is duplicated; catalogue identities must be unique; and 1 more | `src/oak/adapters/catalogue/local_catalogue.py:53` |
| `OAK-CATALOGUE-EMPTY` | catalogue requires manifests and patterns | `src/oak/adapters/catalogue/local_catalogue.py:28` |
| `OAK-CATALOGUE-INELIGIBLE` | catalogue has no eligible manifests | `src/oak/compiler/catalogue.py:94` |
| `OAK-CATALOGUE-INVALID` | catalogue document failed bounded validation | `src/oak/adapters/catalogue/local_catalogue.py:86` |
| `OAK-CATALOGUE-PATH` | catalogue directory is unsafe or missing; catalogue documents must be regular files | `src/oak/adapters/catalogue/local_catalogue.py:34` |
| `OAK-CATALOGUE-PATTERN` | architecture edge references an unknown role; architecture pattern references a missing component manifest; architecture pattern roles are duplicated; and 2 more | `src/oak/compiler/catalogue.py:160` |
| `OAK-CATALOGUE-TIME` | catalogue timestamp is invalid | `src/oak/compiler/catalogue.py:198` |

### Policy (13)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-POLICY-ACTION` | policy action must be evaluate or packs | `src/oak/interfaces/cli/main.py:1169` |
| `OAK-POLICY-ENGINE-DIVERGED` | the external policy engine disagreed with the built-in reference engine; refusing to publish a decision | `src/oak/adapters/policies/opa.py:156` |
| `OAK-POLICY-ENGINE-FAILED` | opa evaluation failed; opa evaluation omitted a rule verdict; opa evaluation returned an unreadable result; and 2 more | `src/oak/adapters/policies/opa.py:188` |
| `OAK-POLICY-ENGINE-UNAVAILABLE` | the opa binary is not installed; the built-in engine remains available | `src/oak/adapters/policies/opa.py:95` |
| `OAK-POLICY-ENGINE-UNKNOWN` | policy engine is not registered | `src/oak/application/policy.py:79` |
| `OAK-POLICY-PACK-COUNT` | too many policy pack files | `src/oak/adapters/policies/pack_store.py:49` |
| `OAK-POLICY-PACK-DUPLICATE` | policy pack ID is duplicated | `src/oak/adapters/policies/pack_store.py:53` |
| `OAK-POLICY-PACK-INVALID` | policy pack failed bounded validation; policy pack must not use YAML aliases; policy pack size is out of bounds | `src/oak/adapters/policies/pack_store.py:76` |
| `OAK-POLICY-PACK-NOT-FOUND` | policy pack is not available | `src/oak/adapters/policies/pack_store.py:61` |
| `OAK-POLICY-PACK-PATH` | policy pack must be a regular file; policy pack path must not be a symlink | `src/oak/adapters/policies/pack_store.py:66` |
| `OAK-POLICY-PACK-REQUIRED` | --pack is required to evaluate | `src/oak/interfaces/cli/main.py:1171` |
| `OAK-POLICY-SUBJECT` | policy evaluation requires an interpreted intent | `src/oak/application/policy.py:184` |
| `OAK-POLICY-TIME` | policy timestamp is invalid; policy timestamp must carry a UTC offset | `src/oak/domain/policy_rules.py:258` |

### Extensions (16)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-EXTENSION-ACTION` | extensions action is not recognized | `src/oak/interfaces/cli/main.py:1332` |
| `OAK-EXTENSION-AMBIGUOUS` | multiple versions are installed; pass --version | `src/oak/adapters/extensions/store.py:101` |
| `OAK-EXTENSION-CORRUPT` | activation record is not an object; extension directory name is invalid; extension manifest identity does not match its directory | `src/oak/adapters/extensions/store.py:199` |
| `OAK-EXTENSION-EXISTS` | a quarantined copy already exists; extension version is already active; extension version is already installed | `src/oak/adapters/extensions/store.py:144` |
| `OAK-EXTENSION-IDENTITY` | extension identity is unsafe | `src/oak/adapters/extensions/store.py:320` |
| `OAK-EXTENSION-MANIFEST` | extension manifest failed bounded parsing; extension manifest must not use YAML aliases | `src/oak/adapters/extensions/store.py:255` |
| `OAK-EXTENSION-NOT-FOUND` | extension file does not exist; extension is not installed | `src/oak/adapters/extensions/store.py:297` |
| `OAK-EXTENSION-PATH` | extension files must be regular files; extension files must not be symlinks; extension payload path is unsafe | `src/oak/adapters/extensions/store.py:293` |
| `OAK-EXTENSION-PAYLOAD` | extension file size is out of bounds; extension payload has too many files | `src/oak/adapters/extensions/store.py:118` |
| `OAK-EXTENSION-QUARANTINED` | extension failed verification and stays quarantined (some dynamic) | `src/oak/application/extensions.py:112` |
| `OAK-EXTENSION-SIGNER` | extensions are signed by the steward role | `src/oak/application/extensions.py:140` |
| `OAK-EXTENSION-SOURCE` | extension source must be a plain directory | `src/oak/adapters/extensions/store.py:205` |
| `OAK-EXTENSION-STATE` | extension is not active; only a quarantined extension can activate | `src/oak/adapters/extensions/store.py:139` |
| `OAK-EXTENSION-TARGET` | *dynamic message* | `src/oak/interfaces/cli/main.py:1267` |
| `OAK-EXTENSION-VERSION` | version has no comparable numbers | `src/oak/application/extensions.py:469` |
| `OAK-EXTENSION-VERSION-ACTIVE` | *dynamic message* | `src/oak/adapters/extensions/store.py:154` |

### Runner, signing, approval and dispatch (23)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-APPROVAL-ACTION` | approval action is not recognized | `src/oak/application/release.py:153` |
| `OAK-APPROVAL-EXPIRY` | approval expiry must be in the future | `src/oak/application/release.py:174` |
| `OAK-APPROVAL-MISSING` | no approval exists for that action | `src/oak/application/release.py:249` |
| `OAK-APPROVAL-REVOKED` | approval is already revoked | `src/oak/application/release.py:253` |
| `OAK-APPROVAL-STATE` | approval requires a compiled bundle | `src/oak/application/release.py:167` |
| `OAK-DISPATCH-APPROVAL` | approval action does not match dispatch; approval binds a different bundle digest; approval binds a different plan digest; and 3 more (some dynamic) | `src/oak/application/release.py:355` |
| `OAK-DISPATCH-EXISTS` | dispatch envelope was already delivered | `src/oak/adapters/dispatch/mailbox.py:40` |
| `OAK-DISPATCH-KINDS` | dispatch requested an unclassified kind; dispatch requested kinds absent from the compiled plan; dispatch requires at least one operation kind | `src/oak/application/release.py:307` |
| `OAK-DISPATCH-NAME` | mailbox document name is unsafe | `src/oak/adapters/dispatch/mailbox.py:93` |
| `OAK-DISPATCH-SIGNATURE` | plan signature binds a different plan; plan signature does not verify | `src/oak/application/release.py:337` |
| `OAK-DISPATCH-SIZE` | dispatch document exceeds the mailbox bound | `src/oak/adapters/dispatch/mailbox.py:84` |
| `OAK-DISPATCH-STATE` | dispatch requires a compiled bundle | `src/oak/application/release.py:322` |
| `OAK-GITOPS-OUTPUT` | --output is required | `src/oak/interfaces/cli/main.py:1120` |
| `OAK-KEYS-ACTION` | keys action must be init or show | `src/oak/interfaces/cli/main.py:927` |
| `OAK-RUNNER-APPLY` | fixture container creation failed | `src/oak/runner/adapters.py:95` |
| `OAK-RUNNER-CONFIG` | OAK_RUNNER_TARGET_PROFILE could not be read; OAK_RUNNER_TARGET_PROFILE is not a valid target profile; the runner home, mailbox or trust anchors are unreadable | `src/oak/runner/main.py:59` |
| `OAK-RUNNER-DRIFT` | target state digest drifted during execution | `src/oak/runner/execution.py:209` |
| `OAK-RUNNER-EXECUTABLE` | executable is not allowlisted (some dynamic) | `src/oak/runner/adapters.py:126` |
| `OAK-RUNNER-KEY` | runner key length is invalid; runner key must be a private regular file | `src/oak/runner/identity.py:44` |
| `OAK-RUNNER-OPERATION` | operation kind is not supported | `src/oak/runner/execution.py:217` |
| `OAK-RUNNER-PARAMETERS` | container name is not permitted; image digest is not permitted; image reference is not permitted; and 2 more | `src/oak/runner/adapters.py:135` |
| `OAK-RUNNER-ROLLBACK` | *dynamic message* | `src/oak/runner/adapters.py:121` |
| `OAK-SIGN-STATE` | plan signing requires a compiled bundle | `src/oak/application/release.py:94` |

### Rendering and deployment (6)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-RENDER-ADAPTER` | deployment renderer is not registered | `src/oak/application/rendering.py:34` |
| `OAK-RENDER-COMPONENT` | component manifest for the lock entry is not available | `src/oak/adapters/deployment/helm_kubernetes.py:49` |
| `OAK-RENDER-IMAGE` | component artifact digest is not a sha256 digest; component image reference carries a digest that is not the attested digest; component image repository is unsafe; and 1 more | `src/oak/adapters/deployment/helm_kubernetes.py:191` |
| `OAK-RENDER-NAME` | rendered label value is unsafe; rendered resource name is unsafe | `src/oak/adapters/deployment/helm_kubernetes.py:209` |
| `OAK-RENDER-OUTPUT` | --output is required | `src/oak/interfaces/cli/main.py:1209` |
| `OAK-RENDER-PATH` | rendered file path is unsafe | `src/oak/application/rendering.py:78` |

### Remote CLI (9)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-REMOTE-CASE-REQUIRED` | remote mode requires an explicit design-case identifier | `src/oak/interfaces/cli/main.py:108` |
| `OAK-REMOTE-DIGEST` | remote export digest is invalid; remote export object digest does not match (some dynamic) | `src/oak/interfaces/cli/remote.py:359` |
| `OAK-REMOTE-OPERATION-TIMEOUT` | *dynamic message* | `src/oak/interfaces/cli/remote.py:305` |
| `OAK-REMOTE-PROTOCOL` | remote candidate result is malformed; remote case extensions are invalid; remote export document is invalid; and 9 more (some dynamic) | `src/oak/interfaces/cli/main.py:389` |
| `OAK-REMOTE-REQUEST` | input is not canonical JSON data; request body is not canonical JSON | `src/oak/interfaces/cli/remote.py:349` |
| `OAK-REMOTE-SERVER` | --server must be an http or https URL | `src/oak/interfaces/cli/remote.py:62` |
| `OAK-REMOTE-SIZE` | remote export exceeds the size limit; remote export object exceeds the size limit; remote response exceeds the size limit | `src/oak/interfaces/cli/remote.py:114` |
| `OAK-REMOTE-UNAVAILABLE` | the remote control plane could not be reached | `src/oak/interfaces/cli/remote.py:108` |
| `OAK-REMOTE-UNSUPPORTED` | init is local-only; a remote case is created by oak design; mcp serve is local-only; serve is local-only (some dynamic) | `src/oak/interfaces/cli/main.py:100` |

### Headless validation (11)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-VALIDATE-DIGEST` | deployment bundle does not reference this architecture decision; export object digest is invalid; runner plan does not reference this deployment bundle | `src/oak/interfaces/cli/validate.py:125` |
| `OAK-VALIDATE-EXECUTION-FIELD` | *dynamic message* | `src/oak/interfaces/cli/validate.py:64` |
| `OAK-VALIDATE-KEY` | publisher identity carries no public key; publisher identity document is invalid | `src/oak/interfaces/cli/validate.py:187` |
| `OAK-VALIDATE-KEY-REQUIRED` | --public-key is required to verify a webhook envelope | `src/oak/interfaces/cli/main.py:877` |
| `OAK-VALIDATE-KIND` | validate kind must be export, bundle, or webhook | `src/oak/interfaces/cli/main.py:887` |
| `OAK-VALIDATE-MALFORMED` | an export object is not canonical JSON; export manifest entry is invalid; export manifest index is invalid; and 3 more (some dynamic) | `src/oak/interfaces/cli/validate.py:110` |
| `OAK-VALIDATE-PLAN-STATUS` | runner plan is not an inert draft | `src/oak/interfaces/cli/validate.py:168` |
| `OAK-VALIDATE-SIZE` | input size is outside the accepted range | `src/oak/interfaces/cli/validate.py:53` |
| `OAK-VALIDATE-UNSAFE-PATH` | bundle must be a regular directory; export must be a regular directory; input could not be opened safely; and 2 more | `src/oak/interfaces/cli/validate.py:107` |
| `OAK-VALIDATE-WEBHOOK-KEY` | envelope key id does not derive from the pinned publisher key; envelope signer does not match the pinned publisher key | `src/oak/interfaces/cli/validate.py:223` |
| `OAK-VALIDATE-WEBHOOK-SIGNATURE` | envelope signature does not verify under the pinned publisher key | `src/oak/interfaces/cli/validate.py:247` |

### Durable operations and the outbox (22)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-OPERATION-ATTEMPTS` | operation attempts must be between 1 and 10 | `src/oak/adapters/persistence/operations.py:550` |
| `OAK-OPERATION-CANCELLED` | the remote operation was cancelled | `src/oak/interfaces/cli/remote.py:302` |
| `OAK-OPERATION-CONFLICT` | operation identity already exists | `src/oak/adapters/persistence/operations.py:103` |
| `OAK-OPERATION-CORRUPT` | operation request is not an object | `src/oak/adapters/persistence/operations.py:496` |
| `OAK-OPERATION-DOCUMENT` | operation candidate is invalid; operation document is invalid; operation request is invalid; and 1 more (some dynamic) | `src/oak/adapters/persistence/operations.py:561` |
| `OAK-OPERATION-ERROR-CODE` | operation error code is invalid | `src/oak/adapters/persistence/operations.py:568` |
| `OAK-OPERATION-FAILED` | the remote operation failed | `src/oak/interfaces/cli/remote.py:303` |
| `OAK-OPERATION-KIND` | operation kind is not supported | `src/oak/application/control_plane.py:432` |
| `OAK-OPERATION-LEASE` | heartbeat lease must extend into the future; operation lease must expire after claim time | `src/oak/adapters/persistence/operations.py:188` |
| `OAK-OPERATION-LEASE-LOST` | operation lease is no longer current | `src/oak/adapters/persistence/operations.py:470` |
| `OAK-OPERATION-NOT-CANCELLING` | operation has no cancellation request | `src/oak/adapters/persistence/operations.py:399` |
| `OAK-OPERATION-NOT-FOUND` | operation was not found | `src/oak/adapters/persistence/operations.py:481` |
| `OAK-OPERATION-SCOPE` | operation workspace does not match its case | `src/oak/application/control_plane.py:420` |
| `OAK-OPERATION-SIZE` | *dynamic message* | `src/oak/adapters/persistence/operations.py:563` |
| `OAK-OPERATION-UNSAFE-FIELD` | operation request contains a prohibited execution field | `src/oak/application/operations.py:133` |
| `OAK-OUTBOX-CORRUPT` | outbox payload is not an object | `src/oak/adapters/persistence/outbox.py:277` |
| `OAK-OUTBOX-ERROR-CODE` | outbox error code is invalid | `src/oak/adapters/persistence/outbox.py:123` |
| `OAK-OUTBOX-LEASE` | outbox lease must expire after claim time | `src/oak/adapters/persistence/outbox.py:48` |
| `OAK-OUTBOX-LEASE-LOST` | outbox delivery lease is no longer current | `src/oak/adapters/persistence/outbox.py:110` |
| `OAK-OUTBOX-LIMIT` | outbox claim limit must be between 1 and 100 | `src/oak/adapters/persistence/outbox.py:44` |
| `OAK-OUTBOX-UNAVAILABLE` | outbox observation is unavailable | `src/oak/application/control_plane.py:389` |
| `OAK-PROJECTION-NAME` | projection name is invalid | `src/oak/adapters/persistence/outbox.py:152` |

### Concurrency, identity and requests (9)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-ACTOR-DENIED` | local actor is not authorized | `src/oak/interfaces/api/app.py:73` |
| `OAK-CORRELATION-ID` | correlation ID must contain at least 8 characters | `src/oak/application/candidate_planning.py:677` |
| `OAK-DIRECTORY-UNAVAILABLE` | design-case directory is unavailable | `src/oak/application/control_plane.py:117` |
| `OAK-EXPECTED-VERSION` | expected case version does not match current version (some dynamic) | `src/oak/adapters/persistence/file_workspace.py:469` |
| `OAK-IDEMPOTENCY-CONFLICT` | idempotency key was already used for different input; idempotency key was already used for different operation input; import destination contains different canonical state | `src/oak/adapters/persistence/file_workspace.py:190` |
| `OAK-IDEMPOTENCY-KEY` | cancellation idempotency key is invalid; idempotency key is required; idempotency key must contain at least 16 characters; and 1 more | `src/oak/adapters/persistence/operations.py:147` |
| `OAK-PRECONDITION-INVALID` | expected version is required; weak entity tags are not accepted | `src/oak/interfaces/api/app.py:160` |
| `OAK-TENANT-MISMATCH` | repository scope does not match workspace initialization; requested resource was not found; workspace tenant does not match command | `src/oak/adapters/persistence/postgresql.py:99` |
| `OAK-TIME-INVALID` | timestamp must include a timezone; worker timestamp must include a timezone | `src/oak/adapters/persistence/postgresql.py:927` |

### Everything else (19)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-AUDIT-LINEAGE` | audit event does not extend the current head; audit event result does not match its case; audit result does not match its event; and 10 more | `src/oak/adapters/persistence/file_workspace.py:367` |
| `OAK-AUDIT-SEQUENCE` | audit event sequence is not contiguous | `src/oak/adapters/persistence/file_workspace.py:364` |
| `OAK-CURSOR-INVALID` | pagination cursor is invalid | `src/oak/interfaces/api/app.py:183` |
| `OAK-DEPENDENCY-MISSING` | case has no recorded policy decision; rendering requires a compiled bundle; rendering requires a semantic manifest; and 1 more (some dynamic) | `src/oak/application/candidate_planning.py:655` |
| `OAK-INTERPRET-BRIEF-TYPE` | brief unknowns must be a string array (some dynamic) | `src/oak/compiler/interpretation.py:277` |
| `OAK-INTERPRET-STATE` | only a draft case can be interpreted | `src/oak/application/design_case.py:251` |
| `OAK-INTERPRETER-INPUT-LIMIT` | proposal input exceeds its limit | `src/oak/adapters/models/fake_interpreter.py:28` |
| `OAK-INTERPRETER-MALFORMED` | optional interpreter returned no proposal; optional proposal failed validation; optional proposal is not canonical JSON data; and 1 more | `src/oak/adapters/models/fake_interpreter.py:36` |
| `OAK-INTERPRETER-OUTPUT-LIMIT` | proposal output exceeds its limit | `src/oak/compiler/interpretation.py:655` |
| `OAK-INTERPRETER-SOURCE` | optional proposal is not bound to the requested source record | `src/oak/application/design_case.py:478` |
| `OAK-INTERPRETER-UNAVAILABLE` | optional interpretation provider is unavailable | `src/oak/adapters/models/fake_interpreter.py:30` |
| `OAK-JOURNAL-ENTRY` | journal entry type is not recognized | `src/oak/runner/journal.py:59` |
| `OAK-JOURNAL-TAMPERED` | journal hash chain does not verify | `src/oak/runner/journal.py:101` |
| `OAK-OUTPUT-EXISTS` | GitOps output directory already exists; output directory already exists; render output directory already exists | `src/oak/application/gitops.py:36` |
| `OAK-REVOCATION-REASON` | revocation requires a reason | `src/oak/application/release.py:236` |
| `OAK-SIGNING-KEY-INVALID` | signing key length is invalid; signing key must be a regular file | `src/oak/adapters/signing/local_ed25519.py:75` |
| `OAK-SIGNING-KEY-MISSING` | signing key does not exist; run oak keys init | `src/oak/adapters/signing/local_ed25519.py:70` |
| `OAK-SIGNING-KEY-PERMISSIONS` | signing key must not be group or world accessible | `src/oak/adapters/signing/local_ed25519.py:77` |
| `OAK-SIGNING-ROLE` | signing role is not recognized | `src/oak/adapters/signing/local_ed25519.py:99` |

