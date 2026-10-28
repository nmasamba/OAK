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
| Runner | `CODE: message` on stderr. Exit `64` for a configuration refusal (a required `OAK_RUNNER_*` variable missing), `70` for a verification or execution refusal |
| Process startup | `oak-api`, `oak-worker`, `oak-db-migrate` and `oak-mcp` print `CODE: message` and exit non-zero before serving anything. `OAK-SAFE-BIND`, `OAK-DATABASE-CONFIG`, `OAK-DATABASE-MIGRATION`, `OAK-WORKER-CONFIG` and `OAK-MCP-CONFIG` reach you only this way |

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
| `OAK-CASE-NOT-FOUND` | The case id names no design case here. On a server (REST, MCP and the remote CLI alike) the server holds no such case; locally, the workspace has no case yet, or `--case` names a different one | Check the case id: `GET /v1/design-cases` lists the cases a server holds. Locally, run `oak design` first |
| `OAK-WORKSPACE-NOT-FOUND` | There is no OAK workspace at this location | Check the working directory, or run `oak init` |
| `OAK-ARTIFACT-NOT-FOUND` | The workspace is present; this artifact reference did not match | Check the id, version and digest triple. The workspace is fine |
| `OAK-WORKSPACE-CORRUPT` | The manifest or an indexed object failed verification | Run `python scripts/verify_deployment.py --workspace <dir>`. See [operations.md](operations.md#restore) |
| `OAK-REMOTE-UNSUPPORTED` | A local-only command was run with `--server` | Signing, approval, dispatch, keys, model-provider configuration, extensions and policy are local-only by design |
| `OAK-REMOTE-UNAVAILABLE` | The control plane could not be reached | Check the URL and that `oak-api` is running |
| `OAK-TENANT-MISMATCH` | A different tenant was requested | Reported as not-found on purpose, so it leaks no existence information |
| `OAK-ACTOR-DENIED` | A different actor was claimed | The local actor is bound by `OAK_LOCAL_ACTOR` |

## Full index

372 codes across 17 families.

### Workspace, artifacts and import/export (23)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-ARTIFACT-COLLISION` | artifact digest collision detected | `src/oak/adapters/persistence/file_workspace.py:542` |
| `OAK-ARTIFACT-DIGEST` | artifact digest is invalid | `src/oak/adapters/persistence/file_workspace.py:802` |
| `OAK-ARTIFACT-IDENTITY` | artifact metadata does not match canonical content | `src/oak/adapters/persistence/file_workspace.py:459` |
| `OAK-ARTIFACT-IMMUTABLE` | an immutable artifact version already has different content | `src/oak/adapters/persistence/file_workspace.py:476` |
| `OAK-ARTIFACT-INVALID` | a brief source must carry a brief media type; a report rendering must be a PDF document; artifact media type does not fit its kind; and 2 more (some dynamic) | `src/oak/adapters/persistence/file_workspace.py:106` |
| `OAK-ARTIFACT-KIND` | artifact kind is not supported | `src/oak/adapters/persistence/file_workspace.py:104` |
| `OAK-ARTIFACT-NONCANONICAL` | canonical artifact bytes are not normalized | `src/oak/adapters/persistence/file_workspace.py:463` |
| `OAK-ARTIFACT-NOT-FOUND` | artifact was not found | `src/oak/adapters/persistence/postgresql.py:245` |
| `OAK-ARTIFACT-SIZE` | artifact exceeds the local size limit | `src/oak/adapters/persistence/file_workspace.py:535` |
| `OAK-EXPORT-EXISTS` | export destination already exists | `src/oak/adapters/persistence/file_workspace.py:261` |
| `OAK-EXPORT-OUTPUT` | --output is required; output directory already exists | `src/oak/interfaces/cli/main.py:895` |
| `OAK-EXPORT-SIZE` | canonical export exceeds the size limit | `src/oak/adapters/persistence/postgresql.py:347` |
| `OAK-IMPORT-DIGEST` | an imported object digest does not match; import object digest does not match; import object digest is invalid | `src/oak/adapters/persistence/file_workspace.py:331` |
| `OAK-IMPORT-INVALID` | an imported artifact does not fit its indexed kind; an imported object size does not match; an indexed import object is missing; and 13 more | `src/oak/adapters/persistence/file_workspace.py:303` |
| `OAK-IMPORT-REPLAY` | *dynamic message* | `src/oak/application/control_plane.py:524` |
| `OAK-IMPORT-SCOPE` | import tenant does not match command authority; import workspace or tenant does not match destination | `src/oak/adapters/persistence/postgresql.py:367` |
| `OAK-IMPORT-SIZE` | an import object exceeds the size limit; canonical import exceeds the size limit; import manifest exceeds the size limit | `src/oak/adapters/persistence/postgresql.py:382` |
| `OAK-IMPORT-UNSAFE-PATH` | import object store is unsafe; import source must be a regular directory | `src/oak/adapters/persistence/file_workspace.py:292` |
| `OAK-WORKSPACE-CORRUPT` | artifact reference is not canonical JSON; artifact reference is not indexed correctly; canonical artifact is not an object; and 11 more | `src/oak/adapters/persistence/file_workspace.py:183` |
| `OAK-WORKSPACE-EXISTS` | import destination is already initialized; workspace is already initialized | `src/oak/adapters/persistence/file_workspace.py:148` |
| `OAK-WORKSPACE-MUTATION` | mutation is missing its audit event; mutation is missing its case artifact; outbox event identity changed; and 2 more | `src/oak/adapters/persistence/file_workspace.py:391` |
| `OAK-WORKSPACE-NOT-FOUND` | no OAK workspace found; workspace is not initialized; workspace manifest is missing; and 1 more | `src/oak/adapters/persistence/file_workspace.py:141` |
| `OAK-WORKSPACE-UNSAFE-PATH` | workspace root cannot be a symlink | `src/oak/adapters/persistence/file_workspace.py:145` |

### Design case: intake, interpretation, confirmation (35)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-CASE-CONFLICT` | workspace contains a different design case | `src/oak/application/control_plane.py:178` |
| `OAK-CASE-EXISTS` | *dynamic message* | `src/oak/application/design_case.py:180` |
| `OAK-CASE-NOT-FOUND` | design case was not found; requested design case is not current; the server holds no such design case; and 1 more (some dynamic) | `src/oak/application/candidate_planning.py:796` |
| `OAK-CASE-TRANSITION-DENIED` | *dynamic message* | `src/oak/domain/design_case.py:95` |
| `OAK-CASE-VERSION` | case version is not a supported semantic version | `src/oak/domain/design_case.py:46` |
| `OAK-CONFIRM-ANSWERS` | --answers is required | `src/oak/interfaces/cli/main.py:438` |
| `OAK-CONFIRM-CASE` | answers target a different design case | `src/oak/application/design_case.py:473` |
| `OAK-CONFIRM-CONTROL` | answers contain a prohibited control or formatting character | `src/oak/application/design_case.py:448` |
| `OAK-CONFIRM-DECISION` | confirmation decision is unsupported | `src/oak/application/design_case.py:907` |
| `OAK-CONFIRM-DUPLICATE` | each question may be answered once | `src/oak/application/design_case.py:485` |
| `OAK-CONFIRM-MALFORMED` | answers are malformed; confirmation input is not canonical JSON data | `src/oak/application/design_case.py:455` |
| `OAK-CONFIRM-PATH` | confirmation path has no current value; confirmation path is outside intent spec; rejected claim path does not exist | `src/oak/application/design_case.py:1005` |
| `OAK-CONFIRM-PROVENANCE` | claim has no provenance to confirm | `src/oak/application/design_case.py:1020` |
| `OAK-CONFIRM-QUESTION` | answer references no open question | `src/oak/application/design_case.py:492` |
| `OAK-CONFIRM-STATE` | claims can be confirmed only while the case needs confirmation | `src/oak/application/design_case.py:475` |
| `OAK-CONFIRM-VALUE-MISMATCH` | confirmed value does not match the current canonical claim | `src/oak/application/design_case.py:887` |
| `OAK-INTAKE-ALIAS` | YAML aliases and anchors are not accepted | `src/oak/adapters/intake/local_file.py:120` |
| `OAK-INTAKE-COMPLEXITY` | structured brief is too complex | `src/oak/adapters/intake/local_file.py:133` |
| `OAK-INTAKE-CYCLE` | structured brief contains a cycle | `src/oak/adapters/intake/local_file.py:183` |
| `OAK-INTAKE-EMPTY` | text brief has no usable content | `src/oak/compiler/interpretation.py:239` |
| `OAK-INTAKE-ENCODING` | brief must be valid UTF-8 | `src/oak/adapters/intake/local_file.py:64` |
| `OAK-INTAKE-IDENTITY` | a brief id must not contain '..'; a server design case id is at most 160 characters of lower-case letters, digits, '.', '_' and '-'; give the brief an id of that form; structured brief requires string id, brief_version, and title | `src/oak/adapters/intake/local_file.py:146` |
| `OAK-INTAKE-KEY-TYPE` | structured brief keys must be strings | `src/oak/adapters/intake/local_file.py:187` |
| `OAK-INTAKE-MALFORMED` | structured brief is malformed | `src/oak/adapters/intake/local_file.py:135` |
| `OAK-INTAKE-NUMBER` | structured brief numbers must be finite | `src/oak/adapters/intake/local_file.py:208` |
| `OAK-INTAKE-READ` | brief could not be read | `src/oak/adapters/intake/local_file.py:92` |
| `OAK-INTAKE-SIZE` | *dynamic message* | `src/oak/adapters/intake/local_file.py:104` |
| `OAK-INTAKE-TYPE` | brief file type is not supported | `src/oak/adapters/intake/local_file.py:55` |
| `OAK-INTAKE-UNICODE-CONTROL` | brief contains a prohibited control or formatting character | `src/oak/adapters/intake/local_file.py:165` |
| `OAK-INTAKE-UNICODE-PATH` | brief filename must use NFC Unicode | `src/oak/adapters/intake/local_file.py:52` |
| `OAK-INTAKE-UNSAFE-PATH` | brief filename must not contain a path; brief must be a regular non-symlink file (some dynamic) | `src/oak/adapters/intake/local_file.py:37` |
| `OAK-INTAKE-VALUE-TYPE` | structured brief contains a non-JSON value | `src/oak/adapters/intake/local_file.py:210` |
| `OAK-INTENT-NOT-FOUND` | design case has no intent artifact; interpreted design has no intent artifact | `src/oak/application/design_case.py:765` |
| `OAK-INTENT-PROVENANCE` | every populated scalar intent value must have exactly one provenance record | `src/oak/compiler/interpretation.py:1043` |
| `OAK-SOURCE-MISSING` | draft case has no source record; intent has no source record | `src/oak/application/design_case.py:655` |

### Candidates, evaluation, selection and planning (22)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-ASSURE-CANDIDATE` | assurance candidate is not selected | `src/oak/application/candidate_planning.py:476` |
| `OAK-ASSURE-OUTPUT` | --output is required | `src/oak/interfaces/cli/main.py:719` |
| `OAK-ASSURE-STATE` | assurance requires candidate_selected state | `src/oak/application/candidate_planning.py:473` |
| `OAK-CANDIDATE-NOT-FOUND` | candidate is not part of this design case | `src/oak/application/architecture.py:48` |
| `OAK-CANDIDATES-STATE` | candidates require a case that is ready for candidates; candidates require every model-proposed value to be confirmed, corrected or rejected first | `src/oak/application/candidate_planning.py:170` |
| `OAK-EVALUATE-STATE` | candidate evaluation requires candidates_ready state | `src/oak/application/candidate_planning.py:339` |
| `OAK-EVALUATION-EXISTS` | candidate already has an immutable evaluation; retry with the original key | `src/oak/application/candidate_planning.py:344` |
| `OAK-EVALUATION-NOT-FOUND` | candidate has no evaluation result | `src/oak/application/candidate_planning.py:744` |
| `OAK-PLAN-CANDIDATE` | plan candidate is not selected | `src/oak/application/candidate_planning.py:580` |
| `OAK-PLAN-INPUT` | --target and --output are required; target profile is malformed | `src/oak/interfaces/cli/main.py:791` |
| `OAK-PLAN-STATE` | plan compilation requires assurance_planned state | `src/oak/application/candidate_planning.py:577` |
| `OAK-PLAN-TARGET` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/cli/main.py:837` |
| `OAK-SELECT-EVALUATION` | candidate evaluation must pass before selection | `src/oak/application/candidate_planning.py:413` |
| `OAK-SELECT-INFEASIBLE` | an infeasible candidate cannot be selected | `src/oak/application/candidate_planning.py:409` |
| `OAK-SELECT-RATIONALE` | --rationale-file is required; selection rationale is required and bounded | `src/oak/application/candidate_planning.py:385` |
| `OAK-SELECT-STATE` | selection requires candidates_ready state | `src/oak/application/candidate_planning.py:405` |
| `OAK-TARGET-CAPABILITY` | target does not allow every required read-only planning operation | `src/oak/application/candidate_planning.py:567` |
| `OAK-TARGET-EXECUTION` | execution.container_image_reference and container_image_digest are superseded; declare execution.component_images, one acknowledged image per component; mutation-capable target profile is missing its execution block (some dynamic) | `src/oak/compiler/planning.py:524` |
| `OAK-TARGET-INCOMPATIBLE` | *dynamic message* | `src/oak/compiler/planning.py:628` |
| `OAK-TARGET-INVALID` | target profile failed bounded validation | `src/oak/adapters/targets/local_profile.py:51` |
| `OAK-TARGET-PATH` | target profile must be a regular file | `src/oak/adapters/targets/local_profile.py:24` |
| `OAK-TARGET-TENANT` | target tenant does not match the command authority | `src/oak/application/candidate_planning.py:561` |

### Catalogue (30)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-CAT-AVAILABILITY-BLOCKED` | *reason or mapping code; carries no fixed message* | `src/oak/domain/catalogue_rules.py:31` |
| `OAK-CAT-EVIDENCE-FUTURE` | *reason or mapping code; carries no fixed message* | `src/oak/compiler/catalogue.py:28` |
| `OAK-CAT-EVIDENCE-STALE` | *reason or mapping code; carries no fixed message* | `src/oak/domain/catalogue_rules.py:33` |
| `OAK-CAT-EVIDENCE-UNDIGESTED` | *reason or mapping code; carries no fixed message* | `src/oak/domain/catalogue_rules.py:46` |
| `OAK-CAT-KNOWN-VULNERABILITY` | *reason or mapping code; carries no fixed message* | `src/oak/compiler/catalogue.py:28` |
| `OAK-CAT-RESEARCH-ARCHIVED` | *reason or mapping code; carries no fixed message* | `src/oak/domain/research_rules.py:71` |
| `OAK-CAT-RESEARCH-CAPABILITY` | *reason or mapping code; carries no fixed message* | `src/oak/domain/research_rules.py:77` |
| `OAK-CAT-RESEARCH-DISABLED` | *reason or mapping code; carries no fixed message* | `src/oak/domain/research_rules.py:72` |
| `OAK-CAT-RESEARCH-FORBIDDEN-WORD` | *reason or mapping code; carries no fixed message* | `src/oak/domain/research_rules.py:80` |
| `OAK-CAT-RESEARCH-FUTURE` | *reason or mapping code; carries no fixed message* | `src/oak/domain/research_rules.py:75` |
| `OAK-CAT-RESEARCH-GATED` | *reason or mapping code; carries no fixed message* | `src/oak/domain/research_rules.py:70` |
| `OAK-CAT-RESEARCH-LICENCE-BLOCKED` | *reason or mapping code; carries no fixed message* | `src/oak/domain/research_rules.py:69` |
| `OAK-CAT-RESEARCH-LICENCE-UNLISTED` | *reason or mapping code; carries no fixed message* | `src/oak/domain/research_rules.py:68` |
| `OAK-CAT-RESEARCH-MALFORMED` | *reason or mapping code; carries no fixed message* | `src/oak/domain/research_rules.py:81` |
| `OAK-CAT-RESEARCH-REJECTED` | *reason or mapping code; carries no fixed message* | `src/oak/domain/research_rules.py:79` |
| `OAK-CAT-RESEARCH-STALE` | *reason or mapping code; carries no fixed message* | `src/oak/domain/research_rules.py:74` |
| `OAK-CAT-RESEARCH-UNDATED` | *reason or mapping code; carries no fixed message* | `src/oak/domain/research_rules.py:73` |
| `OAK-CAT-RESEARCH-UNDIGESTED` | *reason or mapping code; carries no fixed message* | `src/oak/domain/research_rules.py:76` |
| `OAK-CAT-RESEARCH-UNREACHABLE` | *reason or mapping code; carries no fixed message* | `src/oak/domain/research_rules.py:82` |
| `OAK-CAT-RESEARCH-UNVETTED` | *reason or mapping code; carries no fixed message* | `src/oak/domain/research_rules.py:78` |
| `OAK-CAT-STATUS-NOT-ELIGIBLE` | *reason or mapping code; carries no fixed message* | `src/oak/domain/catalogue_rules.py:29` |
| `OAK-CAT-TRANSITIVE-LICENCE-UNRESOLVED` | *reason or mapping code; carries no fixed message* | `src/oak/domain/catalogue_rules.py:37` |
| `OAK-CATALOGUE-COUNT` | catalogue contains too many documents | `src/oak/adapters/catalogue/local_catalogue.py:37` |
| `OAK-CATALOGUE-DUPLICATE` | architecture pattern ID is duplicated; architecture pattern variant is duplicated; catalogue identities must be unique; and 1 more | `src/oak/adapters/catalogue/local_catalogue.py:53` |
| `OAK-CATALOGUE-EMPTY` | catalogue requires manifests and patterns | `src/oak/adapters/catalogue/local_catalogue.py:28` |
| `OAK-CATALOGUE-INELIGIBLE` | catalogue has no eligible manifests | `src/oak/compiler/catalogue.py:128` |
| `OAK-CATALOGUE-INVALID` | catalogue document failed bounded validation | `src/oak/adapters/catalogue/local_catalogue.py:62` |
| `OAK-CATALOGUE-PATH` | catalogue directory is unsafe or missing; catalogue documents must be regular files | `src/oak/adapters/catalogue/local_catalogue.py:34` |
| `OAK-CATALOGUE-PATTERN` | architecture edge references an unknown role; architecture pattern references a missing component manifest; architecture pattern roles are duplicated; and 2 more | `src/oak/compiler/catalogue.py:180` |
| `OAK-CATALOGUE-TIME` | catalogue timestamp is invalid | `src/oak/domain/catalogue_rules.py:23` |

### Policy (18)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-POLICY-ACTION` | policy action must be evaluate or packs | `src/oak/interfaces/cli/main.py:1932` |
| `OAK-POLICY-ENGINE-DIVERGED` | the external policy engine disagreed with the built-in reference engine; refusing to publish a decision | `src/oak/adapters/policies/opa.py:228` |
| `OAK-POLICY-ENGINE-FAILED` | opa evaluation failed; opa evaluation omitted a rule verdict; opa evaluation returned an unreadable result; and 2 more | `src/oak/adapters/policies/opa.py:260` |
| `OAK-POLICY-ENGINE-UNAVAILABLE` | the installed opa did not report its version; the built-in engine remains available; the installed opa is older than 1.0.0; the built-in engine remains available; the opa binary is not installed; the built-in engine remains available | `src/oak/adapters/policies/opa.py:126` |
| `OAK-POLICY-ENGINE-UNKNOWN` | policy engine is not registered | `src/oak/application/policy.py:85` |
| `OAK-POLICY-PACK-COUNT` | too many policy pack files | `src/oak/adapters/policies/pack_store.py:52` |
| `OAK-POLICY-PACK-DUPLICATE` | policy pack ID is duplicated | `src/oak/adapters/policies/pack_store.py:56` |
| `OAK-POLICY-PACK-EFFECTIVE` | *reason or mapping code; carries no fixed message* | `src/oak/domain/policy_rules.py:105` |
| `OAK-POLICY-PACK-EXPIRED` | *reason or mapping code; carries no fixed message* | `src/oak/domain/policy_rules.py:104` |
| `OAK-POLICY-PACK-INVALID` | policy pack failed bounded validation; policy pack must not use YAML aliases; policy pack size is out of bounds | `src/oak/adapters/policies/pack_store.py:124` |
| `OAK-POLICY-PACK-NOT-FOUND` | policy pack is not available | `src/oak/adapters/policies/pack_store.py:64` |
| `OAK-POLICY-PACK-NOT-YET-EFFECTIVE` | *reason or mapping code; carries no fixed message* | `src/oak/domain/policy_rules.py:101` |
| `OAK-POLICY-PACK-PATH` | policy pack must be a regular file; policy pack path must not be a symlink | `src/oak/adapters/policies/pack_store.py:114` |
| `OAK-POLICY-PACK-REQUIRED` | --pack is required to evaluate | `src/oak/interfaces/cli/main.py:1934` |
| `OAK-POLICY-PACK-STATUS` | *reason or mapping code; carries no fixed message* | `src/oak/domain/policy_rules.py:99` |
| `OAK-POLICY-PACK-UNVERIFIED` | an activated policy pack no longer matches what was verified at activation; an activated policy pack's records are unreadable | `src/oak/adapters/policies/pack_store.py:105` |
| `OAK-POLICY-SUBJECT` | policy evaluation requires an interpreted intent | `src/oak/application/policy.py:193` |
| `OAK-POLICY-TIME` | policy timestamp is invalid; policy timestamp must carry a UTC offset | `src/oak/domain/policy_rules.py:258` |

### Extensions (16)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-EXTENSION-ACTION` | extensions action is not recognized | `src/oak/interfaces/cli/main.py:2096` |
| `OAK-EXTENSION-AMBIGUOUS` | multiple versions are installed; pass --version | `src/oak/adapters/extensions/store.py:101` |
| `OAK-EXTENSION-CORRUPT` | activation record is not an object; extension directory name is invalid; extension manifest identity does not match its directory | `src/oak/adapters/extensions/store.py:199` |
| `OAK-EXTENSION-EXISTS` | a quarantined copy already exists; extension version is already active; extension version is already installed | `src/oak/adapters/extensions/store.py:144` |
| `OAK-EXTENSION-IDENTITY` | extension identity is unsafe | `src/oak/adapters/extensions/store.py:320` |
| `OAK-EXTENSION-MANIFEST` | extension manifest failed bounded parsing; extension manifest must not use YAML aliases | `src/oak/adapters/extensions/store.py:255` |
| `OAK-EXTENSION-NOT-FOUND` | extension file does not exist; extension is not installed | `src/oak/adapters/extensions/store.py:297` |
| `OAK-EXTENSION-PATH` | extension files must be regular files; extension files must not be symlinks; extension payload path is unsafe | `src/oak/adapters/extensions/store.py:293` |
| `OAK-EXTENSION-PAYLOAD` | extension file size is out of bounds; extension payload has too many files | `src/oak/adapters/extensions/store.py:118` |
| `OAK-EXTENSION-QUARANTINED` | extension failed verification and stays quarantined (some dynamic) | `src/oak/application/extensions.py:117` |
| `OAK-EXTENSION-SIGNER` | extensions are signed by the steward role | `src/oak/application/extensions.py:145` |
| `OAK-EXTENSION-SOURCE` | extension source must be a plain directory | `src/oak/adapters/extensions/store.py:205` |
| `OAK-EXTENSION-STATE` | extension is not active; only a quarantined extension can activate | `src/oak/adapters/extensions/store.py:139` |
| `OAK-EXTENSION-TARGET` | *dynamic message* | `src/oak/interfaces/cli/main.py:2031` |
| `OAK-EXTENSION-VERSION` | version has no comparable numbers | `src/oak/application/extensions.py:476` |
| `OAK-EXTENSION-VERSION-ACTIVE` | *dynamic message* | `src/oak/adapters/extensions/store.py:154` |

### Runner, signing, approval and dispatch (57)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-APPROVAL-ACTION` | approval action is not recognized | `src/oak/application/release.py:174` |
| `OAK-APPROVAL-ARCHITECTURE` | approve the architecture before approving its installation; the architecture approval is not current for this plan | `src/oak/application/release.py:900` |
| `OAK-APPROVAL-EXPIRY` | approval expiry must be in the future | `src/oak/application/release.py:208` |
| `OAK-APPROVAL-MISSING` | no approval exists for that action | `src/oak/application/release.py:307` |
| `OAK-APPROVAL-REVOKED` | approval is already revoked | `src/oak/application/release.py:311` |
| `OAK-APPROVAL-STATE` | an installed case accepts only rollback and destroy approvals; approval requires a compiled bundle | `src/oak/application/release.py:192` |
| `OAK-DISPATCH-APPROVAL` | approval action does not match dispatch; approval binds a different bundle digest; approval binds a different plan digest; and 4 more (some dynamic) | `src/oak/application/release.py:455` |
| `OAK-DISPATCH-EXISTS` | dispatch envelope was already delivered; this mailbox already holds a dispatch with that id (another workspace of the same case?); give each workspace its own OAK_DISPATCH_MAILBOX | `src/oak/adapters/dispatch/mailbox.py:47` |
| `OAK-DISPATCH-KINDS` | dispatch requested an unclassified kind; dispatch requested kinds absent from the compiled plan; dispatch requires at least one operation kind | `src/oak/application/release.py:398` |
| `OAK-DISPATCH-NAME` | mailbox document name is unsafe; notice id collides with the manifest | `src/oak/adapters/dispatch/mailbox.py:100` |
| `OAK-DISPATCH-SIGNATURE` | plan signature binds a different plan; plan signature does not verify | `src/oak/application/release.py:434` |
| `OAK-DISPATCH-SIZE` | dispatch document exceeds the mailbox bound | `src/oak/adapters/dispatch/mailbox.py:134` |
| `OAK-DISPATCH-STATE` | dispatch requires a compiled bundle | `src/oak/application/release.py:419` |
| `OAK-GITOPS-OUTPUT` | --output is required | `src/oak/interfaces/cli/main.py:1883` |
| `OAK-INGEST-JOURNAL` | the completion names an invalid journal length; the runner's journal for this lease no longer reaches the entry it reported before; inspect the runner home before believing it | `src/oak/application/release.py:862` |
| `OAK-INGEST-RUNNER-UNENROLLED` | no runner is enrolled, so no runner message can be believed; pin the runner's public identity with `oak keys enroll-runner` first | `src/oak/application/release.py:552` |
| `OAK-KEYS-ACTION` | keys action must be init, show or enroll-runner | `src/oak/interfaces/cli/main.py:1115` |
| `OAK-KEYS-RUNNER-IDENTITY` | a runner identity must be a JSON object; an enrolled runner identity file has been altered; an enrolled runner identity is not a file; and 4 more | `src/oak/adapters/signing/local_ed25519.py:107` |
| `OAK-KEYS-UNINITIALIZED` | no signing keys exist yet; run oak keys init to create them | `src/oak/adapters/signing/local_ed25519.py:126` |
| `OAK-RUNNER-ADAPTER` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:441` |
| `OAK-RUNNER-APPLY` | container labels could not be read; container state could not be read; fixture container creation failed | `src/oak/runner/adapters.py:379` |
| `OAK-RUNNER-APPROVAL` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:494` |
| `OAK-RUNNER-ATTACHMENT` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:258` |
| `OAK-RUNNER-BUSY` | another oak-runner run-once is using this runner home | `src/oak/runner/main.py:75` |
| `OAK-RUNNER-CONFIG` | OAK_RUNNER_TARGET_PROFILE could not be read; OAK_RUNNER_TARGET_PROFILE is not a valid target profile; the runner home has no room for a working directory; and 2 more | `src/oak/runner/main.py:101` |
| `OAK-RUNNER-DIGEST` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:707` |
| `OAK-RUNNER-DRIFT` | target state digest drifted during execution | `src/oak/runner/execution.py:277` |
| `OAK-RUNNER-ENVIRONMENT` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:303` |
| `OAK-RUNNER-EXECUTABLE` | executable is not allowlisted (some dynamic) | `src/oak/runner/adapters.py:141` |
| `OAK-RUNNER-FOREIGN` | a container this installation does not own already has the planned name | `src/oak/runner/adapters.py:736` |
| `OAK-RUNNER-IMAGE` | resolved image does not carry the approved digest | `src/oak/runner/adapters.py:463` |
| `OAK-RUNNER-ISOLATION` | the container's configuration does not match the approved isolation; the existing container was created under a different isolation | `src/oak/runner/adapters.py:427` |
| `OAK-RUNNER-KEY` | runner key length is invalid; runner key must be a private regular file | `src/oak/runner/identity.py:44` |
| `OAK-RUNNER-LEASE` | the lease expired before the next side effect | `src/oak/runner/adapters.py:755` |
| `OAK-RUNNER-MAILBOX` | *dynamic message* | `src/oak/runner/main.py:237` |
| `OAK-RUNNER-NETWORK` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:480` |
| `OAK-RUNNER-OPERATION` | operation kind is not supported | `src/oak/runner/execution.py:279` |
| `OAK-RUNNER-PARAMETERS` | container entry is not permitted; container list is not permitted; container name is not permitted; and 8 more | `src/oak/runner/adapters.py:797` |
| `OAK-RUNNER-PLAN-EXPIRED` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:323` |
| `OAK-RUNNER-PLAN-STATE` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:318` |
| `OAK-RUNNER-POLICY` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:369` |
| `OAK-RUNNER-PROTOCOL` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:236` |
| `OAK-RUNNER-REGISTRY` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:619` |
| `OAK-RUNNER-REPLAY` | the consumed-nonce ledger is malformed; refusing to treat it as empty; the consumed-nonce ledger is unreadable; refusing to treat it as empty | `src/oak/runner/mailbox.py:229` |
| `OAK-RUNNER-REVOCATION` | revocation directory contains an entry that is not a notice; revocation directory is missing or unreadable; revocation notice exceeds the mailbox bound; and 4 more | `src/oak/runner/mailbox.py:142` |
| `OAK-RUNNER-ROLLBACK` | *dynamic message* | `src/oak/runner/adapters.py:663` |
| `OAK-RUNNER-SCHEMA` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:716` |
| `OAK-RUNNER-SECRETS` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:469` |
| `OAK-RUNNER-SEPARATION` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:355` |
| `OAK-RUNNER-SIGNATURE` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:112` |
| `OAK-RUNNER-SMOKE-TEST` | *reason or mapping code; carries no fixed message* | `src/oak/runner/adapters.py:348` |
| `OAK-RUNNER-SUBPROCESS` | docker invocation failed before completing | `src/oak/runner/adapters.py:769` |
| `OAK-RUNNER-TARGET` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:288` |
| `OAK-RUNNER-TARGET-CAPABILITY` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:488` |
| `OAK-RUNNER-TENANT` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:298` |
| `OAK-RUNNER-TRUST` | *reason or mapping code; carries no fixed message* | `src/oak/runner/verification.py:126` |
| `OAK-SIGN-STATE` | plan signing requires a compiled bundle | `src/oak/application/release.py:115` |

### Rendering and deployment (6)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-RENDER-ADAPTER` | deployment renderer is not registered | `src/oak/application/rendering.py:34` |
| `OAK-RENDER-COMPONENT` | component manifest for the lock entry is not available | `src/oak/adapters/deployment/helm_kubernetes.py:49` |
| `OAK-RENDER-IMAGE` | component artifact digest is not a sha256 digest; component image reference carries a digest that is not the attested digest; component image repository is unsafe; and 1 more | `src/oak/adapters/deployment/helm_kubernetes.py:191` |
| `OAK-RENDER-NAME` | rendered label value is unsafe; rendered resource name is unsafe | `src/oak/adapters/deployment/helm_kubernetes.py:209` |
| `OAK-RENDER-OUTPUT` | --output is required | `src/oak/interfaces/cli/main.py:1973` |
| `OAK-RENDER-PATH` | rendered file path is unsafe | `src/oak/application/rendering.py:78` |

### Remote CLI (9)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-REMOTE-CASE-REQUIRED` | remote mode requires an explicit design-case identifier | `src/oak/interfaces/cli/main.py:134` |
| `OAK-REMOTE-DIGEST` | remote export digest is invalid; remote export object digest does not match (some dynamic) | `src/oak/interfaces/cli/remote.py:238` |
| `OAK-REMOTE-OPERATION-TIMEOUT` | *dynamic message* | `src/oak/interfaces/cli/remote.py:465` |
| `OAK-REMOTE-PROTOCOL` | remote candidate result is malformed; remote case extensions are invalid; remote case is invalid; and 11 more (some dynamic) | `src/oak/interfaces/cli/main.py:1367` |
| `OAK-REMOTE-REQUEST` | input is not canonical JSON data; request body is not canonical JSON | `src/oak/interfaces/cli/remote.py:123` |
| `OAK-REMOTE-SERVER` | --server must be an http or https URL | `src/oak/interfaces/cli/remote.py:89` |
| `OAK-REMOTE-SIZE` | remote export exceeds the size limit; remote export object exceeds the size limit; remote response exceeds the size limit | `src/oak/interfaces/cli/remote.py:145` |
| `OAK-REMOTE-UNAVAILABLE` | the remote control plane could not be reached | `src/oak/interfaces/cli/remote.py:139` |
| `OAK-REMOTE-UNSUPPORTED` | init is local-only; a remote case is created by oak design; mcp serve is local-only; serve is local-only (some dynamic) | `src/oak/interfaces/cli/main.py:1081` |

### MCP (2)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-MCP-CONFIG` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/mcp/server.py:237` |
| `OAK-TOOL-UNKNOWN` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/mcp/server.py:167` |

### Headless validation (11)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-VALIDATE-DIGEST` | deployment bundle does not reference this architecture decision; export object digest is invalid; runner plan does not reference this deployment bundle; and 1 more | `src/oak/interfaces/cli/validate.py:131` |
| `OAK-VALIDATE-EXECUTION-FIELD` | *dynamic message* | `src/oak/interfaces/cli/validate.py:64` |
| `OAK-VALIDATE-KEY` | publisher identity carries no public key; publisher identity document is invalid | `src/oak/interfaces/cli/validate.py:231` |
| `OAK-VALIDATE-KEY-REQUIRED` | --public-key is required to verify a webhook envelope | `src/oak/interfaces/cli/main.py:1052` |
| `OAK-VALIDATE-KIND` | this directory is a case export, not a compiled bundle; run oak validate export on it; this directory is a compiled bundle, not a case export; run oak validate bundle on it; validate kind must be export, bundle, or webhook | `src/oak/interfaces/cli/main.py:1062` |
| `OAK-VALIDATE-MALFORMED` | an export object is not canonical JSON; export manifest entry is invalid; export manifest index is invalid; and 3 more (some dynamic) | `src/oak/interfaces/cli/validate.py:116` |
| `OAK-VALIDATE-PLAN-STATUS` | runner plan is not an inert draft | `src/oak/interfaces/cli/validate.py:204` |
| `OAK-VALIDATE-SIZE` | input size is outside the accepted range | `src/oak/interfaces/cli/validate.py:53` |
| `OAK-VALIDATE-UNSAFE-PATH` | bundle must be a regular directory; export must be a regular directory; input could not be opened safely; and 2 more | `src/oak/interfaces/cli/validate.py:107` |
| `OAK-VALIDATE-WEBHOOK-KEY` | envelope key id does not derive from the pinned publisher key; envelope signer does not match the pinned publisher key | `src/oak/interfaces/cli/validate.py:267` |
| `OAK-VALIDATE-WEBHOOK-SIGNATURE` | envelope signature does not verify under the pinned publisher key | `src/oak/interfaces/cli/validate.py:291` |

### Durable operations and the outbox (26)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-OPERATION-ATTEMPTS` | operation attempts must be between 1 and 10 | `src/oak/adapters/persistence/operations.py:552` |
| `OAK-OPERATION-ATTEMPTS-EXHAUSTED` | *reason or mapping code; carries no fixed message* | `src/oak/adapters/persistence/operations.py:436` |
| `OAK-OPERATION-CANCELLED` | the remote operation was cancelled | `src/oak/interfaces/cli/remote.py:462` |
| `OAK-OPERATION-CONFLICT` | operation identity already exists | `src/oak/adapters/persistence/operations.py:103` |
| `OAK-OPERATION-CORRUPT` | operation request is not an object | `src/oak/adapters/persistence/operations.py:498` |
| `OAK-OPERATION-DOCUMENT` | operation candidate is invalid; operation consent is invalid; operation document is invalid; and 2 more (some dynamic) | `src/oak/adapters/persistence/operations.py:563` |
| `OAK-OPERATION-ERROR-CODE` | operation error code is invalid | `src/oak/adapters/persistence/operations.py:570` |
| `OAK-OPERATION-FAILED` | the remote operation failed | `src/oak/application/operations.py:199` |
| `OAK-OPERATION-KIND` | operation kind is not supported | `src/oak/application/control_plane.py:681` |
| `OAK-OPERATION-LEASE` | heartbeat lease must extend into the future; operation lease must expire after claim time | `src/oak/adapters/persistence/operations.py:188` |
| `OAK-OPERATION-LEASE-LOST` | operation lease is no longer current | `src/oak/adapters/persistence/operations.py:472` |
| `OAK-OPERATION-NOT-CANCELLING` | operation has no cancellation request | `src/oak/adapters/persistence/operations.py:401` |
| `OAK-OPERATION-NOT-FOUND` | operation was not found | `src/oak/adapters/persistence/operations.py:483` |
| `OAK-OPERATION-SCOPE` | operation workspace does not match its case | `src/oak/application/control_plane.py:663` |
| `OAK-OPERATION-SIZE` | *dynamic message* | `src/oak/adapters/persistence/operations.py:565` |
| `OAK-OPERATION-UNSAFE-FIELD` | operation request contains a prohibited execution field | `src/oak/application/operations.py:135` |
| `OAK-OUTBOX-CONSUMER-FAILED` | *reason or mapping code; carries no fixed message* | `src/oak/application/operations.py:272` |
| `OAK-OUTBOX-CORRUPT` | outbox payload is not an object | `src/oak/adapters/persistence/outbox.py:281` |
| `OAK-OUTBOX-ERROR-CODE` | outbox error code is invalid | `src/oak/adapters/persistence/outbox.py:123` |
| `OAK-OUTBOX-LEASE` | outbox lease must expire after claim time | `src/oak/adapters/persistence/outbox.py:48` |
| `OAK-OUTBOX-LEASE-LOST` | outbox delivery lease is no longer current | `src/oak/adapters/persistence/outbox.py:110` |
| `OAK-OUTBOX-LIMIT` | outbox claim limit must be between 1 and 100 | `src/oak/adapters/persistence/outbox.py:44` |
| `OAK-OUTBOX-UNAVAILABLE` | outbox observation is unavailable | `src/oak/application/control_plane.py:632` |
| `OAK-PROJECTION-NAME` | projection name is invalid | `src/oak/adapters/persistence/outbox.py:152` |
| `OAK-WORKER-CONFIG` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/worker.py:108` |
| `OAK-WORKER-CYCLE` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/worker.py:65` |

### Model provider and interpretation proposals (38)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-INTERPRETER-` | *reason or mapping code; carries no fixed message* | `src/oak/adapters/models/report_narrator.py:202` |
| `OAK-INTERPRETER-INPUT-LIMIT` | proposal input exceeds its limit | `src/oak/adapters/models/fake_interpreter.py:28` |
| `OAK-INTERPRETER-MALFORMED` | optional interpreter returned no proposal; optional proposal failed validation; optional proposal is not canonical JSON data; and 6 more | `src/oak/adapters/models/fake_interpreter.py:36` |
| `OAK-INTERPRETER-MODE` | interpreter must be deterministic, online or local | `src/oak/application/design_case.py:279` |
| `OAK-INTERPRETER-OUTPUT-LIMIT` | proposal output exceeds its limit; provider response exceeds its size limit; the model's answer was truncated | `src/oak/adapters/models/huggingface_catalogue.py:97` |
| `OAK-INTERPRETER-SOURCE` | optional proposal is not bound to the requested source record; the source record carries no artifact reference | `src/oak/adapters/models/hosted_interpreter.py:202` |
| `OAK-INTERPRETER-UNAVAILABLE` | optional interpretation provider is unavailable; the TLS handshake with the provider failed; the provider could not be reached or answered with an unusable response; and 2 more (some dynamic) | `src/oak/adapters/models/fake_interpreter.py:30` |
| `OAK-MODEL-` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/cli/main.py:213` |
| `OAK-MODEL-ACTION` | models action is not recognized | `src/oak/interfaces/cli/main.py:2194` |
| `OAK-MODEL-CONFIGURATION-FILE` | *reason or mapping code; carries no fixed message* | `src/oak/adapters/credentials/configuration_store.py:17` |
| `OAK-MODEL-CREDENTIAL-SOURCE` | --store must be auto, keychain, file, or env; the credential source must be keychain, file, or env; this family has no documented environment variable; store the key in the keychain or file backend instead (some dynamic) | `src/oak/adapters/credentials/environment_reference.py:24` |
| `OAK-MODEL-DISCOVERY-UNAVAILABLE` | model discovery is not available in this build; select a model identifier directly; the Hugging Face catalogue did not answer within its deadline; the provider's model list could not be read (some dynamic) | `src/oak/adapters/models/huggingface_catalogue.py:133` |
| `OAK-MODEL-EGRESS-DENIED` | only https is spoken to a provider (plain http only to a loopback address); the request destination is not on the provider's fixed host allowlist | `src/oak/adapters/models/research_sources.py:222` |
| `OAK-MODEL-ENDPOINT-INVALID` | OAK_MODEL_ENDPOINT_LOCAL is not a usable URL; OAK_MODEL_ENDPOINT_LOCAL must be an http(s) URL on a loopback address (for example http://127.0.0.1:11434/v1) with no credentials in it | `src/oak/adapters/models/providers.py:229` |
| `OAK-MODEL-FAMILY-REQUIRED` | *dynamic message* | `src/oak/interfaces/cli/main.py:2196` |
| `OAK-MODEL-FAMILY-UNKNOWN` | *dynamic message* | `src/oak/adapters/models/providers.py:271` |
| `OAK-MODEL-ID` | a Hugging Face model identifier carries no `:` suffix; pin the provider route with --provider instead; a model identifier must be 1 to 256 characters; models select requires a model identifier | `src/oak/application/model_configuration.py:618` |
| `OAK-MODEL-KEY-INPUT` | a provider key must be printable ASCII with no spaces or control characters; no terminal to prompt on; pipe the key with --stdin (it is never accepted as an argument); read no usable key from standard input (some dynamic) | `src/oak/adapters/credentials/environment_reference.py:42` |
| `OAK-MODEL-KEY-INVALID` | *dynamic message* | `src/oak/adapters/models/transport.py:232` |
| `OAK-MODEL-KEY-MISSING` | *dynamic message* | `src/oak/adapters/credentials/environment_reference.py:36` |
| `OAK-MODEL-KEY-PERMISSIONS` | *reason or mapping code; carries no fixed message* | `src/oak/adapters/credentials/file_store.py:18` |
| `OAK-MODEL-KEY-REJECTED` | *dynamic message* | `src/oak/adapters/models/providers.py:695` |
| `OAK-MODEL-KEY-SCOPE` | the Hugging Face token lacks the 'Make calls to Inference Providers' permission; create a fine-grained token with that permission and store it with `oak models set-key huggingface` | `src/oak/adapters/models/providers.py:704` |
| `OAK-MODEL-KEYCHAIN-` | *reason or mapping code; carries no fixed message* | `src/oak/application/model_configuration.py:495` |
| `OAK-MODEL-KEYCHAIN-UNAVAILABLE` | *reason or mapping code; carries no fixed message* | `src/oak/adapters/credentials/keychain_store.py:23` |
| `OAK-MODEL-KEYCHAIN-UNSAFE` | *reason or mapping code; carries no fixed message* | `src/oak/adapters/credentials/keychain_store.py:24` |
| `OAK-MODEL-NOT-AVAILABLE` | the selected model is gated for this account; accept its licence on the Hugging Face model page or run `oak models discover huggingface` and select an ungated model (some dynamic) | `src/oak/adapters/models/providers.py:711` |
| `OAK-MODEL-NOT-CONFIGURED` | *dynamic message* | `src/oak/application/design_case.py:298` |
| `OAK-MODEL-POLICY` | provider policy must be cheapest or fastest | `src/oak/application/model_configuration.py:684` |
| `OAK-MODEL-QUOTA-EXHAUSTED` | *dynamic message* | `src/oak/adapters/models/providers.py:739` |
| `OAK-MODEL-RATE-LIMITED` | *dynamic message* | `src/oak/adapters/models/hosted_interpreter.py:286` |
| `OAK-MODEL-REQUEST-REJECTED` | *dynamic message* | `src/oak/adapters/models/providers.py:776` |
| `OAK-MODEL-ROUTE` | a provider route is meaningful only for Hugging Face (some dynamic) | `src/oak/application/model_configuration.py:626` |
| `OAK-MODEL-ROUTE-UNAVAILABLE` | this provider route is not available for pay-as-you-go on the Hugging Face account; pick another with `oak models select huggingface <model_id> --provider <route>`, or `oak models clear huggingface` for the preferred pair | `src/oak/adapters/models/providers.py:726` |
| `OAK-MODEL-TOKEN-FILE` | *reason or mapping code; carries no fixed message* | `src/oak/adapters/credentials/api_token.py:19` |
| `OAK-MODEL-TOKEN-MISSING` | no model-configuration token exists; start `oak serve` or `oak-api` first | `src/oak/interfaces/cli/main.py:2174` |
| `OAK-MODEL-TOKEN-REQUIRED` | the X-OAK-Model-Token header does not match the token this server minted; run `oak models token` to read the current one; this operation requires the X-OAK-Model-Token header; run `oak models token` to read the token this server minted | `src/oak/interfaces/api/app.py:378` |
| `OAK-MODEL-VERIFICATION-UNAVAILABLE` | credential verification is not available in this build; the verdict is not recognised; the verification method is not recognised | `src/oak/application/model_configuration.py:520` |

### Request host and origin guard (2)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-HOST-DENIED` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/api/app.py:314` |
| `OAK-ORIGIN-DENIED` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/api/app.py:326` |

### Concurrency, identity and requests (11)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-ACTOR-DENIED` | local actor is not authorized | `src/oak/interfaces/api/app.py:119` |
| `OAK-CORRELATION-ID` | correlation ID must contain at least 8 characters; correlation id must contain at least 8 characters | `src/oak/application/candidate_planning.py:829` |
| `OAK-DIRECTORY-UNAVAILABLE` | design-case directory is unavailable | `src/oak/application/control_plane.py:190` |
| `OAK-EXPECTED-VERSION` | expected case version does not match current version (some dynamic) | `src/oak/adapters/persistence/file_workspace.py:526` |
| `OAK-IDEMPOTENCY-CONFLICT` | idempotency key was already used for different input; idempotency key was already used for different operation input; import destination contains different canonical state | `src/oak/adapters/persistence/file_workspace.py:232` |
| `OAK-IDEMPOTENCY-KEY` | cancellation idempotency key is invalid; idempotency key is required; idempotency key must contain 16 to 240 characters; and 2 more | `src/oak/adapters/persistence/operations.py:147` |
| `OAK-PRECONDITION-INVALID` | expected version is required; weak entity tags are not accepted | `src/oak/interfaces/api/app.py:419` |
| `OAK-REQUEST-INVALID` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/api/app.py:694` |
| `OAK-REQUEST-SIZE` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/api/app.py:191` |
| `OAK-TENANT-MISMATCH` | repository scope does not match workspace initialization; requested resource was not found; workspace tenant does not match command | `src/oak/adapters/persistence/postgresql.py:114` |
| `OAK-TIME-INVALID` | timestamp must include a timezone; worker timestamp must include a timezone | `src/oak/adapters/persistence/postgresql.py:972` |

### Configuration and process startup (3)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-DATABASE-CONFIG` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/migrations.py:25` |
| `OAK-DATABASE-MIGRATION` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/migrations.py:36` |
| `OAK-DATABASE-UNCONFIGURED` | this server has no database configured; set OAK_DATABASE_URL to the PostgreSQL database that holds the design cases, then restart it | `src/oak/interfaces/api/app.py:479` |

### Everything else (63)

| Code | Meaning | First raise site |
|---|---|---|
| `OAK-ARCHITECTURE-UNSELECTED` | *dynamic message* | `src/oak/application/architecture.py:36` |
| `OAK-AUDIT-LINEAGE` | audit event does not extend the current head; audit event result does not match its case; audit result does not match its event; and 10 more | `src/oak/adapters/persistence/file_workspace.py:424` |
| `OAK-AUDIT-SEQUENCE` | audit event sequence is not contiguous | `src/oak/adapters/persistence/file_workspace.py:421` |
| `OAK-CONFIRM` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/cli/main.py:2490` |
| `OAK-CONTRACT-INVALID` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/api/app.py:677` |
| `OAK-CURSOR-INVALID` | pagination cursor is invalid | `src/oak/interfaces/api/app.py:442` |
| `OAK-DEPENDENCY-MISSING` | case has no recorded policy decision; rendering requires a compiled bundle; rendering requires a semantic manifest; and 2 more (some dynamic) | `src/oak/application/candidate_planning.py:807` |
| `OAK-HTTP-ERROR` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/api/app.py:708` |
| `OAK-INPUT-INVALID` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/cli/main.py:2650` |
| `OAK-INT-CONTRADICTION-PRODUCTION-DATA` | *reason or mapping code; carries no fixed message* | `src/oak/compiler/interpretation.py:586` |
| `OAK-INT-INFEASIBLE-CAPACITY` | *reason or mapping code; carries no fixed message* | `src/oak/compiler/interpretation.py:602` |
| `OAK-INT-MISSING-CRITICAL` | *reason or mapping code; carries no fixed message* | `src/oak/compiler/interpretation.py:564` |
| `OAK-INT-PROPOSAL-REJECTED` | *reason or mapping code; carries no fixed message* | `src/oak/compiler/interpretation.py:50` |
| `OAK-INT-PROPOSAL-UNANSWERED` | *reason or mapping code; carries no fixed message* | `src/oak/compiler/interpretation.py:51` |
| `OAK-INT-UNKNOWN-DECLARED` | *reason or mapping code; carries no fixed message* | `src/oak/compiler/interpretation.py:498` |
| `OAK-INTAKE` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/cli/main.py:327` |
| `OAK-INTERNAL` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/api/app.py:731` |
| `OAK-INTERPRET-BRIEF-TYPE` | brief unknowns must be a string array (some dynamic) | `src/oak/compiler/interpretation.py:477` |
| `OAK-INTERPRET-STATE` | only a draft case can be interpreted | `src/oak/application/design_case.py:322` |
| `OAK-JOURNAL-ENTRY` | journal entry type is not recognized | `src/oak/runner/journal.py:59` |
| `OAK-JOURNAL-TAMPERED` | journal hash chain does not verify (some dynamic) | `src/oak/runner/journal.py:103` |
| `OAK-LOG-CONFIG` | OAK_LOG_LEVEL must be DEBUG, INFO, WARNING or ERROR | `src/oak/interfaces/logs.py:103` |
| `OAK-NARRATIVE-` | *reason or mapping code; carries no fixed message* | `src/oak/adapters/models/report_narrator.py:203` |
| `OAK-NARRATIVE-EMPTY` | none of the model's notes passed OAK's checks, so nothing was recorded; record again or use --narrative deterministic | `src/oak/application/report/service.py:239` |
| `OAK-NARRATIVE-INPUT-LIMIT` | the report is too long to narrate | `src/oak/adapters/models/report_narrator.py:112` |
| `OAK-NARRATIVE-MALFORMED` | the model's answer was longer than allowed; the model's answer was not the requested JSON; the narrator did not name its model | `src/oak/adapters/models/report_narrator.py:121` |
| `OAK-NARRATIVE-MODE` | narrative must be deterministic, online or local | `src/oak/application/report/service.py:114` |
| `OAK-NARRATIVE-UNAVAILABLE` | the provider did not answer; the provider did not answer within the request deadline | `src/oak/adapters/models/fake_narrator.py:33` |
| `OAK-NOT-FOUND` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/api/app.py:708` |
| `OAK-OBSERVE-DUPLICATE` | no runner result has arrived since the last observation record | `src/oak/application/release.py:680` |
| `OAK-OBSERVE-EVIDENCE` | the case holds no accepted runner result | `src/oak/application/release.py:673` |
| `OAK-OBSERVE-STATE` | observation requires an installed case; ingest a successful install first | `src/oak/application/release.py:663` |
| `OAK-OUTPUT-EXISTS` | GitOps output directory already exists; output directory already exists; render output directory already exists | `src/oak/application/gitops.py:38` |
| `OAK-REPORT-MISSING` | no report is recorded for this case; run `oak report --record` first | `src/oak/interfaces/cli/main.py:1742` |
| `OAK-REPORT-OUTPUT` | --output names a directory; give a file name; a PDF needs --output <file>; the directory --output names does not exist (some dynamic) | `src/oak/interfaces/cli/main.py:1444` |
| `OAK-REPORT-RENDER` | no PDF report renderer is configured; the report document could not be drawn; this renderer writes PDF only | `src/oak/adapters/report/pdf.py:1172` |
| `OAK-REPORT-SIZE` | the rendered report exceeds 4 MiB | `src/oak/adapters/report/pdf.py:1178` |
| `OAK-REPORT-STATE` | *dynamic message* | `src/oak/application/report/service.py:156` |
| `OAK-RESEARCH-BUDGET` | *reason or mapping code; carries no fixed message* | `src/oak/adapters/models/research_sources.py:175` |
| `OAK-RESEARCH-CONSENT` | the consent does not name the hosts and terms this research would send; read the plan again and consent to what it shows; the research source changed since the plan | `src/oak/application/research.py:157` |
| `OAK-RESEARCH-FIXTURE` | a research fixture exceeds its size limit; a research fixture is not a regular file | `src/oak/adapters/models/research_fixture.py:103` |
| `OAK-RESEARCH-ITEM-STATE` | only an item that needs a review can be reviewed; a passed or failed item keeps the verdict the gates gave it; this item is already reviewed against this research snapshot; one decision is recorded per item per run, so run research again to review it afresh | `src/oak/application/research.py:330` |
| `OAK-RESEARCH-ITEM-UNKNOWN` | the snapshot holds no such item | `src/oak/application/research.py:328` |
| `OAK-RESEARCH-MISSING` | the case holds no research snapshot; the case holds no research snapshot to review | `src/oak/application/research.py:324` |
| `OAK-RESEARCH-OVERSIZED` | *reason or mapping code; carries no fixed message* | `src/oak/adapters/models/research_sources.py:226` |
| `OAK-RESEARCH-RATE-LIMITED` | *reason or mapping code; carries no fixed message* | `src/oak/adapters/models/research_sources.py:240` |
| `OAK-RESEARCH-REDIRECTED` | *reason or mapping code; carries no fixed message* | `src/oak/adapters/models/research_sources.py:219` |
| `OAK-RESEARCH-REVIEW-DECISION` | a review is accept or reject | `src/oak/application/research.py:277` |
| `OAK-RESEARCH-REVIEW-RATIONALE` | a rationale must not hold a control or formatting character; a review needs a rationale | `src/oak/application/research.py:279` |
| `OAK-RESEARCH-REVIEW-SIZE` | *dynamic message* | `src/oak/application/research.py:287` |
| `OAK-RESEARCH-REVIEW-STATE` | a research item is reviewed only while the case is ready for candidates | `src/oak/application/research.py:312` |
| `OAK-RESEARCH-STATE` | research needs an interpreted case; this case has no intent yet; research runs only while the case is ready for candidates; once candidates exist the recorded design is kept as it is; the case holds no interpreted intent yet | `src/oak/application/research.py:123` |
| `OAK-RESEARCH-UNAVAILABLE` | research is not configured on this server | `src/oak/application/control_plane.py:755` |
| `OAK-RESEARCH-UNREACHABLE` | *reason or mapping code; carries no fixed message* | `src/oak/adapters/models/research_sources.py:197` |
| `OAK-RESEARCH-USAGE` | a review needs --rationale-file <file>; use exactly one of --accept or --reject; use exactly one of --plan or --consent <digest> | `src/oak/interfaces/cli/main.py:1561` |
| `OAK-RESEARCH-VOCABULARY` | freshness window must be 1 to 365 days; hardware classes have no fallback; no research binding yields a capability; and 8 more (some dynamic) | `src/oak/adapters/catalogue/research_vocabulary.py:50` |
| `OAK-REVOCATION-CHANNEL` | the mailbox's revocation manifest is not one this control plane signed; restore the mailbox's revocations directory before publishing again | `src/oak/application/release.py:979` |
| `OAK-REVOCATION-REASON` | revocation requires a reason | `src/oak/application/release.py:292` |
| `OAK-SAFE-BIND` | *reason or mapping code; carries no fixed message* | `src/oak/interfaces/api/server.py:120` |
| `OAK-SIGNING-KEY-INVALID` | signing key length is invalid; signing key must be a regular file | `src/oak/adapters/signing/local_ed25519.py:181` |
| `OAK-SIGNING-KEY-MISSING` | signing key does not exist; run oak keys init | `src/oak/adapters/signing/local_ed25519.py:176` |
| `OAK-SIGNING-KEY-PERMISSIONS` | signing key must not be group or world accessible | `src/oak/adapters/signing/local_ed25519.py:183` |
| `OAK-SIGNING-ROLE` | signing role is not recognized | `src/oak/adapters/signing/local_ed25519.py:205` |

