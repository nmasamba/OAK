<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Mirrored from the OAK governance repository, which holds the authoritative copy.
  It is reproduced here so that citations in shipped documentation resolve for a
  reader who has only this repository. Do not edit this copy; see docs/adr/README.md.
-->

# ADR-0011: Classify openness explicitly and approve components contextually

- Status: Accepted
- Date: 2026-08-13
- Owners: @owner, @legal-compliance, @architecture
- Requirement IDs: OAK-FR-CAT-001–006

## Context

“Openly available” conflates OSI-approved software, Open Source AI, open-weight models with restrictions, source-available products, proprietary services and datasets with independent terms. Repository licence alone does not resolve transitive, model or data rights.

## Decision

Adopt explicit software/model/data availability classes and default to commercially usable OSI-approved software. Evaluate Open Source AI under the current OSI definition. Restricted open-weight, source-available and proprietary dependencies require a configured exception with consequences, owner and exit plan. Approval is specific to component version, target, use and expiry.

OAK Community source, schemas and repository documentation are licensed under Apache License 2.0 unless a file states otherwise. Third-party components, models, data, generated bundles and imported policy packs retain their independent terms; OAK records rather than overrides them.

## Alternatives

- **Permissive-only software:** simpler but may exclude justified copyleft; can be a deployment policy.
- **Anything downloadable is open:** rejected as inaccurate and risky.
- **Proprietary forbidden absolutely:** may conflict with customer requirements; exception policy is more explicit.

## Consequences

Licence evidence and review become catalogue costs. The benefit is no proprietary or restrictive dependency by stealth.

## Revisit triggers

The relevant OSI definition changes, a material dependency category is introduced, or a first customer defines a stricter sovereignty rule.
