<!-- SPDX-License-Identifier: Apache-2.0 -->

# Container image scan — OAK Community 0.7.0

`OAK-S8-003` asks for dependency **and container** scans. The dependency half was done
throughout the sprint; this is the container half, which was initially missed and recorded
as `RR-035`. It found real problems, so this document records what was found, what was
fixed, and what is left.

Reproduce with:

```bash
make scan-images
```

| | |
|---|---|
| Scanner | `aquasec/trivy:0.74.0`, pinned |
| Platform | `linux/amd64` |
| Method | `docker save` to a tarball, scanned by the scanner container |
| Report | [container-scan.json](container-scan.json) |

The scanner is never given the Docker socket. A scanner container holding the daemon
socket holds the daemon, which is a poor trade for a tool whose job is to tell you about
risk — so the images are exported and the tarball is what gets read.

## What the first scan found

| Image | CRITICAL | HIGH | MEDIUM | LOW |
|---|---|---|---|---|
| API | 6 | 72 | 119 | 109 |
| Web | 3 | 33 | 54 | 48 |

Three distinct causes, not one:

1. **`uv` and `uvx` were shipping in the runtime layer.** The API image was a single stage,
   so the build tool stayed in the delivered image, carrying three HIGH advisories each in
   its vendored Rust dependencies (`quinn-proto`, `rustls-webpki`) plus one in `uv` itself.
   OAK never invokes `uv` at run time.
2. **The base images lag their distributions' patch streams.** This is the one that would
   have been easy to get wrong: the pinned digests were checked against the registry and
   found to be **current for their tags**. Re-pinning would have changed nothing. The
   upstream `python:3.13.12-slim` and `nginx:1.29.1-alpine` images simply had not been
   rebuilt since their distributions published fixes — including a CRITICAL OpenSSL
   (`CVE-2026-31789`) fixed in both Debian and Alpine.
3. **A residue with no vendor fix at all**, dominated by `perl-base`.

## What changed

- **The API image is now multi-stage.** `uv` builds the virtual environment in a build
  stage; the runtime stage copies only `/app/.venv`. `uv`, `uvx` and the source tree no
  longer ship. Verified afterwards: all six console scripts resolve, and canonical schemas,
  the catalogue, migrations and policy packs all resolve from inside the installed package
  rather than from a copied source tree.
- **Both images apply their distribution's security updates** (`apt-get upgrade`,
  `apk upgrade`). This costs build-time determinism — image contents now depend on when the
  build ran. OAK does not claim byte-reproducible images (`RR-006`), and shipping a
  known-fixed CRITICAL is the worse trade. It is a real cost and it is recorded, not waved
  away.

## Where it ended

| Image | CRITICAL | HIGH | MEDIUM | LOW | Fixable CRITICAL/HIGH |
|---|---|---|---|---|---|
| API | 3 | 14 | 49 | 58 | **0** |
| Web | **0** | **0** | **0** | **0** | **0** |

The API image also dropped from 428 MB to 373 MB, and Debian moved 13.4 → 13.6.

**Every remaining CRITICAL and HIGH has no vendor fix published.** There is nothing left to
apply:

| Package | Findings |
|---|---|
| `perl-base` | 3 CRITICAL, 5 HIGH |
| `openssl`, `libssl3t64`, `openssl-provider-legacy` | 1 HIGH each (`CVE-2026-14456`) |
| `ncurses-base`, `ncurses-bin`, `libncursesw6`, `libtinfo6` | 1 HIGH each (`CVE-2025-69720`) |
| `gzip` | 1 HIGH (`CVE-2026-41992`) |
| `libacl1` | 1 HIGH (`CVE-2026-54369`) |

`perl-base` accounts for all three remaining CRITICALs. It is an Essential Debian package
inherited from the Python base image; OAK never invokes Perl, and the runner's only
subprocess is a fixed allowlisted `docker` argument vector. Removing an Essential package
from a Debian image risks breaking `dpkg` itself, so it stays and is recorded as `RR-036`
rather than forced out at release time.

## The gate

`make scan-images` fails the build on **fixable** CRITICAL or HIGH findings and reports
unfixable ones without failing. That asymmetry is deliberate: a finding nobody can act on,
blocking a build, gets suppressed within a week, and a suppressed gate protects nothing.
`tests/contract/test_image_scan_gate.py` pins both halves so neither can quietly invert.

The gate is **not** part of `make check`. It needs Docker and network, which `make check`
deliberately does not, and it belongs to the release procedure — see
[release-process.md](../../release-process.md).
