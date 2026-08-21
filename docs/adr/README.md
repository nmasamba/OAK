<!-- SPDX-License-Identifier: Apache-2.0 -->

# Architecture decision records

There are two series here, and they are numbered independently.

## Implementation decisions

Decisions about how *this repository* is built. Owned here.

| ADR | Decision |
|---|---|
| [0001](0001-toolchain-and-runtime-contracts.md) | Pin supported toolchains and handwrite runtime contract wrappers |
| [0002](0002-release-versioning.md) | Release the first OAK Community version as `0.7.0` |

## Architecture decisions (`architecture/`)

Decisions about what OAK *is*, taken in the OAK governance repository, which holds the
authoritative copies. The ones cited by shipped documentation are mirrored here verbatim
so that a reader who has only this repository can follow the reference — a load-bearing
justification a reader cannot resolve is worse than no citation.

| ADR | Decision | Why it is cited here |
|---|---|---|
| [0005](architecture/0005-deployment-substrates.md) | Deployment substrates | The second renderer backend in [extension-sdk.md](../extension-sdk.md) |
| [0011](architecture/0011-open-component-policy.md) | Open component policy | Every dependency review in [dependencies.md](../dependencies.md) |
| [0012](architecture/0012-control-plane-distributions.md) | One control-plane contract across distributions | Why Community has no Kubernetes profile and why its local tenant is not tenant isolation |
| [0013](architecture/0013-community-implementation-stack.md) | Python core and TypeScript web workspace | The choice of stack behind the dependency record |
| [0014](architecture/0014-design-case-interface-parity.md) | Design-case interface parity | Why every interface drives the same aggregate |
| [0015](architecture/0015-typed-runner-operations.md) | Typed runner operations | The runner authority model behind [signed-runner.md](../signed-runner.md) |

**Do not edit the mirrored copies.** Change the governance repository and re-mirror. They
carry a header saying so. A contract test
(`tests/contract/test_adr_references.py`) fails if a shipped document cites an ADR that
does not resolve to a file here.

## Writing a new one

Implementation decisions go in this directory with the next number in the implementation
series. Anything that changes what OAK is — a contract, a trust boundary, a distribution
boundary — belongs in the governance repository instead.

Follow the existing shape: Status, Date, Owners, Requirement IDs, Context, Decision,
Alternatives (with the reason each was rejected), Consequences, Revisit triggers. The
alternatives section is the part that matters in two years; a decision without recorded
rejected options reads as an accident.
