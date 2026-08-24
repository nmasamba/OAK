<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Mirrored from the OAK governance repository, which holds the authoritative copy.
  It is reproduced here so that citations in shipped documentation resolve for a
  reader who has only this repository. Do not edit this copy; see docs/adr/README.md.
-->

# ADR-0005: Compile through target adapters; do not require Kubernetes

- Status: Accepted
- Date: 2026-08-13
- Owners: @architecture, @operations
- Requirement IDs: OAK-FR-DEP-001–008, OAK-NFR-PORT-002

## Context

OAK must support local, appliance, edge, cloud, cluster, HPC and air-gapped environments. Kubernetes is valuable but brings its own operational contract and cannot represent every target economically.

## Decision

Keep the canonical deployment IR provider-neutral and compile through versioned target adapters. Prove a local/single-node OCI-compatible adapter first and a Kubernetes adapter second. Git/OCI promotion transports immutable digests; it does not define the canonical product model.

## Alternatives

- **Kubernetes-only:** rejected by product doctrine and resource-constrained targets.
- **Imperative shell generation:** rejected for reproducibility, review and recovery.
- **One lowest-common-denominator output:** rejected because it cannot express substrate safety features.

## Consequences

Adapter capability discovery, compatibility matrices and contract tests are required. Target extensions live in namespaced fields and cannot silently alter canonical semantics.

The Community build begins with a non-executing/local adapter and proves a second backend through the same contract before `0.1.0`. Support for a target tool never transfers execution ownership to OAK.

## Revisit triggers

First-customer targets and measured adapter cost may change ordering or drop an adapter; provider-neutral canonical state remains.
