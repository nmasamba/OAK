<!-- SPDX-License-Identifier: Apache-2.0 -->

# Signed webhook events for portals and CI

OAK Community does not run a webhook dispatcher. What it defines — here and in
`schemas/webhook-envelope.schema.json` — is the *envelope contract* a publisher
(a small bridge you run beside `oak-worker`, reading the outbox) uses to hand
audit events to portals, chat bridges, or CI, and the verification rules every
consumer must apply before trusting one.

## The contract

An envelope wraps exactly one canonical audit event and is signed with Ed25519
over its canonical JSON bytes with the `signature` block removed (the same
convention as every other signed OAK document):

- `delivery_id` — unique per delivery; consumers deduplicate on it;
- `sequence` — the event's audit sequence; consumers detect gaps with it;
- `event` — the full canonical audit-event document, untouched;
- `signature` — role `webhook-publisher`, with `key_id` derived from the
  public key so a rotated key is visibly a different identity.

`examples/example-webhook-envelope.yaml` is a real signed envelope. Its
signing key was generated in a throwaway directory and discarded; the pinned
public half lives in `webhook-publisher.identity.json`, so the example is
verification-reproducible but cannot be re-signed.

## Verifying

Never verify with the key embedded in the envelope — pin the publisher's
public key out of band and verify against that:

```bash
oak validate webhook ../example-webhook-envelope.yaml \
  --public-key webhook-publisher.identity.json
```

The validator refuses an envelope whose signer differs from the pinned key,
whose `key_id` does not derive from it, or whose signature fails, with the
stable codes `OAK-VALIDATE-WEBHOOK-KEY` and `OAK-VALIDATE-WEBHOOK-SIGNATURE`.

## Headless CI validation

The same `oak validate` command verifies exported cases and compiled plan
bundles with no live server, which is the CI entry point for any portal that
receives OAK artifacts:

```bash
oak validate export ./case-export/
oak validate bundle ./bundle/
```

Export validation replays the full workspace import (schemas, digests,
lineage, tenant scope); bundle validation checks the five compiled documents
against their schemas, verifies the digest links between plan, bundle, and
decision, confirms the runner plan is still an inert draft, and refuses any
document carrying a `command`/`shell`/`executable`/`argv` field.

## Replay and ordering

Delivery is at-least-once by assumption: consumers must deduplicate by
`delivery_id`, order by `sequence`, and treat a sequence gap as missing
events, never as silence. A consumer that acts on webhook content without
signature verification and deduplication is outside this contract.
