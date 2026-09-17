<!-- SPDX-License-Identifier: Apache-2.0 -->

# The OAK Community user manual

[`OAK-Community-Manual.pdf`](OAK-Community-Manual.pdf) is the illustrated end-to-end
manual for OAK Community: install, the CLI journey from brief to compiled bundle, the
browser workspace, the signed runner journey including revocation, artifact
verification, troubleshooting, and complete uninstall.

The authoritative source is [`manual.html`](manual.html); the PDF is a rendering of it.
The optional model-provider chapter's screenshot (`assets/11-models.png`) is captured the
same way as the rest, with the stack's own capability token and no key stored, so the
capture changes nothing about the running configuration.
The screenshots in `assets/` are captured from a **real journey** against the Compose
stack, the expected-output excerpts are what real runs of the documented journeys
printed, and the repository's end-to-end suites exercise the same invocations
continuously (`oak revoke-approval` is covered by the revocation integration suite
instead — see the manual's colophon).

## Rebuilding

```bash
# 1. Screenshots (requires the Compose stack healthy)
docker compose up -d --build
OAK_MANUAL_SCREENS=1 pnpm --dir web exec playwright test e2e/manual-screens.spec.ts

# 2. The PDF, via the same pinned Chromium the e2e suite uses
pnpm --dir web exec node ../docs/manual/build_manual.mjs
```

Regenerate both whenever the workspace UI or the documented commands change. The
capture spec (`web/e2e/manual-screens.spec.ts`) is gated behind `OAK_MANUAL_SCREENS=1`:
`make web-e2e` collects it but reports it as skipped. The PDF rebuild uses the pinned
Chromium already installed for the e2e suite, so a rebuild on the same platform from
unchanged source reproduces the same document apart from the PDF's embedded creation
timestamp. It is not byte-reproducible across machines: the stylesheet names system
font families (Georgia, Helvetica Neue, SF Mono) with generic fallbacks, so a host
without them substitutes fonts and can repaginate. That is why the HTML source, not
the PDF, is authoritative — the PDF is a convenience rendering.
