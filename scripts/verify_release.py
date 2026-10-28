# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-004: verify a set of downloaded OAK Community release artifacts.

This is the consumer-side half of `scripts/build_release.py`. It recomputes the SHA-256
of every file named in `SHA256SUMS` and refuses the release if anything disagrees.

It is deliberately standard-library only and has no OAK import, so it runs against a
downloaded directory on a machine where OAK is not installed — which is the situation a
verifier is actually in. `sha256sum -c SHA256SUMS` (GNU coreutils) or
`shasum -a 256 -c SHA256SUMS` (macOS) do the same job; this exists so the documented
procedure works identically on both, and so the failure modes can be tested.

What this proves and what it does not:

* It proves the bytes you have are the bytes the manifest describes.
* From `1.0.0` on, it also proves who released them (RR-005): the maintainer signs
  `SHA256SUMS` offline with an SSH key (`ssh-keygen -Y sign -n oak-release`), the
  signature ships beside it as `SHA256SUMS.sig`, and this checks it with
  `ssh-keygen -Y verify` against the public key pinned in the repository's
  `keys/allowed_signers`, never against anything inside the directory being verified.
  It fails closed: from `1.0.0` a missing signature, an unpinned key, a signature by any
  other key or over any other manifest, or no `ssh-keygen` to check it with, refuses the
  release. Releases before `1.0.0` (`0.7.1`, `0.9.0`) were published unsigned and verify
  by checksum alone, unless a signature is present, which must then verify.
* A signature binds who released the artifacts, not how they were built.

`--checksums-only` skips the signature, for the release build before it is signed, and
says so. Exit codes: 0 verified, 2 verification failed, 3 the manifest or a listed file is
missing or malformed, 4 the signature is missing, does not verify or cannot be checked.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

CHECKSUM_MANIFEST = "SHA256SUMS"
SIGNATURE = "SHA256SUMS.sig"
# The SSH signature namespace: a signature made for anything else does not verify here.
NAMESPACE = "oak-release"
SIGNED_FROM = (1, 0, 0)
DEFAULT_ALLOWED_SIGNERS = Path(__file__).resolve().parents[1] / "keys" / "allowed_signers"
_WHEEL = re.compile(r"oak_community-(?P<release>\d+(?:\.\d+)*)[^-]*-py3-none-any\.whl")
EXIT_OK = 0
EXIT_MISMATCH = 2
EXIT_MALFORMED = 3
EXIT_SIGNATURE = 4


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse(manifest_text: str) -> list[tuple[str, str]]:
    """Parse coreutils checksum lines: `<64 hex><two spaces><name>`.

    The manifest is untrusted input, not a trusted index: it arrives over the same
    channel as the artifacts it describes, so every field is validated before use.
    """

    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for number, line in enumerate(manifest_text.splitlines(), start=1):
        if not line.strip():
            continue
        expected, separator, name = line.partition("  ")
        if not separator or len(expected) != 64:
            raise ValueError(f"{CHECKSUM_MANIFEST}: malformed entry on line {number}")
        try:
            int(expected, 16)
        except ValueError as error:
            raise ValueError(
                f"{CHECKSUM_MANIFEST}: non-hexadecimal digest on line {number}"
            ) from error

        # Validate the name exactly as written, and never a normalized copy of it.
        # Stripping first and validating afterwards is precisely how a padded name
        # slips through: `<digest>` + the separator + ` /etc/passwd` is not absolute
        # as written, and the stripped form is the one that would be opened.
        if not name or name != name.strip():
            raise ValueError(f"{CHECKSUM_MANIFEST}: entry name is empty or padded on line {number}")
        if any(character in name for character in ("\x00", "\r")):
            raise ValueError(f"{CHECKSUM_MANIFEST}: entry name is not printable on line {number}")
        candidate = Path(name)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"{CHECKSUM_MANIFEST}: entry escapes the release directory: {name}")
        if name == CHECKSUM_MANIFEST:
            raise ValueError(f"{CHECKSUM_MANIFEST}: the manifest cannot verify itself")
        if name in seen:
            raise ValueError(f"{CHECKSUM_MANIFEST}: duplicate entry for {name}")
        seen.add(name)
        # `sha256sum -c` accepts either case; comparing case-sensitively would
        # report a perfectly good artifact as tampered with.
        entries.append((expected.lower(), name))
    if not entries:
        raise ValueError(f"{CHECKSUM_MANIFEST}: no entries")
    return entries


def _release(entries: list[tuple[str, str]]) -> tuple[int, ...] | None:
    """The release segment of the one wheel the manifest lists, or None."""

    found = [match for _, name in entries if (match := _WHEEL.fullmatch(name)) is not None]
    if len(found) != 1:
        return None
    return tuple(int(part) for part in found[0].group("release").split("."))


def _pinned_keys(allowed_signers: Path) -> int:
    lines = allowed_signers.read_text(encoding="utf-8").splitlines()
    return sum(1 for line in lines if line.strip() and not line.lstrip().startswith("#"))


def _check_signature(
    directory: Path, allowed_signers: Path, release: tuple[int, ...] | None
) -> int:
    """Verify `SHA256SUMS.sig` against the pinned key, where one is required or present."""

    signature = directory / SIGNATURE
    required = release is None or release >= SIGNED_FROM
    if not signature.exists():
        if required:
            print(
                f"{SIGNATURE}: not found; a release from 1.0.0 on must be signed",
                file=sys.stderr,
            )
            return EXIT_SIGNATURE
        print(
            f"{CHECKSUM_MANIFEST} is unsigned: releases before 1.0.0 were published unsigned "
            "(RR-005), so checksums prove the bytes match it, not who produced them."
        )
        return EXIT_OK
    root = directory.resolve()
    pinned = allowed_signers.resolve()
    if pinned.is_relative_to(root):
        print(
            f"{allowed_signers}: the pinned key cannot come from the release being verified",
            file=sys.stderr,
        )
        return EXIT_SIGNATURE
    if not signature.is_file() or signature.is_symlink() or not pinned.is_file():
        print(f"{SIGNATURE} or {allowed_signers}: not a regular file", file=sys.stderr)
        return EXIT_SIGNATURE
    if _pinned_keys(pinned) == 0:
        print(
            f"{allowed_signers}: no release signing key is pinned, so {SIGNATURE} "
            "cannot be checked",
            file=sys.stderr,
        )
        return EXIT_SIGNATURE
    keygen = shutil.which("ssh-keygen")
    if keygen is None:
        print("ssh-keygen is needed to check the signature and was not found", file=sys.stderr)
        return EXIT_SIGNATURE
    manifest = (directory / CHECKSUM_MANIFEST).read_bytes()
    found = subprocess.run(
        [keygen, "-Y", "find-principals", "-s", str(signature), "-f", str(pinned)],
        check=False,
        capture_output=True,
        text=True,
    )
    for principal in found.stdout.split():
        checked = subprocess.run(
            [
                keygen,
                "-Y",
                "verify",
                "-f",
                str(pinned),
                "-I",
                principal,
                "-n",
                NAMESPACE,
                "-s",
                str(signature),
            ],
            input=manifest,
            check=False,
            capture_output=True,
        )
        if checked.returncode == 0:
            print(
                f"{CHECKSUM_MANIFEST} is signed by {principal}, the key pinned in {allowed_signers}"
            )
            return EXIT_OK
    print(
        f"{SIGNATURE} does not verify {CHECKSUM_MANIFEST} under the key pinned in "
        f"{allowed_signers}. Do not install these artifacts.",
        file=sys.stderr,
    )
    return EXIT_SIGNATURE


def verify(
    directory: Path,
    *,
    allowed_signers: Path = DEFAULT_ALLOWED_SIGNERS,
    checksums_only: bool = False,
) -> int:
    manifest = directory / CHECKSUM_MANIFEST
    if not manifest.is_file():
        print(f"{manifest}: not found", file=sys.stderr)
        return EXIT_MALFORMED

    try:
        entries = _parse(manifest.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        print(str(error), file=sys.stderr)
        return EXIT_MALFORMED

    root = directory.resolve()
    failures: list[str] = []
    missing: list[str] = []
    for expected, name in entries:
        # Resolve before opening: a symlink placed inside the release directory is
        # another way for a manifest to name something that is not in it.
        artifact = (directory / name).resolve()
        if not artifact.is_relative_to(root):
            print(f"ESCAPES  {name}: resolves outside {root}", file=sys.stderr)
            return EXIT_MALFORMED
        if not artifact.is_file():
            missing.append(name)
            continue
        actual = _digest(artifact)
        if actual != expected:
            failures.append(f"{name}: expected sha256:{expected}, got sha256:{actual}")
        else:
            print(f"OK  {name}")

    for name in missing:
        print(f"MISSING  {name}", file=sys.stderr)
    for failure in failures:
        print(f"FAILED   {failure}", file=sys.stderr)

    if missing:
        return EXIT_MALFORMED
    if failures:
        print(
            f"\n{len(failures)} artifact(s) do not match {CHECKSUM_MANIFEST}. Do not install them.",
            file=sys.stderr,
        )
        return EXIT_MISMATCH

    covered = {name for _, name in entries}
    unlisted = sorted(
        path.name
        for path in directory.iterdir()
        if path.is_file() and path.name not in {CHECKSUM_MANIFEST, SIGNATURE, *covered}
    )
    for name in unlisted:
        print(
            f"UNLISTED {name}: present but not covered by {CHECKSUM_MANIFEST}",
            file=sys.stderr,
        )

    print(f"\nverified {len(entries)} artifact(s) against {CHECKSUM_MANIFEST}")
    if checksums_only:
        print(
            "Checksums prove the bytes match the manifest; who produced them was not "
            "checked (--checksums-only)."
        )
        return EXIT_OK
    return _check_signature(directory, allowed_signers, _release(entries))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify OAK Community release artifacts.")
    parser.add_argument(
        "directory", type=Path, help="directory holding the artifacts and SHA256SUMS"
    )
    parser.add_argument(
        "--allowed-signers",
        type=Path,
        default=DEFAULT_ALLOWED_SIGNERS,
        help="the pinned public key, from the repository at the release's tag",
    )
    parser.add_argument(
        "--checksums-only",
        action="store_true",
        help="check the checksums but not who signed them (the build, before signing)",
    )
    arguments = parser.parse_args()
    return verify(
        arguments.directory,
        allowed_signers=arguments.allowed_signers,
        checksums_only=arguments.checksums_only,
    )


if __name__ == "__main__":
    sys.exit(main())
