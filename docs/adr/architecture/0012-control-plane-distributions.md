<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Mirrored from the OAK governance repository, which holds the authoritative copy.
  It is reproduced here so that citations in shipped documentation resolve for a
  reader who has only this repository. Do not edit this copy; see docs/adr/README.md.
-->

# ADR-0012: Ship one control-plane contract across Community, Enterprise and Cloud

- Status: Accepted
- Date: 2026-08-14
- Owners: @owner, @architecture, @security
- Requirement IDs: OAK-FR-CTL-001–009, OAK-NFR-PORT-001–002, OAK-NFR-SEC-001–005

## Context

OAK must be convenient for community users, commercially operable as a managed service and deployable in regulated, private or disconnected estates. A central service that processes customer production data or proxies inference would add latency, concentration of privilege, data-processing obligations and lock-in. Separate product implementations would drift in assurance and make the self-hosted edition dependent on hidden SaaS behavior.

## Decision

Ship three distributions from the same canonical schemas, application services, runner protocol and container builds:

1. **OAK Community:** local compiler, CLI, API/UI, policy/adapter SDK and basic runners; no OAK account required.
2. **OAK Enterprise:** the complete control plane and runners deployed into customer Kubernetes, cloud, on-premises or air-gapped estates with enterprise identity, tenancy, registries, approvals and evidence operations.
3. **OAK Cloud:** a managed multi-tenant control plane with customer-environment runners that communicate outbound where possible.

The control plane receives architecture and assurance metadata by default, not production prompts/responses, source data/documents, weights, credentials or raw personal data. Installed application traffic bypasses OAK. Capabilities may differ by edition, but canonical correctness and export cannot depend on an unavailable hosted service.

## Alternatives

- **SaaS-only central execution:** rejected because it violates sovereignty, data minimization, latency and air-gap goals.
- **Independent Community and enterprise codebases:** rejected because safety and contract drift would be structural.
- **Self-hosted only:** retained as Enterprise, but not the default commercial convenience model.
- **OAK in the inference path:** rejected; OAK is supervisory, not a universal application gateway.

## Consequences

Ports for identity, storage, keys, policy, registry and runner transport must support local and enterprise implementations. Release tests must prove no hidden SaaS dependency. Managed operations and tenancy are substantial future work; Community's local tenant is not evidence that those controls exist.

## Revisit triggers

A distribution cannot meet a verified legal/security requirement with the shared contract, a customer requires a materially different trust boundary, or operating evidence shows the runner communication model is infeasible. A revisit must preserve export and document compatibility/migration.
