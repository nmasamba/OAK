<!-- SPDX-License-Identifier: Apache-2.0 -->

# The OAK Community user manual

[`OAK-Community-Manual.pdf`](OAK-Community-Manual.pdf) is the illustrated end-to-end
manual for OAK Community: install, the CLI journey from brief to compiled bundle, the
browser workspace, the signed runner journey including revocation, artifact
verification, troubleshooting, and complete uninstall.

The authoritative source is [`manual.html`](manual.html); the PDF is a rendering of it.
The screenshots in `assets/` are captured from a **real journey** against the Compose
stack, and every command in the manual is the exact invocation exercised by the
repository's end-to-end suites — the suite passing means the manual's commands work.

## Rebuilding

```bash
# 1. Screenshots (requires the Compose stack healthy)
docker compose up -d --build
OAK_MANUAL_SCREENS=1 pnpm --dir web exec playwright test e2e/manual-screens.spec.ts

# 2. The PDF, via the same pinned Chromium the e2e suite uses
pnpm --dir web exec node ../docs/manual/build_manual.mjs
```

Regenerate both whenever the workspace UI or the documented commands change. The
capture spec (`web/e2e/manual-screens.spec.ts`) is gated behind
`OAK_MANUAL_SCREENS=1` and does not run as part of `make web-e2e`.
