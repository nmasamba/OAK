<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Mirrored from the OAK governance repository, which holds the authoritative copy.
  It is reproduced here so that citations in shipped documentation resolve for a
  reader who has only this repository. Do not edit this copy; see docs/adr/README.md.
-->

# ADR-0014: Make `DesignCase` the shared aggregate for every interface

- Status: Accepted
- Date: 2026-08-14
- Owners: @architecture, @product
- Requirement IDs: OAK-FR-CTL-001, OAK-FR-INT-001–006, OAK-NFR-UX-001–002, OAK-NFR-REL-001

## Context

OAK serves architects, product/risk reviewers, engineers and authorized agents through web, API, CLI, MCP and portals. Separate interface workflows would create competing state, inconsistent approvals and a privileged path that could bypass questions or gates. A conversation transcript is not an adequate aggregate.

## Decision

Add a versioned `DesignCase` aggregate that indexes immutable brief, intent, cost/nexus, candidate, decision, assurance, bundle, runner, approval and observation artifacts. Every interface maps onto the same application commands/queries and state-transition policy. `interface_origin` is audit metadata only and never authority.

REST/OpenAPI is the first public network contract. Local CLI invokes the same application services through a file repository; remote CLI, web and portal integrations use REST; MCP exposes a bounded subset mapped to the same services. The runner protocol is separate because it crosses a different trust boundary.

## Alternatives

- **Per-interface workflows:** rejected because semantics and authority would drift.
- **REST for every local CLI action:** rejected because Community must work offline without a server; application-service parity provides the same meaning.
- **Chat transcript as workspace:** rejected because it cannot provide typed immutable lineage or safe concurrency.
- **One giant embedded document:** rejected because artifact lifecycles, digests and evidence retention differ.

## Consequences

Application commands, expected version, idempotency and tenant/actor context become stable seams. Interface conformance tests must compare semantic digests and denials. UI clients display server-allowed actions rather than reimplementing transitions. The aggregate needs explicit migration/compatibility policy.

## Revisit triggers

Representative workflows prove the aggregate is too coarse or creates unacceptable contention. Decomposition must retain one authoritative workflow and cross-interface conformance.

