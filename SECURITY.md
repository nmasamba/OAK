<!-- SPDX-License-Identifier: Apache-2.0 -->

# Security policy

## Reporting a vulnerability

Report privately, not in a public issue.

Use GitHub's private vulnerability reporting on this repository:
**Security → Report a vulnerability** at
<https://github.com/nmasamba/OAK/security/advisories/new>. That channel is private to the
maintainers and does not require an email address to be published here.

Please include: what you can do with it, the steps to reproduce, the commit or release you
tested, and your platform. A proof of concept against a local instance is ideal — never
test against infrastructure you do not own.

**Expectations, stated honestly.** OAK Community is maintained on a best-effort basis by a
small project. There is no staffed security team, no guaranteed response time, and no bug
bounty. What you will get is an acknowledgement, an assessment, and a fix or a documented
limitation. If you need a response by a deadline, say so in the report.

## Scope

**In scope** — anything that breaks a control this project claims:

- Bypassing signature, approval or runner verification: acting on a plan that is
  unsigned, unapproved, tampered, expired, replayed, revoked or bound to a different
  target.
- Verifying a signature against a key carried inside the document being checked rather
  than a pinned anchor.
- Reaching a capability through the MCP server or remote CLI that the capability matrix in
  [docs/interfaces.md](docs/interfaces.md) says is unavailable — approval, signing,
  dispatch, secret resolution, policy override, arbitrary file read, command execution.
- Getting a `command`, `shell`, `executable` or `argv` field into any canonical document.
- Making a fail-closed path fail open: an unknown tool, kind, adapter or schema that is
  skipped rather than refused.
- Crossing a tenant boundary, or getting an existence oracle out of a cross-tenant denial.
- Leaking a secret value, private key or another tenant's content into a log, error
  message, journal entry or exported artifact.
- Making the artifact verification procedure in
  [docs/release-process.md](docs/release-process.md) accept a tampered artifact.

**Out of scope** — already documented, and not news:

- Everything in [docs/security/residual-risk.md](docs/security/residual-risk.md). Those
  are known, recorded, accepted gaps. If you can show one is *worse* than the register
  says, that is very much in scope.
- The absence of authentication. Community binds a local actor and tenant from headers or
  environment; they are not credentials and the documentation says so repeatedly. An
  unauthenticated deployment exposed on a network is a configuration you were told not to
  create, not a vulnerability.
- Attacks that require write access to the operator's own home directory or Docker daemon.
  Anyone with that already holds the private keys in `~/.oak/trust`.
- Denial of service through unbounded local workloads. There is no quota or rate limiter
  and the register says so (`RR-024`).
- Findings against dependencies with no OAK-reachable path — report those upstream, though
  we would like to hear about them.

## What this release does and does not assure

OAK Community `0.7.0` is a **local-first developer release**. It carries no production or
customer readiness claim, and a release approval is not a deployment approval.

**No external security review was commissioned for this release.** All security work —
the threat-model coverage index, the adversarial suites, the secret and log review, the
runner sandbox review — was performed by the project itself. Nothing in this repository
should be read as third-party assurance, certification, or an audit in the sense that word <!-- assurance-claim-reviewed: this sentence denies the claim -->
carries in a compliance context.

What does exist, and is checkable:

- [docs/security/threat-coverage.md](docs/security/threat-coverage.md) — every threat id
  mapped to the tests that exercise it, and every gap named.
- [docs/security/residual-risk.md](docs/security/residual-risk.md) — what is not
  defended, with severities scored for the shipped configuration.
- Adversarial suites covering signature forgery, replay, revocation, wrong target,
  expiry, tampering, prompt injection, MCP tool escalation, confused-deputy actors,
  tenant crossover, oversized and deeply nested frames, and execution-field injection.

## Supported versions

`0.7.0` is the first release. Only the latest release is supported; there is no
backport policy yet.

## Dependencies

`make audit` runs `pip-audit` and `pnpm audit`. Dependency reviews, including reachability
analysis for advisories that are not reachable from OAK, are recorded in
[docs/dependencies.md](docs/dependencies.md). Advisories are never suppressed with an
ignore list.
