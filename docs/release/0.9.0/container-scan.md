<!-- SPDX-License-Identifier: Apache-2.0 -->

# Container image scan — OAK Community 0.9.0

The `0.9.0` scan, run on 2026-09-30 from a clean tree at `c067aad` (the version commit,
after Sprint 11 merged). Since `v0.8.0`, no Dockerfile, no base pin and no dependency has
changed. The image inputs that did change are the version string in `VERSION`,
`pyproject.toml`, `uv.lock`, `package.json` and `web/package.json`, the rewritten
`README.md`, and OAK's own source. The package *names* are the `0.8.0` set, but the
build-time distribution upgrade moved some versions:
- in the API image, four Debian packages went from `deb13u2` to `deb13u3`: `openssl`,
  `libssl3t64`, `openssl-provider-legacy` and `libpcre2-8-0`;
- in the web image, `libexpat` went from `2.8.4-r0` to `2.8.5-r0`.

What differs below reflects both those updates and advisories published since the `0.8.0`
scan. The `0.8.0` record is at
[../0.8.0/container-scan.md](../0.8.0/container-scan.md).

Reproduce with:

```bash
make scan-images
```

| | |
|---|---|
| Scanner | `aquasec/trivy:0.74.0`, pinned |
| Platform | `linux/amd64` |
| Method | `docker save` to a tarball, scanned by the scanner container |
| Build | `--no-cache --pull`, so the build-time distribution upgrade ran today rather than from a cached layer |
| Report | [container-scan.json](container-scan.json) |
| SBOMs | [oak-community-api-image-0.9.0.cdx.json](oak-community-api-image-0.9.0.cdx.json), [oak-community-web-image-0.9.0.cdx.json](oak-community-web-image-0.9.0.cdx.json) |
| Provenance | [image-provenance.json](image-provenance.json) — unsigned, excluded from checksums by design |

The scanner is never given the Docker socket. The SBOMs come from the same pinned scanner
and the same exported tarball as the vulnerability scan, so they describe the image that
ships, including its final-stage base, and not a build stage.

## Results

| Image | CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN | Fixable CRITICAL/HIGH |
|---|---|---|---|---|---|---|
| API | **0** | 44 | 59 | 60 | 2 | **0** |
| Web | **0** | **0** | **0** | **0** | **0** | **0** |

**Zero fixable findings**, which is what the gate judges. Debian has published no fix for
any of the API image's 44 HIGH findings.

## What moved since 0.8.0

- **The HIGH set is identical.** It is the same 44 package instances as at `0.8.0`, and
  the same eight distinct advisories:
  - four `util-linux` advisories (`CVE-2026-76642`, `CVE-2026-78408`, `CVE-2026-78409`,
    `CVE-2026-78410`), each reported against the nine packages Debian builds from that
    source, which accounts for 36 of the 44;
  - one `systemd` advisory (`CVE-2026-16742`), against `libsystemd0` and `libudev1`;
  - one `ncurses` advisory (`CVE-2025-69720`), against the four `ncurses` packages;
  - one each for `libacl1` (`CVE-2026-54369`) and `perl-base` (`CVE-2026-9538`).
- **MEDIUM rose from 53 to 59 and LOW from 58 to 60.** The gate does not judge these
  severities. The report records neither which advisories they are nor whether any has a
  fix. The movement may come from advisories published since the `0.8.0` scan, from the
  package updates this rebuild picked up, or both.

The 44 HIGH findings are counted per *package instance*, not per defect. This residue is
the set `RR-036` records. The API image is Debian-based and inherits its distribution's
patch cadence. Rebuilding picks up whatever Debian has published, which is why the scan is
a release step and not a pinned artefact.

The web image (`nginxinc/nginx-unprivileged:1.29.1-alpine`, running as uid 101) still
reports **no findings at any severity**.

## The gate

The gate is unchanged:
- `make scan-images` fails on **fixable** CRITICAL or HIGH findings, and reports
  unfixable ones without failing.
- `tests/contract/test_image_scan_gate.py` pins both halves.
- The gate stays out of `make check`, because it needs Docker and the network.
- The release workflow's `images` job runs this same script, so a fixable finding fails
  the release build as well as this local run.
