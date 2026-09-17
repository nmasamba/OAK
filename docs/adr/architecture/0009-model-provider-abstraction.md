<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Mirrored from the OAK governance repository, which holds the authoritative copy.
  It is reproduced here so that citations in shipped documentation resolve for a
  reader who has only this repository. Do not edit this copy; see docs/adr/README.md.
-->

# ADR-0009: Abstract model providers through capability contracts

- Status: Accepted
- Date: 2026-08-13
- Owners: @architecture, @security
- Requirement IDs: OAK-FR-ARC-007, OAK-NFR-SEC-003, OAK-NFR-PORT-002

## Context

OAK may use local or hosted LLMs for parsing, retrieval assistance and explanation. Provider APIs, data policies, context limits, structured-output behaviour and tool semantics vary. A nominally compatible API does not imply equivalent security or quality.

## Decision

Define task-level ports—structured extraction, evidence-grounded synthesis, embedding/reranking and optional planning—with capability, data-use, residency, latency/cost and evaluation metadata. Provider adapters expose deviations. Deterministic validation surrounds every response. Tool/deployment authority is external to the model interface.

## Alternatives

- **One provider SDK throughout:** rejected for lock-in and sovereignty.
- **Assume one wire protocol equals portability:** rejected because semantics and controls differ.
- **No LLM abstraction:** feasible for a minimal fixed model, but undermines the open component mandate.

## Consequences

Cross-provider contract/evaluation tests are required. Lowest-common-denominator interfaces may hide useful features, so extensions are namespaced and never required by canonical state.

## Revisit triggers

Task evidence may split or merge ports; no provider gains ambient authority.
