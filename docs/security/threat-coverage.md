<!-- SPDX-License-Identifier: Apache-2.0 -->

# Threat-model coverage index — OAK Community 0.7.1 (updated for Sprint 9)

Which tests exercise which threat, and — more usefully — which threats nothing exercises.

The governance threat model defines twenty threats, `TM-01` to `TM-20`; `TM-20` is new in
Sprint 9, with the optional model provider that made it reachable. Before this
release nothing connected them to the test suite: the string `TM-` appeared in three
completed sprint plans and in **zero** test files, so coverage was rediscovered by hand
every sprint and a renamed or deleted test dropped a threat silently.

## How to read this

- **direct** — a test asserts the mitigation or the denial for this threat.
- **partial** — some aspect is covered and the gap is named explicitly.
- **structural** — the threat is defended by the *absence* of a surface, not by a control.
  Where a test can prove the absence, it now does.
- **none** — nothing covers it.

Verdict tally: **10 direct, 9 partial, 1 structural, 0 none.**

Every test function cited below was verified to exist in the tree at the time of writing;
a citation to a test that does not exist would make this document worse than nothing. The
line number after each threat is its row in the governance `docs/threat-model.md`.

**This index is not an audit.** It records what the project tested itself. No external
security review was commissioned for this release (`RR-028`).

## Coverage

| ID | Threat | Verdict | Evidence |
|---|---|---|---|
| TM-01 | Prompt injection makes OAK choose tools, leak secrets or bypass policy (58) | **direct** | `tests/integration/test_mcp_abuse.py::test_prompt_injection_in_brief_content_is_stored_as_inert_data`, `::test_privileged_tool_names_do_not_exist`, `::test_non_tool_methods_cannot_be_reached`; `tests/unit/test_intake.py::test_prompt_injection_text_remains_inert_untrusted_brief_content`; `tests/unit/test_interpretation.py::test_prompt_injection_is_copied_as_a_claim_and_cannot_change_interpreter_behavior`; `tests/unit/test_proposal_merge.py::test_injection_inside_rationale_or_paths_is_inert`, `::test_inadmissible_oversize_and_schema_breaking_claims_are_rejected_not_silent` (a proposal cannot write outside the admissible path set, exceed the value bounds or break the intent schema); `tests/unit/test_hosted_interpreter.py::test_the_system_prompt_states_the_brief_is_untrusted_and_the_brief_is_delimited` |
| TM-02 | Poisoned component metadata recommends an attacker-controlled image (59) | **partial** | `tests/unit/test_candidate_compiler.py::test_ineligible_manifest_cannot_produce_a_feasible_candidate`, `::test_stale_or_restricted_manifest_is_not_eligible`; digest pin at `tests/unit/test_runner_trust.py::test_image_reference_carrying_its_own_digest_is_refused`. **No test for signature/provenance/SBOM gating — and no such gate exists** (`src/oak/compiler/catalogue.py:131-154`) |
| TM-03 | Malicious policy pack weakens a legal/security rule (60) | **direct** | `tests/integration/test_extension_service.py::test_unsigned_extension_stays_quarantined`, `::test_wrong_key_signature_is_not_a_pinned_anchor`, `::test_tampered_payload_fails_digest_verification`, `::test_poisoned_pack_test_expectations_fail`, `::test_expired_pack_payload_cannot_activate`; `tests/integration/test_policy_service.py::test_stale_or_inactive_packs_refuse_evaluation` |
| TM-04 | LLM confidently invents hardware fit, licence or legal conclusion (61) | **direct** | `tests/unit/test_interpretation.py::test_optional_provider_outage_and_malformed_output_fail_explicitly`, `::test_missing_scalar_provenance_fails_closed`, `::test_optional_proposal_output_limit_is_enforced`; `tests/integration/test_design_case_service.py::test_optional_proposal_is_read_only_and_provider_failure_adds_no_event`; and, for the merged path, `tests/unit/test_proposal_merge.py::test_every_section_yields_one_valid_question_even_at_full_confidence` (a model value always produces a confirmation question, at any confidence) and `tests/integration/test_model_interpretation_service.py::test_model_values_keep_the_case_in_confirmation_until_two_rounds_resolve_them` (candidates refuse until every model-proposed value is confirmed, corrected or rejected) |
| TM-05 | Optimizer manipulates weights or hides dominated alternatives (62) | **partial** | `tests/unit/test_candidate_compiler.py::test_catalogue_snapshot_and_candidates_ignore_input_order`, `::test_candidate_set_includes_baseline_variants_and_excludes_unknown_from_frontier`. **No test tampers with a weight or objective contract; no sensitivity or predicted-vs-observed test** |
| TM-06 | Approval replayed for a changed bundle or wrong target (63) | **direct** | `tests/integration/test_signed_runner.py::test_replayed_lease_nonce_is_denied`, `::test_wrong_target_fingerprint_is_denied`, `::test_expired_lease_is_denied`, `::test_revoked_approval_is_denied`, `::test_tampered_plan_is_denied_before_execution`, `::test_untrusted_signer_is_denied`; `tests/integration/test_runner_revocation.py` (notice deletion, whole-set deletion and sequence-rollback denials on the revocation channel the approval binding leans on) |
| TM-07 | Runner compromise exposes cross-tenant credentials (64) | **partial** | `tests/unit/test_runner_adapters.py::test_inventory_is_bounded_and_secret_free`; `tests/e2e/test_runner_journey.py::test_signed_apply_and_rollback_touch_only_the_fixture_container`, `tests/e2e/test_cli.py::test_runner_requires_explicit_environment`. **No test asserts the runner holds no control-plane DB credential; no workspace-zeroize test; single local tenant means cross-tenant has no surface** |
| TM-08 | Time-of-check/time-of-use substitution at deployment (65) | **direct** | `tests/unit/test_runner_trust.py::test_approved_digest_is_always_the_pin`, `::test_image_reference_carrying_its_own_digest_is_refused`; `tests/unit/test_runner_adapters.py::test_apply_removes_the_container_when_the_resolved_digest_differs`, `::test_apply_fails_closed_when_the_image_has_no_repo_digest`, `::test_apply_fails_closed_when_the_inspection_itself_fails`, `::test_renderer_pins_images_to_the_attested_digest_not_the_reference`; `tests/integration/test_signed_runner.py::test_a_disallowed_registry_is_denied_before_any_adapter_exists`; `tests/integration/test_validate_cli.py::test_a_real_bundle_validates_and_tampering_is_refused`. The time-of-use half is enforced since `0.7.1`: the adapter verifies the runtime's resolved `RepoDigests` after `docker create` and removes the container on mismatch, and a target-profile registry allowlist is enforced before any adapter exists (`RR-003`, closed) |
| TM-09 | Partial deployment leaves unsafe mixed versions (66) | **direct** | `tests/unit/test_runner_journal.py::test_incomplete_operation_is_detected_on_resume`, `::test_manual_recovery_state_sticks`, `::test_chain_verifies_and_detects_tampering`; `tests/integration/test_signed_runner.py::test_mutating_dispatch_applies_and_rolls_back`; `tests/integration/test_operations.py::test_expired_final_attempt_is_swept_to_safe_failure` |
| TM-10 | Tenant data leaks through caches, logs, prompts, embeddings or global learning (67) | **partial** | `tests/integration/test_mcp_abuse.py::test_tenant_crossover_is_an_opaque_denial`; `tests/unit/test_mcp_server.py::test_foreign_tenant_receives_an_opaque_denial_without_dispatch`; `tests/integration/test_design_case_service.py::test_idempotent_result_is_not_returned_across_tenant_or_actor_context`; `tests/integration/test_api.py::test_outbox_lag_is_observable_without_exposing_event_payloads`. **Explicitly not multi-tenant evidence per security-invariants.md:98** |
| TM-11 | Telemetry or feedback poisoned to induce a bad self-improvement (68) | **structural** | No self-improvement or aggregation loop exists in Community. Nearest surface is `ingest_runner_messages` (`src/oak/application/release.py:455-491`), whose deny branches have **no adversarial test** — only the happy path at `tests/e2e/test_runner_journey.py:91` asserts `rejected == []` |
| TM-12 | Audit administrator edits or deletes incriminating history (69) | **partial** | `tests/integration/test_file_workspace.py::test_import_rejects_audit_idempotency_tampering_and_symlinked_store`, `::test_corrupted_content_addressed_object_is_rejected`; `tests/unit/test_runner_journal.py::test_chain_verifies_and_detects_tampering`. **No restricted-writer / separation-of-duties control exists, so none is tested; no external integrity checkpoint** |
| TM-13 | Model or document input exfiltrates confidential data to a provider (70) | **direct** | Community can now send a brief to a provider the user configured, so the verdict rests on controls rather than absence. `tests/integration/test_offline_boundary.py::test_the_reference_journey_completes_with_every_outbound_socket_broken` (the deterministic journey needs no network), `::test_the_deterministic_journey_never_imports_a_hosted_model_module` (a fresh interpreter never loads a provider module), `::test_only_the_remote_cli_may_import_a_network_client` and `::test_only_the_transport_among_the_model_adapters_imports_a_network_client` (one module may open a connection), `::test_the_model_adapter_set_is_exactly_the_documented_one` (the egress surface is a listed set, not a glob); `tests/unit/test_model_transport.py` (host allowlist checked before any socket call, https only except loopback, redirects refused and the second listener receives nothing, environment and system proxies ignored, TLS verified, bounded body, deadline enforced); `tests/unit/test_hosted_interpreter.py::test_exactly_one_request_is_sent_for_a_successful_interpretation`, `::test_the_key_is_read_per_call_and_never_stored_on_the_adapter`, `::test_the_recorded_extension_names_the_model_and_digests_without_content`; `tests/unit/test_huggingface_catalogue.py::test_both_catalogue_reads_are_anonymous_public_gets`; since Sprint 10 the only hosted destination is Hugging Face, a request must name `online` or `local` for anything to be sent (`tests/integration/test_model_interpretation_service.py::test_the_default_is_deterministic_and_a_model_mode_must_be_asked_for`), and a token the Hub rejects is refused before any request that could spend (`tests/integration/test_model_preflight.py::test_a_rejected_token_is_refused_before_anything_could_spend`). That a chosen provider then receives the brief is the point of the feature and is recorded as `RR-039`, not defended against |
| TM-14 | Unbounded architecture search or inference exhausts budget (71) | **partial** | `tests/integration/test_mcp_abuse.py::test_oversized_content_argument_is_refused_by_the_schema`, `::test_unbounded_line_cannot_exhaust_memory_before_the_limit`; `tests/integration/test_api.py::test_chunked_or_sized_request_body_is_bounded`; `tests/integration/test_operations.py::test_operation_lease_expiry_retry_backoff_and_terminal_failure`. **No per-job cost/token budget, tenant quota or rate limiter exists in `src/`** (`RR-024`); a model interpretation is individually bounded (one request, one retry, a 55-second ceiling, bounded output) but nothing caps aggregate provider spend (`RR-041`) |
| TM-15 | Dependency vulnerability compromises build or runtime (72) | **partial** | `tests/contract/test_toolchain_contract.py::test_ci_uv_drift_is_rejected`, `::test_repository_toolchain_declarations_agree`; `tests/integration/test_release_verification.py::test_a_tampered_artifact_is_refused`. **`OAK-CAT-KNOWN-VULNERABILITY` and every licence-gate reason are untested; image SBOM/provenance generation is pinned by `tests/contract/test_image_scan_gate.py::test_provenance_records_the_final_stage_base_not_a_build_stage`, `::test_image_sboms_follow_the_distribution_naming_convention` and `::test_image_provenance_is_marked_unsigned_and_unreproducible`** |
| TM-16 | Confused deputy lets a low-privilege user deploy through OAK's identity (73) | **direct** | `tests/integration/test_mcp_abuse.py::test_actor_impersonation_is_denied_before_dispatch`, `::test_confirm_actor_field_cannot_escalate_beyond_the_bound_identity`; `tests/integration/test_signed_runner.py::test_mutating_dispatch_without_apply_approval_is_denied`; `tests/integration/test_candidate_planning_service.py:141` (`OAK-TARGET-CAPABILITY`) |
| TM-17 | Legal-source outage or scraping error yields false "current" policy (74) | **partial** | `tests/integration/test_policy_service.py::test_expired_pack_refuses_even_for_a_previously_evaluated_request`, `::test_stale_or_inactive_packs_refuse_evaluation`. **Stale-pack half tested; outage half has no surface (no legal-source fetch). Refusal is an `OAKError`, not a `review_required` decision** |
| TM-18 | Malicious blueprint includes covert external calls/telemetry (75) | **direct** | `tests/contract/test_runner_contracts.py::test_no_committed_schema_permits_execution_fields`; `tests/integration/test_validate_cli.py::test_an_injected_execution_field_is_refused`, `::test_an_execution_field_in_a_webhook_envelope_is_refused`, `::test_an_execution_field_in_an_export_object_is_refused`; `tests/integration/test_deployment_render.py::test_kubernetes_render_is_pinned_inert_and_egress_free` |
| TM-20 | A local principal reads or spends the operator's stored model-provider credential (76) | **direct** | The credential is stored owner-only and never rendered: `tests/unit/test_credential_store.py` (the `0700` directory and `0600` file, a symlinked or foreign-owned path refused, atomic overwrite, the salted fingerprint, the environment reference storing only a name), `tests/unit/test_secrets.py`-equivalent coverage inside `tests/unit/test_model_configuration.py` (`SecretValue` renders as `<redacted>` in `repr`, `str`, `format`, JSON and logging, and refuses hashing and pickling), `tests/contract/test_secret_shapes.py` (no committed file carries a provider key shape, and the OpenAPI document does not either), `tests/integration/test_models_cli.py::test_set_key_reads_stdin_stores_owner_only_and_echoes_only_a_fingerprint` (the key is never an argument and never printed), `tests/integration/test_models_api.py::test_a_key_is_never_echoed_by_any_response_or_stored_outside_its_directory` and `::test_every_model_route_requires_the_capability_token`, `tests/integration/test_loopback_hardening.py::test_credential_routes_require_a_same_origin_browser_or_a_non_browser_client`, `web/e2e/models.spec.ts` (no response body the browser received carries the key; the volume is owner-only on `api` and empty on `worker`), and — for the verification Sprint 10 added — `tests/unit/test_provider_profiles.py::test_the_hub_whoami_answer_becomes_a_verdict_and_nothing_else` and `tests/unit/test_model_configuration.py::test_verify_records_the_verdict_with_its_time_and_a_new_key_forgets_it` (the Hub's answer is reduced to a typed verdict; the account's name and email are never stored). **What none of this defends against is a process already running as that user**, which is the residual the register records as `RR-040` |
| TM-19 | OAK becomes a production-content proxy or hidden runtime dependency (76) | **partial** | `tests/e2e/test_cli.py::test_offline_design_confirmation_retry_and_portable_round_trip`, `::test_offline_candidate_to_plan_flow_is_semantically_reproducible`; `tests/integration/test_gitops_output.py::test_patch_description_states_promotion_is_manual`; `tests/unit/test_server_safety.py::test_non_loopback_bind_fails_closed`. **Nothing asserts the rendered system contains no reference to OAK at runtime** |
## Threats defended by absence

`TM-11` (poisoned telemetry driving a bad self-improvement) is the one threat still marked
**structural**: there is no self-improvement or aggregation loop in Community to poison.
That is a legitimate position, but an absence can be undone by a single commit, and it has
no equivalent enforcement because there is nothing yet to enforce against. Its nearest
surface, `ingest_runner_messages`, has covered deny branches only through the happy path;
that gap is recorded rather than papered over.

`TM-13` used to sit here too, on the grounds that no provider adapter shipped. Since
Sprint 9 that is no longer true, and the honest claim is narrower: OAK calls a provider
only when a user configures one, only through `oak/adapters/models/transport.py`, only to
that provider's own hosts, and never on the deterministic path. Each clause is a test, and
they are cited in the `TM-13` row above. The tests that carried the old claim were
rewritten rather than deleted:

- the old "no provider adapter ships" assertion became
  `::test_the_model_adapter_set_is_exactly_the_documented_one`, which pins the five model
  modules by name so a sixth cannot appear without a deliberate edit here, and
  `::test_only_the_transport_among_the_model_adapters_imports_a_network_client`, which
  keeps the other four free of any network client.
- `::test_only_the_remote_cli_may_import_a_network_client` still parses every module under
  `src/oak`; its allowlist gained exactly one entry, the transport.
- `::test_the_deterministic_journey_never_imports_a_hosted_model_module` is new: it runs
  the offline journey in a fresh interpreter and fails if a provider module was loaded at
  all, which is the check a grep could never do.
- `::test_the_reference_journey_completes_with_every_outbound_socket_broken` is unchanged
  and runs the brief-through-plan-compilation journey with `socket.connect`,
  `socket.create_connection` and `socket.getaddrinfo` patched to raise, and
  `::test_the_egress_guard_itself_actually_blocks` proves the guard is not vacuous. It ends
  at `bundle_compiled`: signing and dispatch are separate commands and are not covered by
  this particular test, though the AST pin above covers the whole of `src/oak` including
  the runner.

What none of this defends against is the provider itself: once a user selects a hosted
model, that provider receives the brief. That is `RR-039`, an accepted consequence of the
feature, not a gap in it.

## Named gaps

These are the specific things the table calls "partial", plus the one residual a **direct**
verdict still leaves: `TM-20`'s controls stop everything except a process already running as
that user, which no control on this machine can. Each is in the residual-risk register with
an id.

| Threat | Gap | Register |
|---|---|---|
| TM-02 | No signature, provenance or SBOM gate on catalogue component manifests | `RR-025` |
| TM-05 | No test tampers with an objective weight; no sensitivity or predicted-versus-observed test | — |
| TM-07 | No test asserts the runner holds no control-plane credential; no workspace zeroization | `RR-027` |
| TM-10 | Single local tenant; not multi-tenant evidence | `RR-026` |
| TM-12 | No restricted-writer or separation-of-duties control exists, so none is tested | — |
| TM-14 | No per-job budget, tenant quota or rate limiter, including for provider spend | `RR-024`, `RR-041` |
| TM-15 | Catalogue vulnerability and licence gate reasons are untested (image SBOM/provenance generation is now pinned by contract tests) | `RR-025` |
| TM-17 | Stale-pack refusal is an `OAKError`, not a `review_required` decision; no legal-source fetch exists to fail | — |
| TM-19 | Nothing asserts a rendered system contains no runtime reference to OAK | — |
| TM-20 | A same-user process can read the stored key; nothing defends against one | `RR-040` |

## What changed in this release

`TM-10` (tenant data through logs) had a live instance, now fixed: canonical documents are
bound as SQLAlchemy statement parameters, and the default `hide_parameters=False` put brief
text into `StatementError` messages that uvicorn's error logger wrote to stderr — which
under Compose is the container log. The same review found the MCP and canonical validation
diagnostics echoing rejected values. Both are fixed and pinned by
`tests/unit/test_diagnostic_confidentiality.py`.

`TM-13` and `TM-19` moved from "defended by a grep" to "defended by a test", as above.

Since Sprint 9, `TM-13` has moved again — from **structural** to **direct** — because the
surface it describes now exists by design. See the section above for what replaced the
absence claim, and `RR-039` and `RR-041` for what the controls deliberately do not cover.

At `0.7.1`, `TM-08` moved from **partial** to **direct**: the pre-launch hardening closed
`RR-003` (post-create resolved-digest verification plus a target-profile registry
allowlist), closed `RR-001` (signed revocation notices inventoried by a signed,
monotonically sequenced manifest over a fail-closed channel — strengthening the
revocation control TM-02 and TM-06 lean on), and made the compiled verification policy's
clauses enforced rather than carried (`RR-032`), each with adversarial tests cited in the
rows above and in `tests/integration/test_runner_revocation.py`.
