<!-- SPDX-License-Identifier: Apache-2.0 -->

# Threat-model coverage index — OAK Community 0.7.0

Which tests exercise which threat, and — more usefully — which threats nothing exercises.

The governance threat model defines nineteen threats, `TM-01` to `TM-19`. Before this
release nothing connected them to the test suite: the string `TM-` appeared in three
completed sprint plans and in **zero** test files, so coverage was rediscovered by hand
every sprint and a renamed or deleted test dropped a threat silently.

## How to read this

- **direct** — a test asserts the mitigation or the denial for this threat.
- **partial** — some aspect is covered and the gap is named explicitly.
- **structural** — the threat is defended by the *absence* of a surface, not by a control.
  Where a test can prove the absence, it now does.
- **none** — nothing covers it.

Verdict tally: **8 direct, 9 partial, 2 structural, 0 none.**

Every test function cited below was verified to exist in the tree at the time of writing;
a citation to a test that does not exist would make this document worse than nothing. The
line number after each threat is its row in the governance `docs/threat-model.md`.

**This index is not an audit.** It records what the project tested itself. No external
security review was commissioned for this release (`RR-028`).

## Coverage

| ID | Threat | Verdict | Evidence |
|---|---|---|---|
| TM-01 | Prompt injection makes OAK choose tools, leak secrets or bypass policy (58) | **direct** | `tests/integration/test_mcp_abuse.py::test_prompt_injection_in_brief_content_is_stored_as_inert_data`, `::test_privileged_tool_names_do_not_exist`, `::test_non_tool_methods_cannot_be_reached`; `tests/unit/test_intake.py::test_prompt_injection_text_remains_inert_untrusted_brief_content`; `tests/unit/test_interpretation.py::test_prompt_injection_is_copied_as_a_claim_and_cannot_change_interpreter_behavior` |
| TM-02 | Poisoned component metadata recommends an attacker-controlled image (59) | **partial** | `tests/unit/test_candidate_compiler.py::test_ineligible_manifest_cannot_produce_a_feasible_candidate`, `::test_stale_or_restricted_manifest_is_not_eligible`; digest pin at `tests/unit/test_runner_trust.py::test_image_reference_carrying_its_own_digest_is_refused`. **No test for signature/provenance/SBOM gating — and no such gate exists** (`src/oak/compiler/catalogue.py:131-154`) |
| TM-03 | Malicious policy pack weakens a legal/security rule (60) | **direct** | `tests/integration/test_extension_service.py::test_unsigned_extension_stays_quarantined`, `::test_wrong_key_signature_is_not_a_pinned_anchor`, `::test_tampered_payload_fails_digest_verification`, `::test_poisoned_pack_test_expectations_fail`, `::test_expired_pack_payload_cannot_activate`; `tests/integration/test_policy_service.py::test_stale_or_inactive_packs_refuse_evaluation` |
| TM-04 | LLM confidently invents hardware fit, licence or legal conclusion (61) | **direct** | `tests/unit/test_interpretation.py::test_optional_provider_outage_and_malformed_output_fail_explicitly`, `::test_missing_scalar_provenance_fails_closed`, `::test_optional_proposal_output_limit_is_enforced`; `tests/integration/test_design_case_service.py::test_optional_proposal_is_read_only_and_provider_failure_adds_no_event` |
| TM-05 | Optimizer manipulates weights or hides dominated alternatives (62) | **partial** | `tests/unit/test_candidate_compiler.py::test_catalogue_snapshot_and_candidates_ignore_input_order`, `::test_candidate_set_includes_baseline_variants_and_excludes_unknown_from_frontier`. **No test tampers with a weight or objective contract; no sensitivity or predicted-vs-observed test** |
| TM-06 | Approval replayed for a changed bundle or wrong target (63) | **direct** | `tests/integration/test_signed_runner.py::test_replayed_lease_nonce_is_denied`, `::test_wrong_target_fingerprint_is_denied`, `::test_expired_lease_is_denied`, `::test_revoked_approval_is_denied`, `::test_tampered_plan_is_denied_before_execution`, `::test_untrusted_signer_is_denied` |
| TM-07 | Runner compromise exposes cross-tenant credentials (64) | **partial** | `tests/unit/test_runner_adapters.py::test_inventory_is_bounded_and_secret_free`; `tests/e2e/test_runner_journey.py::test_signed_apply_and_rollback_touch_only_the_fixture_container`, `tests/e2e/test_cli.py::test_runner_requires_explicit_environment`. **No test asserts the runner holds no control-plane DB credential; no workspace-zeroize test; single local tenant means cross-tenant has no surface** |
| TM-08 | Time-of-check/time-of-use substitution at deployment (65) | **direct** | `tests/unit/test_runner_trust.py::test_approved_digest_is_always_the_pin`, `::test_image_reference_carrying_its_own_digest_is_refused`; `tests/unit/test_runner_adapters.py::test_renderer_pins_images_to_the_attested_digest_not_the_reference`; `tests/integration/test_validate_cli.py::test_a_real_bundle_validates_and_tampering_is_refused` |
| TM-09 | Partial deployment leaves unsafe mixed versions (66) | **direct** | `tests/unit/test_runner_journal.py::test_incomplete_operation_is_detected_on_resume`, `::test_manual_recovery_state_sticks`, `::test_chain_verifies_and_detects_tampering`; `tests/integration/test_signed_runner.py::test_mutating_dispatch_applies_and_rolls_back`; `tests/integration/test_operations.py::test_expired_final_attempt_is_swept_to_safe_failure` |
| TM-10 | Tenant data leaks through caches, logs, prompts, embeddings or global learning (67) | **partial** | `tests/integration/test_mcp_abuse.py::test_tenant_crossover_is_an_opaque_denial`; `tests/unit/test_mcp_server.py::test_foreign_tenant_receives_an_opaque_denial_without_dispatch`; `tests/integration/test_design_case_service.py::test_idempotent_result_is_not_returned_across_tenant_or_actor_context`; `tests/integration/test_api.py::test_outbox_lag_is_observable_without_exposing_event_payloads`. **Explicitly not multi-tenant evidence per security-invariants.md:98** |
| TM-11 | Telemetry or feedback poisoned to induce a bad self-improvement (68) | **structural** | No self-improvement or aggregation loop exists in Community. Nearest surface is `ingest_runner_messages` (`src/oak/application/release.py:428-455`), whose deny branches have **no adversarial test** — only the happy path at `tests/e2e/test_runner_journey.py:91` asserts `rejected == []` |
| TM-12 | Audit administrator edits or deletes incriminating history (69) | **partial** | `tests/integration/test_file_workspace.py::test_import_rejects_audit_idempotency_tampering_and_symlinked_store`, `::test_corrupted_content_addressed_object_is_rejected`; `tests/unit/test_runner_journal.py::test_chain_verifies_and_detects_tampering`. **No restricted-writer / separation-of-duties control exists, so none is tested; no external integrity checkpoint** |
| TM-13 | Model or document input exfiltrates confidential data to a provider (70) | **structural** | No real provider adapter ships in Community — `src/oak/adapters/models/fake_interpreter.py` is the only `ModelInterpreterPort` implementation, and the only outbound HTTP in `src/` is the remote CLI to OAK's own API (`src/oak/interfaces/cli/remote.py:23,96,103`). Egress surface does not exist |
| TM-14 | Unbounded architecture search or inference exhausts budget (71) | **partial** | `tests/integration/test_mcp_abuse.py::test_oversized_content_argument_is_refused_by_the_schema`, `::test_unbounded_line_cannot_exhaust_memory_before_the_limit`; `tests/integration/test_api.py::test_chunked_or_sized_request_body_is_bounded`; `tests/integration/test_operations.py::test_operation_lease_expiry_retry_backoff_and_terminal_failure`. **No per-job cost/token budget, tenant quota or rate limiter exists in `src/`** |
| TM-15 | Dependency vulnerability compromises build or runtime (72) | **partial** | `tests/contract/test_toolchain_contract.py::test_ci_uv_drift_is_rejected`, `::test_repository_toolchain_declarations_agree`; `tests/integration/test_release_verification.py::test_a_tampered_artifact_is_refused`. **`OAK-CAT-KNOWN-VULNERABILITY` and every licence-gate reason are untested; SBOM generation has no test** |
| TM-16 | Confused deputy lets a low-privilege user deploy through OAK's identity (73) | **direct** | `tests/integration/test_mcp_abuse.py::test_actor_impersonation_is_denied_before_dispatch`, `::test_confirm_actor_field_cannot_escalate_beyond_the_bound_identity`; `tests/integration/test_signed_runner.py::test_mutating_dispatch_without_apply_approval_is_denied`; `tests/integration/test_candidate_planning_service.py:141` (`OAK-TARGET-CAPABILITY`) |
| TM-17 | Legal-source outage or scraping error yields false "current" policy (74) | **partial** | `tests/integration/test_policy_service.py::test_expired_pack_refuses_even_for_a_previously_evaluated_request`, `::test_stale_or_inactive_packs_refuse_evaluation`. **Stale-pack half tested; outage half has no surface (no legal-source fetch). Refusal is an `OAKError`, not a `review_required` decision** |
| TM-18 | Malicious blueprint includes covert external calls/telemetry (75) | **direct** | `tests/contract/test_runner_contracts.py::test_no_committed_schema_permits_execution_fields`; `tests/integration/test_validate_cli.py::test_an_injected_execution_field_is_refused`, `::test_an_execution_field_in_a_webhook_envelope_is_refused`, `::test_an_execution_field_in_an_export_object_is_refused`; `tests/integration/test_deployment_render.py::test_kubernetes_render_is_pinned_inert_and_egress_free` |
| TM-19 | OAK becomes a production-content proxy or hidden runtime dependency (76) | **partial** | `tests/e2e/test_cli.py::test_offline_design_confirmation_retry_and_portable_round_trip`, `::test_offline_candidate_to_plan_flow_is_semantically_reproducible`; `tests/integration/test_gitops_output.py::test_patch_description_states_promotion_is_manual`; `tests/unit/test_server_safety.py::test_non_loopback_bind_fails_closed`. **Nothing asserts the rendered system contains no reference to OAK at runtime** |
| TM-13 | No model/evidence provider adapter ships. `FakeModelInterpreter` is the only `ModelInterpreterPort` implementation; the only outbound HTTP in `src/` is the remote CLI to OAK's own API. There is no provider to exfiltrate to. |
| TM-11 | No self-improvement, aggregation or global-learning loop exists. There is no mechanism a poisoned observation could bias. |
## Threats defended by absence

`TM-11` (poisoned telemetry driving a bad self-improvement) and `TM-13` (exfiltration to a
model or document provider) are marked **structural** because the surfaces do not exist in
Community: there is no self-improvement or aggregation loop, and no real provider adapter
ships. That is a legitimate position, but an absence can be undone by a single commit, so
two of the three absences are now enforced rather than described:

- `tests/integration/test_offline_boundary.py::test_only_the_remote_cli_may_import_a_network_client`
  parses every module under `src/oak` and fails if any but the remote CLI imports a network
  client.
- `::test_no_model_or_evidence_provider_adapter_ships` fails if any implementation other
  than the deterministic fake appears under `src/oak/adapters/models`.
- `::test_the_reference_journey_completes_with_every_outbound_socket_broken` runs the whole
  brief-to-dispatch journey with `socket.connect`, `socket.create_connection` and
  `socket.getaddrinfo` patched to raise, and
  `::test_the_egress_guard_itself_actually_blocks` proves the guard is not vacuous.

`TM-11` has no equivalent enforcement, because there is nothing to enforce against. Its
nearest surface, `ingest_runner_messages`, has covered deny branches only through the happy
path; that gap is recorded rather than papered over.

## Named gaps

These are the specific things the table calls "partial". Each is in the residual-risk
register with an id.

| Threat | Gap | Register |
|---|---|---|
| TM-02 | No signature, provenance or SBOM gate on catalogue component manifests | `RR-025` |
| TM-05 | No test tampers with an objective weight; no sensitivity or predicted-versus-observed test | — |
| TM-07 | No test asserts the runner holds no control-plane credential; no workspace zeroization | `RR-027` |
| TM-10 | Single local tenant; not multi-tenant evidence | `RR-026` |
| TM-12 | No restricted-writer or separation-of-duties control exists, so none is tested | — |
| TM-14 | No per-job budget, tenant quota or rate limiter | `RR-024` |
| TM-15 | Catalogue vulnerability and licence gate reasons are untested; SBOM generation had no test | `RR-025` |
| TM-17 | Stale-pack refusal is an `OAKError`, not a `review_required` decision; no legal-source fetch exists to fail | — |
| TM-19 | Nothing asserts a rendered system contains no runtime reference to OAK | — |

## What changed in this release

`TM-10` (tenant data through logs) had a live instance, now fixed: canonical documents are
bound as SQLAlchemy statement parameters, and the default `hide_parameters=False` put brief
text into `StatementError` messages that uvicorn's error logger wrote to stderr — which
under Compose is the container log. The same review found the MCP and canonical validation
diagnostics echoing rejected values. Both are fixed and pinned by
`tests/unit/test_diagnostic_confidentiality.py`.

`TM-13` and `TM-19` moved from "defended by a grep" to "defended by a test", as above.
