<!-- SPDX-License-Identifier: Apache-2.0 -->

# Dependency record

OAK uses small, replaceable open components at interface, validation, and persistence
boundaries. Versions are locked in `uv.lock` and `pnpm-lock.yaml`; ranges below are not a
substitute for those locks.

| Component | Purpose | Boundary | Licence family |
|---|---|---|---|
| Pydantic | Typed runtime boundary models | contracts/interfaces | MIT |
| FastAPI | OpenAPI HTTP adapter | interfaces only | MIT |
| Typer | CLI adapter | interfaces only | BSD-3-Clause |
| Uvicorn | Local ASGI process | interface entrypoint | BSD-3-Clause |
| jsonschema | Canonical JSON Schema validation | contracts | MIT (no extras; see the 2026-08-21 review) |
| PyYAML | Public YAML example parsing | contracts | MIT |
| SQLAlchemy 2.0 | PostgreSQL transaction and mapping toolkit | PostgreSQL persistence adapter only | MIT |
| Alembic | Forward-only PostgreSQL migrations | migration tooling and API/worker startup | MIT |
| cryptography (PyCA) | Ed25519 signing and verification | signing adapter and runner verification | Apache-2.0 OR BSD-3-Clause |
| Psycopg 3 with binary implementation | PostgreSQL DB-API driver and bundled local `libpq` | below SQLAlchemy in PostgreSQL processes only | LGPL-3.0-only; bundled libraries retain their terms |
| React | Architecture workspace UI | web only | MIT |
| Vite | Web build tooling | web development | MIT |
| TypeScript | Strict web type checking | web development | Apache-2.0 |
| Playwright | Browser end-to-end harness | web development only | Apache-2.0 |
| axe-core (via @axe-core/playwright) | Automated accessibility checks | web development only | MPL-2.0 |
| Instrument Serif (via @fontsource/instrument-serif) | Display typeface, bundled and served same-origin | web only | OFL-1.1 |
| IBM Plex Sans and IBM Plex Mono (via @fontsource/ibm-plex-sans, @fontsource/ibm-plex-mono) | Interface and monospace typefaces, bundled and served same-origin | web only | OFL-1.1 |
| IBM Plex Sans (regular, bold, italic) and IBM Plex Mono, vendored TTFs | The report PDF's embedded fonts (pre-1.0 assurance batch, below) | report renderer adapter only; four files in the wheel, parsed by ReportLab's `TTFont` | OFL-1.1 |
| keyring (optional extra `keychain`) | OS credential store for user-supplied model-provider keys | credentials adapter only; lazily imported; file store is the fallback | MIT (Linux pulls SecretStorage BSD-3-Clause and jeepney MIT; Windows pywin32-ctypes BSD-3-Clause) |
| ReportLab | The architecture report as a PDF | report renderer adapter only (`oak.adapters.report`) | BSD-3-Clause |
| Pillow (via ReportLab) | Required by ReportLab; OAK passes it no image | below the report renderer only | MIT-CMU (HPND) |

The core domain and compiler packages do not import interface or persistence frameworks.
Development-only format, lint, type, test, audit, and SBOM tools are locked but do not ship as
runtime requirements.

## Sprint 3 persistence review

The capability gap is ACID PostgreSQL transactions, migrations, and a maintained Python
driver. Reimplementing SQL parsing, connection pooling, PostgreSQL type adaptation, migration
ordering, and concurrency behavior with the standard library would be unsafe. ADR-0013
already selects PostgreSQL, SQLAlchemy, and Alembic for Community `0.x`; this review selects
Psycopg 3 as the driver.

- **SQLAlchemy 2.0:** established MIT-licensed toolkit with explicit PostgreSQL/DB-API
  boundaries and Python 3 support. OAK uses SQLAlchemy only in
  `oak.adapters.persistence`, so the repository port is the replacement seam.
- **Alembic:** maintained by the SQLAlchemy project under MIT and designed for SQLAlchemy
  metadata. It is invoked only for database schema lifecycle. Migrations remain plain,
  reviewable Python/DDL and do not define canonical object meaning.
- **Psycopg 3:** the current maintained Psycopg generation, supports Python 3.13 and
  PostgreSQL 17, and exposes sync/async DB-API behavior. It is LGPL-3.0-only rather than
  permissive. ADR-0011 permits contextually reviewed OSI-approved copyleft dependencies and
  requires their independent terms to be recorded. OAK does not copy or modify Psycopg; it
  remains a replaceable SQLAlchemy driver. The `binary` extra is chosen for reproducible local
  Community/container setup without host `libpq` headers and brings its own client libraries;
  the SBOM and vulnerability audit therefore cover both Python distributions and bundled
  native libraries. A production distribution may replace it with the source/C build behind
  the same SQLAlchemy URL after an image-level review.

The selected ranges intentionally stay on SQLAlchemy 2.0 and Psycopg 3 major versions.
Alembic revisions are forward-only. A dependency rollback reverts `pyproject.toml` and
`uv.lock`; file-backed local mode has no dependency on this stack.

No dependency creates a hosted runtime requirement. PostgreSQL receives only the canonical
control-plane metadata permitted by the data boundary; production/customer content remains
excluded by default.

## Sprint 5 signing review

The capability gap is asymmetric signatures for plan, approval, and runner-message
authenticity. Implementing Ed25519 by hand would be unsafe. `cryptography` is the PyCA
reference implementation, dual-licensed Apache-2.0 OR BSD-3-Clause, and is used only through
two narrow seams: `oak.adapters.signing` holds private keys and signs, while
`oak.contracts.signatures` verifies. The runner imports the verification path alone and
never loads a private key. Keys are raw 32-byte Ed25519 seeds in a 0600 file under a private
trust directory, labelled `development`; Community makes no production assurance claim. The
`SigningPort` is the replacement seam if a KMS or hardware backend is introduced later.

## Sprint 6 policy engine review

The capability gap is an optional open policy evaluator behind the policy port. No Python
dependency was added: the OPA adapter executes a locally installed `opa` binary (Open
Policy Agent, Apache-2.0, CNCF-graduated) through a fixed allowlisted argument vector with
`shell=False`, a sanitized environment, timeouts, and bounded output. The binary is never
downloaded, bundled, or required: `oak policy evaluate` defaults to the deterministic
built-in engine, engine selection is explicit, and a missing binary is a stable
`OAK-POLICY-ENGINE-UNAVAILABLE` error. Since `OAK-V1-010` the binary is resolved once, to an
absolute path on the absolute entries of `PATH`, and must report version 1.0.0 or later,
the release whose Rego (`import rego.v1`) the generated module is written in; it has been
exercised with 1.19.1. Generated Rego carries pack content only as
JSON-encoded literals, and the engine-equivalence suite proves byte-identical canonical
evaluations against the built-in engine whenever `opa` is present. The `PolicyEnginePort`
is the replacement seam; removing the adapter removes the integration completely.

## Sprint 12 web font review

The capability gap is the workspace's own typography: before Sprint 12 the web shipped no
font and relied on whatever the browser had. Three Fontsource packages, each pinned to the
exact version `5.3.0` in `web/package.json` and `pnpm-lock.yaml`, carry Instrument Serif,
IBM Plex Sans and IBM Plex Mono as static `woff2` files that Vite bundles into the web
image and nginx serves same-origin. No stylesheet, font or script is fetched from a CDN or
from Google Fonts at runtime; guard G1 in `scripts/check_studio_ui.py` fails on any such
URL in the web source. All three typefaces are under the SIL Open Font License 1.1, which
permits bundling and redistribution and requires no attribution in the interface. It
asks that the copyright notice and the licence travel with the fonts, so the three
licence texts are committed under `web/public/licenses/` and Vite copies them into every
built bundle, beside the font files. The packages declare no install-time build hook, so the pnpm build allowlist is unchanged
(`esbuild` only). Each package is replaceable by editing the seven `@fontsource/...`
imports at the top of `web/src/main.tsx` and the three `--font-*` tokens in
`web/src/tokens.css`. Only the weights the design uses are imported (serif 400 and 400
italic; sans 400, 500 and 600; mono 400 and 500), so the bundle carries the subsets Vite
references rather than every file the packages ship.

## Pre-1.0 assurance batch: report fonts (2026-10-28)

The capability gap is a PDF that prints the brief's own script (`RR-046`). The renderer used
the PDF standard Helvetica and Courier so that no font file shipped (Sprint 13's decision
K5), which limited it to Windows-1252. The owner reversed K5 on 2026-10-28 and chose Latin,
Greek and Cyrillic. The renderer now embeds IBM Plex, the family the web workspace already
uses (reviewed above for Sprint 12), through reportlab's own `TTFont` with subsetting, so
no new Python dependency is added. Each embedded subset holds the font's printable ASCII
range, which ReportLab always maps (`ttfAsciiReadable`, pinned on), and every other glyph
the report draws. ReportLab's font objects are shared by the whole process, so the renderer
draws one report at a time.

| File | Upstream | SHA-256 |
|---|---|---|
| `IBMPlexSans-Regular.ttf` | `@ibm/plex-sans@1.1.0`, `packages/plex-sans/fonts/complete/ttf/` | `975dcda37d80f038dcd143c22e33ca2d97a0cc5a929aace1c749153b0fe1afa5` |
| `IBMPlexSans-Bold.ttf` | `@ibm/plex-sans@1.1.0`, same directory | `9e6c74a889a700d707613d24548fe4ffa6bc59559a0689d2cf9e133bdcdafb2f` |
| `IBMPlexSans-Italic.ttf` | `@ibm/plex-sans@1.1.0`, same directory | `a9c6ef9942c49e49d11e11a6dacc0b3a087978757e9b22a06b8ac22a6400fb15` |
| `IBMPlexMono-Regular.ttf` | `@ibm/plex-mono@2.5.0`, `packages/plex-mono/fonts/complete/ttf/` | `7c6fbddca4b700be918f5f6183d9bd4464fa427fe435f0b480d77fe2bb8c5a43` |
| `OFL-1.1-IBM-Plex.txt` | `LICENSE.txt` of both packages (one file) | `7e6b2818edbd8f6a01ae80641cc8f16a51080d08fb4e532be3a0b6f74adb07da` |

- **Source.** IBM's own repository, github.com/IBM/plex, at the two release tags above
  (2024-11-13 and 2026-06-11). Each file was checked against the git blob the tag names
  before it was vendored.
- **Licence.** SIL Open Font License 1.1, compatible with Apache-2.0 for bundling and
  redistribution. It asks that the copyright notice and the licence travel with the
  fonts, so `OFL-1.1-IBM-Plex.txt` sits beside them in `src/oak/adapters/report/fonts/`,
  ships in the wheel and the sdist with them, and is listed in `license-files`, so it is
  also in the wheel's `.dist-info/licenses/`, and the wheel's licence is
  `Apache-2.0 AND OFL-1.1`. The release's `THIRD-PARTY-LICENCES.md` lists packages, so it
  names the fonts in its preamble rather than as a row; the font's notice lives with the
  font. The name "Plex" is a Reserved Font Name: the files are
  embedded as subsets, which the OFL permits, and not modified or redistributed renamed.
- **Pinning.** `FONT_FILES` in `src/oak/adapters/report/pdf.py` names each file's SHA-256,
  and the renderer refuses to draw (`OAK-REPORT-RENDER`) with a file that differs.
  `.gitattributes` marks the directory `-text`, so git keeps the licence's CRLF bytes.
- **Size.** About 345 KB of the wheel (787 KB installed); a typical report embeds four
  subsets, and the reference report's PDF is about 106 KB.
- **Coverage.** Plex Sans has Latin, Greek and Cyrillic; Plex Mono has Latin and Cyrillic.
  Text prints as written where the font has the glyph; a compatibility character it lacks
  prints as its plain form, and any other character as U+FFFD, which both have.
- **Replacement boundary.** Changing the family means new files and digests in
  `FONT_FILES`, the four names in `src/oak/adapters/report/palette.py` and this table. The
  PDF has no structure tree; a different renderer would be the way to tag it.

## Sprint 4 web test tooling review

The capability gap is real-browser verification of the workspace journey, failure
recovery, and accessibility. Playwright (Apache-2.0, Microsoft-maintained) and axe-core
(MPL-2.0, Deque-maintained, consumed unmodified through `@axe-core/playwright`) are
development-only dependencies in the web workspace; neither ships in runtime artifacts or
images. Neither package registers an install-time build hook, so the pnpm build allowlist
is unchanged. Browser binaries are not vendored: `playwright install chromium` fetches the
pinned build explicitly, and the suite itself needs only the local Compose stack. ADR-0011
permits the reviewed MPL-2.0 component; axe-core remains replaceable behind the single
`expectAccessible` helper in the end-to-end support module.

The pnpm workspace permits an install-time build hook only for the lockfile-pinned `esbuild` package required by Vite. All other dependency build scripts remain blocked by default.

Container base images use readable version tags plus immutable manifest digests. Updating a base requires an explicit manifest edit, rebuild, and audit rather than an implicit tag move.

## Sprint 7 interface review

The capability gap is a Model Context Protocol server and a remote CLI transport. No Python
dependency was added for either.

The MCP server implements the stdio transport in-tree over the standard library. Community
exposes only `initialize`, `ping`, `tools/list` and `tools/call` on newline-delimited stdio;
the reference `mcp` SDK would have added five runtime dependencies (`httpx`, `httpx-sse`,
`sse-starlette`, `pydantic-settings`, `python-multipart`) to support HTTP and SSE transports
that Community does not offer, enlarging the supply chain and the audit surface of the one
interface whose whole purpose is boundedness. Supported protocol revisions are pinned in
`SUPPORTED_PROTOCOL_VERSIONS` and governed by [compatibility.md](compatibility.md); the
replacement seam is `oak.interfaces.mcp`, and adopting the SDK later would not change the
tool contract. Revisit if Community needs HTTP transports or the resources/prompts/sampling
capabilities.

The remote CLI client uses `urllib.request` from the standard library with explicit timeouts
and bounded reads rather than adding a runtime HTTP dependency. One bounded request per
command against a local control plane does not justify enlarging the released dependency set;
`httpx` remains a development-only dependency used by the API test suites. The replacement
seam is `oak.interfaces.cli.remote.RemoteClient`.

Webhook envelope verification reuses the existing `cryptography` Ed25519 primitives and the
in-tree `oak.contracts.signatures` verifier; no new signing or HTTP-server dependency was
introduced, and Community ships no webhook dispatcher.

## Sprint 9 model-provider review

The capability gap is keeping a user-supplied provider API key on the user's machine without
writing it to a plain file when the operating system offers a credential store. Two decisions
were made here, and one dependency was refused.

**No runtime HTTP dependency was added.** The provider adapters speak to one hosted API —
Hugging Face Inference Providers, plus the Hub for a token's verification — and a local
OpenAI-compatible server, with one bounded request per interpretation, through a single
standard-library `http.client` transport (`oak.adapters.models.transport`) that pins the
host allowlist, refuses redirects, reads against a total deadline, and consults no proxy —
`http.client` connects to the host it is given, whereas `urllib.request.urlopen` would read
`HTTPS_PROXY` and the macOS system proxy and send the request somewhere else entirely. The Sprint 7 argument for the
remote CLI (`httpx` "remains a development-only dependency") holds unchanged: one bounded
request per command does not justify enlarging the released closure, and a provider SDK —
or an MCP client for Hugging Face's own server, which Sprint 10 considered and rejected for
the same reason — would dominate it while ADR-0009 rejects "one provider SDK throughout"
in any case.

**`keyring` 25.7.0 (MIT) is the optional extra `keychain`.** It is the only cross-platform
way to reach macOS Keychain, the freedesktop Secret Service and the Windows Credential
Locker from Python, and it is what `gh`, `docker` and the coding-agent CLIs converge on. It is
confined to `oak.adapters.credentials.keychain_store`, imported lazily inside the store's
methods, so the deterministic journey never loads it and an installation without the extra
gets a stable `OAK-MODEL-KEYCHAIN-UNAVAILABLE` rather than an import error. Two behaviours
are deliberate: a missing backend is reported, never silently downgraded to a file (the
`gh` behaviour its users complain about most), and the `keyrings.alt` plaintext backends are
refused (`OAK-MODEL-KEYCHAIN-UNSAFE`) because they store the key base64-encoded while
claiming to be a keychain. Transitive closure on this platform: `jaraco.classes`,
`jaraco.context`, `jaraco.functools`, `more-itertools` (all MIT); Linux adds `SecretStorage`
(BSD-3-Clause), `jeepney` (MIT) and `cryptography`, already present; Windows adds
`pywin32-ctypes` (BSD-3-Clause). The release SBOM and licence inventory export the extra
(`scripts/build_release.py`, `uv export --extra keychain`) so the inventory describes
everything the wheel can install.

**Replacement seam:** `CredentialStorePort`. The file store (`0700` directory, `0600` file,
`O_EXCL | O_NOFOLLOW`, atomic rename, owner and mode checked on every read) is always
available and is the only backend inside the Compose containers. **Rollback:** remove the
extra from `pyproject.toml`, `uv lock`, and `KeychainCredentialStore` becomes permanently
"unavailable"; no stored document changes.

## Sprint 13 report renderer review

The capability gap is a portable document a decision-maker can keep, print and project:
the architecture report as a file. Writing PDF by hand is a format project of its own:
cross-reference tables, font metrics, text encoding and stream compression. A browser-side
library would leave the CLI without a report (kickoff decision K2). One dependency was
adopted and one refused.

**ReportLab 5.0.1 (BSD-3-Clause), adopted.** It is the long-established Python PDF
library, released on 2026-08-20 and shipped as a pure-Python wheel (`py3-none-any`). OSV
listed no known vulnerability on 2026-10-16. OAK uses its canvas, the standard Type 1 font
metrics and nothing else (as reviewed here; since the pre-1.0 assurance batch it embeds
the vendored IBM Plex TTFs through `TTFont` instead of the standard fonts, reviewed above):
- no platypus layout, no embedded font, no image, no hyperlink;
- invariant mode for a byte-stable file, with the document dates taken from the report's
  own `generated_at` rather than the clock;
- every ReportLab setting the canvas reads, and the standard fonts' encoding, set by the
  renderer before each rendering, because ReportLab otherwise takes them from `RL_*`
  environment variables, a `reportlab_settings` module or `~/.reportlab_settings`, and
  several of them change the bytes (`OAK-V1-015`);
- the two processes in `tests/unit/test_report_pdf.py` must produce the same bytes, one of
  them with `RL_*` variables set.

Its closure adds **Pillow 13.0.0** (MIT-CMU/HPND; 12.3.0 was pinned at Sprint 13 and lifted on
2026-10-22 when `pip-audit` named seven advisories against it, all fixed in 13.0.0), which
ReportLab requires at install time. OAK hands it no image, so its decoders see no input.
Pillow is the one new native wheel: macOS arm64, `manylinux_2_27` x86_64 and aarch64, and
`musllinux_1_2`. It raises the Linux x86_64 glibc floor from 2.24 to 2.27 and has no
armv7l wheel ([platforms.md](platforms.md)). `charset-normalizer`, the other runtime
requirement, was already locked.

**python-pptx 1.0.2 (MIT), refused.** Its licence, vulnerability history and wheel are
clean, but it fails maintenance:
- its last commit and release were on 2024-08-07;
- it has 541 open issues;
- the repository shows no maintainer response since.

Under the sprint's stop rule, the owner decided on 2026-10-16 to ship the PDF alone and to
treat the PPTX as a follow-up that needs its own library decision. It is not in the lock,
not even for tests.

**Boundary and replacement seam:** `ReportRendererPort` (`oak.ports.report`). The adapter
names the formats it writes, so a PPTX renderer can join without changing the port.
`tools/check_boundaries.py` forbids `reportlab`, `PIL`, `pptx` and `lxml` in the domain,
compiler, ports, application and runner, so only the adapter can reach them. **Rollback:**
remove `reportlab` from `pyproject.toml` and `uv lock`. Recording a report then fails with
`OAK-REPORT-RENDER`, and no stored document changes.

## Maintenance reviews

### 2026-10-27 msgpack 1.2.1 to 1.2.3 (development only)

On 2026-10-27 `pip-audit` began reporting `CVE-2026-114613` (`GHSA-j586-36cw-2gc2`,
published that day) against the locked `msgpack` 1.2.1: its C extension leaks memory
without bound when map-key validation or a container hook fails. It is fixed in 1.2.3.
`make audit` had passed in CI on 2026-10-26, and failed on both of PR #40's runs the next
day.

`msgpack` is **not** in the runtime closure. `uv tree --no-dev --invert --package msgpack`
finds no path to it. It reaches the development environment only through `cachecontrol`,
which `pip-audit` uses for its cache, as `filelock` below does, so neither the wheel nor an
image carries it, and nothing OAK runs imports it.

`uv lock --upgrade-package 'msgpack==1.2.3'` moved nothing else. It takes 1.2.3, the
release that carries the fix (2026-09-29), rather than the newest, 1.2.4: that was
published on 2026-10-26, a day before the advisory, and changes only the behaviour of the
pure-Python fallback, which nothing here needs. Checked for 1.2.3:
- **Licence:** still Apache-2.0.
- **Supported Python:** 3.10 and later, covering the pinned 3.13.12.
- **Compatibility:** `cachecontrol` 0.14.4 accepts any `msgpack` from 0.5.2 to below 2.0
  and calls only `msgpack.dumps` and `msgpack.loads`. `make audit` ran `pip-audit`, cache
  included, on 1.2.3.

No advisory was suppressed and no `pip-audit` ignore list was introduced.

### 2026-10-26 filelock 3.32.3 to 4.2.4 (development only)

On 2026-10-26 `pip-audit` began reporting three advisories against the locked `filelock`
3.32.3: `CVE-2026-112907`, `CVE-2026-112913` and `CVE-2026-112940`, all fixed in 4.2.1.
`make audit` had passed on 2026-10-23, and CI runs it on every push.

`filelock` is **not** in the runtime closure. `uv tree --no-dev --invert --package filelock`
finds no path to it. It reaches the development environment only through `cachecontrol`'s
`filecache` extra, which `pip-audit` uses for its cache, so neither the wheel nor an image
carries it, and nothing OAK runs imports it.

The upgrade was taken anyway, as for `urllib3` below. `uv lock --upgrade-package filelock`
moved nothing else, and took 4.2.4, the newest release: 4.2.2 to 4.2.4 followed the fix
within two days and fix regressions in it. Checked for 4.2.4:
- **Licence:** still MIT.
- **Supported Python:** 3.11 and later, covering the pinned 3.13.12.
- **Compatibility:** `cachecontrol` 0.14.4 sets no upper bound and takes only `FileLock`.
  The 4.0.0 breaking change is confined to `SoftReadWriteLock`'s on-disk protocol, which
  nothing here uses. `make audit` ran `pip-audit`, cache included, on 4.2.4.

No advisory was suppressed and no `pip-audit` ignore list was introduced.

### 2026-10-15 source-map-js 1.2.1 to 1.2.2 (web build tooling only)

`pnpm audit --audit-level=high` began failing on GHSA-68fv-2mgg-jv7q, an event-loop
denial of service through indexed source-map section offsets in `source-map-js` below
1.2.2. The package reaches the workspace only through `vite` → `postcss`, at build time;
it ships in no runtime artifact or image. Vite 7.3.7 (7.3.6 was lifted on 2026-10-22 for
GHSA-587h-7wmj-h5pm in its `launch-editor` dependency) and PostCSS 8.5.26 still pin the
vulnerable range, so `pnpm-workspace.yaml` carries an `overrides` entry forcing
`source-map-js` to 1.2.2 (BSD-3-Clause, unchanged) until an upstream PostCSS release
lifts it, at which point the override can go. The web build and the browser suite were
rerun on the override; nothing else changed.

The same audit lifted certifi 2026.7.22 to 2026.10.19 (PYSEC-2026-4320). It is a
development dependency only, reached through `httpx` and `pip-audit`'s `requests`, and is in
no runtime artifact: the model and research transport verifies TLS against the operating
system's trust store (`ssl.create_default_context()`).

Reviews outside a sprint boundary are recorded here, newest first, under the same standard
as a sprint dependency review.

### 2026-09-30 urllib3 2.7.0 to 2.8.0 (development only)

On 2026-09-30, after the `0.9.0` release build had passed `make audit`, `pip-audit` began
reporting three advisories against the locked `urllib3` 2.7.0: `CVE-2026-97687`,
`CVE-2026-97688` and `CVE-2026-97689`, all fixed in 2.8.0. CI's `make audit` step failed
on the next pushes.

`urllib3` is **not** in the runtime closure. `uv tree --no-dev --invert --package urllib3`
finds no path to it, and the `0.9.0` release SBOM does not list it. It reaches the
development environment only through `requests`, which `pip-audit` and its `cachecontrol`
cache depend on. So neither the wheel nor the API image carries it, and nothing OAK runs
imports it.

The upgrade was taken anyway, because the audit gate audits the development environment
and an advisory there is still an advisory. `uv lock --upgrade-package urllib3` moved
nothing else. Checked for 2.8.0:
- **Licence:** still MIT.
- **Supported Python:** 3.10 and later, covering the pinned 3.13.12.
- **Compatibility:** `requests` 2.34.2 accepts `urllib3>=1.26,<3`.

No advisory was suppressed and no `pip-audit` ignore list was introduced.

### 2026-08-25 unprivileged nginx base image and the pnpm-managed Node runtime

Two supply-chain changes from the pre-launch hardening, neither a Python or web package.

**Web runtime base image.** The capability gap was running the web image unprivileged
(`RR-037`): the Docker Official `nginx` image's master process runs as root and its
entrypoint writes root-owned paths. `nginxinc/nginx-unprivileged:1.29.1-alpine` was
selected — NGINX's own community-maintained unprivileged variant of the same nginx OSS
(BSD-2-Clause), differing only in uid 101, port 8080 defaults and `/tmp`-relocated
runtime paths — and pinned by tag plus immutable digest, with the pin guarded by
`make toolchain-check`. The alternative, patching the official image in the Dockerfile
(`USER nginx` plus pre-chowned cache/pid paths), was rejected as re-implementing what the
publisher already maintains. The publisher changes from the Docker Official Images
programme to the `nginxinc` organisation — the upstream NGINX maintainers themselves —
and the image lags Alpine's patch stream exactly as the official one did; the scan gate
carries over unchanged, and since Tier 3's Batch A the build applies no `apk upgrade`
(Alpine keeps no dated archive, and the images reproduce, `RR-006`), so a fix reaches the
image by re-pinning this `FROM` line's digest. The `0.9.0` scan reports no findings at any
severity for the rebuilt image, as the `0.8.0` and `0.7.1` scans did. Rollback is restoring
the previous `FROM` line and its pin.

**pnpm-managed Node.js runtime.** The capability gap was `RR-034`: nothing made the Node
that builds the web artifacts be the pinned one. `devEngines.runtime` in `package.json`
makes pnpm download and run Node 24.18.0 itself, and `pnpm-lock.yaml` now locks that
runtime per platform with sha256 integrity — official `nodejs.org` builds, plus the
project's `unofficial-builds.nodejs.org` musl variants, all MIT-licensed. It is a
development-time runtime, not a package: it ships in no artifact, and the image build
strips it (`deploy/images/strip-managed-node.cjs`) because the build container already
*is* the pinned Node. Known residual weakness: the musl variants come from the Node.js
project's unofficial-builds infrastructure — integrity-pinned by the lockfile but outside
the primary release channel; nothing in OAK's builds fetches them (the image build strips
the entry first). Rollback is deleting `devEngines` and re-running `pnpm install` to drop
the lockfile entry. No canonical document, digest, or schema changes from either item:
the reference case was verified byte-stable through both.

### 2026-08-22 container image scanner

`OAK-S8-003` requires container scans, and nothing in the repository performed one. The
capability gap is assessing the OS packages inside the images OAK ships — `pip-audit` and
`pnpm audit` cover the Python and web language closures and never look inside a built
layer.

`aquasec/trivy` was selected and **pinned to `0.74.0` by tag and index digest** in
`scripts/scan_images.py`, and the scan evidence records both. It is
Apache-2.0, actively maintained, and reads both Debian and Alpine package databases, which
is what the two images need. Alternatives considered: `grype` (equivalent, no advantage
here), and `docker scout`, rejected because it requires a Docker Hub account — a hosted
dependency and a credential, for a tool run during release.

It is **not** a project dependency. It is not in `uv.lock` or `pnpm-lock.yaml`, ships in no
artifact, and runs only when someone invokes `make scan-images`. It executes as a
container, and deliberately **without the Docker socket**: images are exported with
`docker save` and the scanner reads the tarball, so the scanner never holds the daemon.
The version pin matters for the same reason any gate's tooling is pinned — a floating tag
would make the gate's verdict depend on when it ran.

The scanner's own vulnerability database is fetched at run time and is not pinned; that is
inherent to vulnerability scanning and is why the scan is a release step rather than part
of `make check`, which must work offline. Results for `0.9.0` are recorded in
`docs/release/0.9.0/container-scan.md`; the earlier `0.8.0`, `0.7.1` and `0.7.0` records
remain at `docs/release/0.8.0/container-scan.md`, `docs/release/0.7.1/container-scan.md`
and `docs/release/0.7.0/container-scan.md`.

### 2026-08-21 jsonschema `format` extra removed

The `jsonschema[format]` extra was dropped from `pyproject.toml` in favour of plain
`jsonschema`. The extra was never load bearing: nothing in `src/` constructs a
`FormatChecker` or passes `format_checker=` to a validator, so `format` keywords in the
canonical schemas have always been annotation rather than validation — the behaviour
`docs/interfaces.md` and the Sprint 7 limitations already record.

What the extra did do was place eight packages in the runtime dependency closure of the
distribution, one of which is `rfc3987` 1.3.8, licensed **GPL-3.0-or-later**. OAK Community
is Apache-2.0. ADR-0011 permits a contextually reviewed OSI-approved copyleft dependency and
requires its independent terms to be recorded — as was done for Psycopg's LGPL — but this one
was neither reviewed nor recorded: the inventory above listed jsonschema as simply "MIT". A
release licence inventory would have had to either disclose an undiscussed GPL transitive or
misstate the closure.

`jsonschema[format-nongpl]` was considered and rejected. It swaps `rfc3987` for
`rfc3987-syntax` and resolves the licence question, but it keeps eight unused runtime
packages in order to preserve a capability that nothing enables. Enabling format checking was
also rejected: tightening validation so previously accepted documents are refused is a
breaking change for producers under `docs/compatibility.md`, and a release-hardening sprint is
the wrong place to make one.

Effect on the closure, measured with `uv export --no-default-groups`: 37 runtime packages,
down from 45. `fqdn`, `isoduration`, `jsonpointer`, `rfc3339-validator`, `rfc3987`,
`uri-template`, and `webcolors` all leave; `idna` stays because `anyio` requires it.
`rfc3987-syntax` and `rfc3986-validator` remain in `uv.lock` and in the development
environment because `cyclonedx-python-lib` — the SBOM generator, a development dependency —
itself depends on `jsonschema[format-nongpl]`. They are not runtime requirements of the
released wheel.

Rollback is restoring the extra in `pyproject.toml` and re-running `uv lock`. No canonical
document, digest, or schema changes: the reference case remains byte-stable, verified
directly. Should format validation ever be wanted, it must arrive as a deliberate,
changelog-announced tightening with `format-nongpl`, never with `format`.

### 2026-08-20 cryptography 46.0.7 to 50.0.0

`pip-audit` reported four advisories against the locked `cryptography` 46.0.7:
`GHSA-537c-gmf6-5ccf` (statically linked OpenSSL in the published wheels, fixed in 48.0.1),
`PYSEC-2026-3552` (PKCS#7 EnvelopedData Bleichenbacher oracle, fixed in 50.0.0),
`PYSEC-2026-3553` / CVE-2026-69249 (X.509 chain-building denial of service, fixed in
49.0.0), and `PYSEC-2026-3554` / CVE-2026-69248 (X.509 DNS name-constraint wildcard escape,
fixed in 49.0.0). No other locked Python or web package carried an advisory.

None of the four is reachable from OAK. `oak.adapters.signing`, `oak.runner.identity`, and
`oak.contracts.signatures` use raw-bytes Ed25519 only — generate, seed load, raw public and
private bytes, sign, and verify. OAK loads no X.509 certificate or chain, decrypts no PKCS#7
structure, and calls no serialization or key-loading API. The upgrade was taken anyway:
reachability is a property of today's call graph rather than a durable control, and this
component is the trust root for plan signatures, approvals, runner envelopes, and
extension-steward signatures. Only 50.0.0 clears all four; 48.0.1 clears one and 49.0.0
clears three. No advisory was suppressed and no `pip-audit` ignore list was introduced.

Verified from primary sources for 50.0.0: the licence expression remains
`Apache-2.0 OR BSD-3-Clause`, so the inventory row above is unchanged; supported Python is
3.9 to 3.14, covering the pinned 3.13.12; `cffi` is the only runtime requirement and the
lock already carries `cffi` 2.1.1 with `pycparser` 3.0, both advisory-free and unmoved by
this change; nothing else in `uv.lock` depends on `cryptography`, so the only edge is
downward.

Platform support narrowed. From 49.0.0 the project no longer publishes macOS x86_64 or
32-bit Windows wheels. `manylinux2014`, `manylinux_2_28`, and `manylinux_2_34` wheels are
published for x86_64 and aarch64, so `python:3.13.12-slim` resolves a wheel and the API
image still needs no Rust toolchain. macOS contributors now require an arm64 interpreter;
an Intel or Rosetta interpreter falls through to the source distribution and cannot build
without Rust.

Backwards-incompatible changes across 47.0.0 to 50.0.0 were reviewed against OAK's call
graph and none is reached: binary elliptic curves, OpenSSL 1.1.x, LibreSSL below 4.1, and
Python 3.8 support were removed; unsupported key loading now raises `UnsupportedAlgorithm`
and `public_bytes`/`private_bytes` raise `TypeError` where they previously raised
`ValueError`; ChaCha20 enforces RFC 7539 counter overflow; stricter X.509 and CRL parsing
rejects mismatched signature algorithms; and finite-field Diffie-Hellman is deprecated. The
two exception-type changes were checked explicitly, because `oak.contracts.signatures`
returns `False` rather than raising and its `except` clause is a fail-closed control: the
raw-bytes loaders it uses still raise `ValueError` on a wrong-length key, and
`tests/unit/test_signing.py` now pins that behaviour.

Ed25519 signatures are deterministic under RFC 8032 and are unchanged by this upgrade — a
fixed-seed signature is byte-identical before and after — so existing signed artifacts,
trust anchors, and canonical digests remain valid and no key rotation or re-signing is
required.

The replacement seam is unchanged: `SigningPort` for signing and `oak.contracts.signatures`
for verification. Rollback is reverting `pyproject.toml` and `uv.lock` together and
re-running `uv sync --frozen`, which restores 46.0.7 and returns `make audit` to a failing
state, so it is a temporary measure only.
