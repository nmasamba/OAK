<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  Mirrored from the OAK governance repository, which holds the authoritative copy.
  It is reproduced here so that citations in shipped documentation resolve for a
  reader who has only this repository. Do not edit this copy; see docs/adr/README.md.
-->

# ADR-0016: Accept user-supplied model-provider credentials as machine-local configuration

- Status: Accepted
- Date: 2026-09-17
- Owners: @architecture, @security
- Requirement IDs: OAK-FR-INT-009, OAK-NFR-SEC-003, OAK-NFR-SEC-007, OAK-FR-CTL-004

## Context

ADR-0009 abstracts model providers behind capability contracts but does not say where the credential that reaches one comes from, and the security invariants say plainly that canonical objects carry secret references rather than values and that the control plane does not hold secrets. Community needs a user to be able to point OAK at a model of their choosing without an OAK account, a hosted service, or a secret manager, and the obvious reading of the invariant — "OAK never touches a key" — would make that impossible.

The distinction the invariant is actually drawing is between two different things that both get called a secret. A *target* secret is the customer's production credential, resolved by the runner, inside the customer's trust domain, after a verified plan. A *model-provider* credential is the operator's own key for their own account, used to make a request that the operator asked for, on the operator's own machine. Conflating them would either forbid a feature the product needs or, worse, license the control plane to start holding the first kind.

## Decision

A user-supplied model-provider credential is **machine-local configuration**, not control-plane state. Specifically:

- It never enters a canonical object, an audit event, an export, a database row, a log, a telemetry record, or any response from any interface. What may be recorded is which backend holds it and a salted fingerprint.
- It is stored by an adapter behind a credential port: the operating system keychain where one exists, otherwise an owner-only file, or a reference to a documented environment variable that stores nothing. A missing keychain is reported, never silently downgraded.
- It is read at the moment of use and not retained on the object that used it.
- It is reachable only from the local CLI, from loopback REST routes guarded by a per-process capability token, and from the browser workspace those routes serve. It is permanently absent from MCP and from remote CLI mode, because neither is the operator's own machine.
- Reading or changing a credential is a narrower thing than causing one to be spent, and the two are separated deliberately. An MCP client cannot store, read, remove or select a credential at all; it can ask for a model-mode interpretation, which spends whichever credential the operator already configured. That is the operator's own decision to have made, it is audited with the family, model and proposal digest, and it defaults to off: an MCP client that says nothing gets the deterministic interpreter.
- Target-secret resolution is unchanged and stays outside the control plane entirely. This ADR grants no authority over it.

## Alternatives

- **Require a secret manager:** rejected. It makes a single-user local tool depend on infrastructure it otherwise does not need, and Community must work without an account or a hosted dependency.
- **Accept the key per request and never store it:** rejected. The key would then travel on every interpretation, including through a browser, which is a worse exposure than storing it once at rest.
- **Forbid user-supplied credentials entirely:** rejected. It does not remove the need; it moves the key into an environment variable on the server process with no fingerprint, no backend choice and no removal path.
- **Store it in the workspace beside the artifacts:** rejected. Workspaces are exported, copied and backed up; a credential in one would travel with it.

## Consequences

A stored key is readable by anything running as that user, and usable by anything that can reach the loopback port and read the token file. That is recorded as `RR-040` rather than mitigated, because the threat model for a local single-user tool does not include a same-user attacker. Backups must exclude the credential directory, which the operations guide states and the Compose volume layout makes practical. The capability token adds a second, separate control so that a web page cannot use the loopback routes even if it reaches them, and the token is per process so a restart revokes it.

Sending a brief to a configured provider is a real data egress and is recorded as `RR-039`. It is opt-in, auditable, and absent from the deterministic path.

## Revisit triggers

A multi-user or hosted distribution invalidates the "operator's own machine" premise and needs a different decision entirely. A per-tenant budget (`RR-041`) would also change the analysis, because spend would stop being self-limiting.
