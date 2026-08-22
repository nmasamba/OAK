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
* It does **not** prove who produced them. OAK Community release artifacts are
  unsigned; a manifest and the artifacts beside it can both be replaced by anyone who
  controls the channel you fetched them over. Obtain `SHA256SUMS` over a channel you
  trust independently of the artifacts, or compare against the digests published in the
  release notes.

Exit codes: 0 verified, 2 verification failed, 3 the manifest or a listed file is
missing or malformed.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

CHECKSUM_MANIFEST = "SHA256SUMS"
EXIT_OK = 0
EXIT_MISMATCH = 2
EXIT_MALFORMED = 3


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


def verify(directory: Path) -> int:
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
        if path.is_file() and path.name != CHECKSUM_MANIFEST and path.name not in covered
    )
    for name in unlisted:
        print(
            f"UNLISTED {name}: present but not covered by {CHECKSUM_MANIFEST}",
            file=sys.stderr,
        )

    print(f"\nverified {len(entries)} artifact(s) against {CHECKSUM_MANIFEST}")
    print(
        "Checksums prove the bytes match the manifest. They do not prove who produced "
        "them: OAK Community release artifacts are unsigned."
    )
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify OAK Community release artifacts.")
    parser.add_argument(
        "directory", type=Path, help="directory holding the artifacts and SHA256SUMS"
    )
    arguments = parser.parse_args()
    return verify(arguments.directory)


if __name__ == "__main__":
    sys.exit(main())
