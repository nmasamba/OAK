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
* It also proves who released them (RR-005): the maintainer signs `SHA256SUMS` offline
  with an SSH key (`ssh-keygen -Y sign -n oak-release`), the signature ships beside it as
  `SHA256SUMS.sig`, and this checks it with `ssh-keygen -Y verify` against the public key
  pinned in the repository's `keys/allowed_signers`, never against anything inside the
  directory being verified. It fails closed: a missing signature, an unpinned key, a
  signature by any other key or over any other manifest, or no `ssh-keygen` to check it
  with, refuses the release. The only exceptions are the two releases published before
  signing began, `0.7.1` and `0.9.0`, recognised by the SHA-256 of the `SHA256SUMS` each
  was published with, never by a version the downloaded files claim; a signature beside
  either must still verify.
* A signature binds who released the artifacts, not how they were built.

`--checksums-only` skips the signature, for the release build before it is signed, and
says so. Exit codes: 0 verified, 2 verification failed, 3 the manifest or a listed file is
missing or malformed, 4 the signature is missing, does not verify or cannot be checked.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

CHECKSUM_MANIFEST = "SHA256SUMS"
SIGNATURE = "SHA256SUMS.sig"
# The SSH signature namespace: a signature made for anything else does not verify here.
NAMESPACE = "oak-release"
DEFAULT_ALLOWED_SIGNERS = Path(__file__).resolve().parents[1] / "keys" / "allowed_signers"
# The `SHA256SUMS` the releases published before signing began, as GitHub reports the
# digest of each release's asset. A manifest is unsigned-but-known only if it is one of these
# byte for byte; a version a downloaded file names is never consulted, because whoever
# controls the download controls the names.
UNSIGNED_RELEASES = {
    "b58b1026c4969f9c2a012789ba2310fb59e092ef5f0c65e3a7fad63493bca861": "0.7.1",
    "ee1c893bf128143b10ff97fbcf8531d43285190de5f331f2740763b000dc0aa9": "0.9.0",
}
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


def _pinned_keys(allowed_signers: Path) -> int:
    lines = allowed_signers.read_text(encoding="utf-8").splitlines()
    return sum(1 for line in lines if line.strip() and not line.lstrip().startswith("#"))


def _check_signature(directory: Path, allowed_signers: Path) -> int:
    """Verify `SHA256SUMS.sig` against the pinned key; only a known unsigned release may lack it."""

    signature = directory / SIGNATURE
    if not signature.exists():
        known = UNSIGNED_RELEASES.get(_digest(directory / CHECKSUM_MANIFEST))
        if known is None:
            print(
                f"{SIGNATURE}: not found; only {' and '.join(sorted(UNSIGNED_RELEASES.values()))} "
                "were published unsigned, and this is not their manifest",
                file=sys.stderr,
            )
            return EXIT_SIGNATURE
        print(
            f"{CHECKSUM_MANIFEST} is the unsigned manifest {known} was published with (RR-005), "
            "so checksums prove the bytes match it, not who produced them."
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
    for principal in (line.strip() for line in found.stdout.splitlines()):
        if not principal:
            continue
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
    return _check_signature(directory, allowed_signers)


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
