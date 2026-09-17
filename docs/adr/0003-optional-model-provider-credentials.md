<!-- SPDX-License-Identifier: Apache-2.0 -->

# ADR-0003: How this build stores a model-provider credential and calls a provider

- Status: Accepted
- Date: 2026-09-17
- Owners: @architecture, @security
- Governs: `src/oak/adapters/credentials/`, `src/oak/adapters/models/`, the `/v1/models` routes
- Implements: [ADR-0016](architecture/0016-user-supplied-model-provider-credentials.md), [ADR-0009](architecture/0009-model-provider-abstraction.md)

## Context

ADR-0016 decides that a user-supplied model-provider credential is machine-local configuration. This ADR records how that is built here, because several of the choices look arbitrary until the alternative is stated.

## Decisions

**The transport is `http.client` from the standard library, in one module.** Not `urllib.request`: `urlopen` builds an opener whose default handlers read `HTTPS_PROXY` and, on macOS, the system proxy configuration, and follow redirects while re-sending headers. A host allowlist means nothing if the connection goes to a proxy instead, and a redirect would hand the `Authorization` header to whatever `Location` names. `http.client` connects to the host it is given and follows nothing. Not a provider SDK either, and not one SDK per family: `docs/dependencies.md` records the argument, and ADR-0009 already rejected "one SDK throughout".

**One module may open a connection.** `oak.adapters.models.transport` is the only importer of a network client among the model adapters, and the egress suite pins that. Provider profiles, prompt construction and catalogue parsing are data and pure functions, which is what makes them testable against recorded hostile fixtures without a socket.

**The deadline covers the whole exchange.** A socket timeout bounds one receive, and `http.client` reads the status line and each header separately, so a provider dribbling its response header could hold a request open indefinitely while every receive stayed inside its timeout. The response's file object is wrapped, through the connection's response class, so every read runs against one monotonic deadline. The cap is 55 seconds because the shipped nginx proxy gives up at 60, and an interpretation the browser saw fail but the API went on to commit is worse than a refusal.

**A loopback host is parsed, not pattern-matched.** The `local` family is allowed to speak plain http precisely because the bytes do not leave the machine, so the test that decides "this is the machine" is load-bearing. `127.evil.example.com` starts with `127.` and is an ordinary DNS name whose owner chooses where it resolves; only a literal loopback address or the exact name `localhost` counts.

**Provider text is parsed to choose a code and then discarded.** No provider message, header or body reaches an `OAKError`, a log or a document. The status map is fixed, and an error `type` that does not fully match a conservative pattern becomes `unspecified` rather than being echoed.

**Model output is untrusted twice.** The adapter bounds and de-duplicates what the model returned before it becomes a proposal; the compiler then merges that proposal under its own rules — admissible paths only, explicit brief values win, every claim re-validated against the intent schema, every refusal recorded as a finding. Neither layer trusts the other's bounds.

**Discovery is explicit.** `oak models status`, `GET /v1/models` and `interpret` never contact a catalogue. Only `oak models discover` and `POST /v1/models/{family}:discover` do, and a catalogue that cannot be read produces the pinned chain labelled `pinned` rather than a pretend live answer.

**The capability token is a dependency, not a check inside each handler.** FastAPI resolves dependencies before it parses a request body, so an unauthorised caller is refused without its request being examined and without being told what was wrong with it.

## Consequences

The egress surface is small enough to name in a test, and does not grow quietly: a module importing an SDK nobody listed is caught by a declared-dependency rule rather than by a denylist. The cost is that the transport is hand-written, including its bounded reads and its refusal to follow redirects, and that each provider profile encodes a request shape that can drift; recorded fixtures catch a shape change in review, and `tests/live/` catches it against the real APIs when someone runs it deliberately.

## Revisit triggers

A second concurrent provider call per interpretation, streaming responses, or a proxy requirement would each need this revisited — the last one with an explicit, documented, safety-relevant variable rather than by inheriting the environment's.
