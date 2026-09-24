<!-- SPDX-License-Identifier: Apache-2.0 -->

# The OAK Community user manual

[`OAK-Community-Manual.pdf`](OAK-Community-Manual.pdf) is the illustrated end-to-end
manual for OAK Community: who it is for, the two install routes and what each sets up,
the CLI journey from brief to compiled bundle, the browser workspace, the other ways in
(REST, the remote CLI and MCP, as one case relayed between them), the signed runner
journey including revocation, artifact verification, troubleshooting, and complete
uninstall. [`../tour.md`](../tour.md) is the Markdown companion to its chapter 5, with
every MCP request written out in full.

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

Regenerate both whenever the workspace UI, the documented commands or the version
change: the masthead in every screenshot shows the version the stack reports. The
capture spec (`web/e2e/manual-screens.spec.ts`) is gated behind `OAK_MANUAL_SCREENS=1`:
`make web-e2e` collects it but reports it as skipped. To capture from a stack on other
ports or under another Compose project name, so that a stack holding real cases is left
alone, set `OAK_WEB_BASE_URL` and `OAK_API_BASE_URL` to that stack's origins (for example
`http://127.0.0.1:15173` and `http://127.0.0.1:18080`) and `COMPOSE_PROJECT_NAME` to its
project name, exported. The spec drives the first. Before the first screenshot it fetches
its token through `compose()` in `web/e2e/support.ts`, which first checks with a read-only
`docker compose port` that Compose reaches the project serving both origins. If not, the
spec stops there and no asset is overwritten. The PDF rebuild uses the pinned Chromium
already installed for the e2e suite, so a rebuild on the same platform from unchanged
source reproduces the same document apart from the PDF's embedded creation timestamp. It
is not byte-reproducible across machines: the stylesheet names system font families
(Georgia, Helvetica Neue, SF Mono) with generic fallbacks, so a host without them
substitutes fonts and can repaginate. That is why the HTML source, not the PDF, is
authoritative — the PDF is a convenience rendering.
