# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-004: the published verification procedure must fail closed.

`docs/release-process.md` tells a consumer to verify downloaded artifacts against
`SHA256SUMS`. That instruction is only worth publishing if it actually refuses a
tampered artifact, so these tests tamper with one and require the refusal — rather than
asserting that verification succeeds on a good copy, which proves almost nothing.
"""

import hashlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "scripts" / "verify_release.py"
COREUTILS_LINE = re.compile(r"^[0-9a-f]{64}  \S.*$")

EXIT_OK = 0
EXIT_MISMATCH = 2
EXIT_MALFORMED = 3

pytestmark = pytest.mark.integration


def _verify(directory: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFIER), str(directory)],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def release(tmp_path: Path) -> Path:
    """A minimal, well-formed release directory."""

    directory = tmp_path / "release"
    directory.mkdir()
    contents = {
        "oak_community-0.7.0-py3-none-any.whl": b"wheel-bytes",
        "oak_community-0.7.0.tar.gz": b"sdist-bytes",
        "oak-community-0.7.0.cdx.json": b'{"bomFormat": "CycloneDX"}',
    }
    lines = []
    for name, payload in sorted(contents.items()):
        (directory / name).write_bytes(payload)
        lines.append(f"{hashlib.sha256(payload).hexdigest()}  {name}")
    (directory / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return directory


def test_an_untouched_release_verifies(release: Path) -> None:
    result = _verify(release)

    assert result.returncode == EXIT_OK, result.stderr
    assert "verified 3 artifact(s)" in result.stdout


def test_the_manifest_is_coreutils_compatible(release: Path) -> None:
    """The docs offer `sha256sum -c` / `shasum -c` as the no-OAK-installed path."""

    lines = (release / "SHA256SUMS").read_text(encoding="utf-8").splitlines()

    assert lines
    for line in lines:
        assert COREUTILS_LINE.match(line), line


def test_a_tampered_artifact_is_refused(release: Path) -> None:
    """One flipped byte must be enough."""

    wheel = release / "oak_community-0.7.0-py3-none-any.whl"
    wheel.write_bytes(wheel.read_bytes() + b"\x00")

    result = _verify(release)

    assert result.returncode == EXIT_MISMATCH
    assert "FAILED" in result.stderr
    assert "Do not install them." in result.stderr


def test_a_substituted_artifact_is_refused(release: Path) -> None:
    """Same length, different content — a length check would not catch this."""

    wheel = release / "oak_community-0.7.0-py3-none-any.whl"
    wheel.write_bytes(b"whee1-bytes")

    result = _verify(release)

    assert result.returncode == EXIT_MISMATCH


def test_a_missing_artifact_is_refused_rather_than_skipped(release: Path) -> None:
    """A removed artifact must not silently reduce the verified set."""

    (release / "oak_community-0.7.0.tar.gz").unlink()

    result = _verify(release)

    assert result.returncode == EXIT_MALFORMED
    assert "MISSING" in result.stderr


def test_an_absent_manifest_is_refused(tmp_path: Path) -> None:
    empty = tmp_path / "release"
    empty.mkdir()

    result = _verify(empty)

    assert result.returncode == EXIT_MALFORMED
    assert "not found" in result.stderr


def test_an_empty_manifest_is_refused_rather_than_vacuously_passing(release: Path) -> None:
    """Zero entries verified is not the same as everything verified."""

    (release / "SHA256SUMS").write_text("\n\n", encoding="utf-8")

    result = _verify(release)

    assert result.returncode == EXIT_MALFORMED
    assert "no entries" in result.stderr


@pytest.mark.parametrize(
    "manifest",
    [
        "not-a-digest  oak_community-0.7.0.tar.gz\n",
        "zzzz5a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f  x.whl\n",
        "abc  oak_community-0.7.0.tar.gz\n",
        "0000000000000000000000000000000000000000000000000000000000000000\n",
    ],
)
def test_a_malformed_manifest_is_refused(release: Path, manifest: str) -> None:
    (release / "SHA256SUMS").write_text(manifest, encoding="utf-8")

    result = _verify(release)

    assert result.returncode == EXIT_MALFORMED


@pytest.mark.parametrize(
    "name",
    ["../outside.txt", "/etc/hosts", "nested/../../escape.whl"],
)
def test_a_manifest_entry_cannot_escape_the_release_directory(release: Path, name: str) -> None:
    """The manifest is untrusted input, not a trusted index.

    A hostile manifest that names a path outside the download directory would make
    verification report on a file the publisher never shipped.
    """

    digest = hashlib.sha256(b"anything").hexdigest()
    (release / "SHA256SUMS").write_text(f"{digest}  {name}\n", encoding="utf-8")

    result = _verify(release)

    assert result.returncode == EXIT_MALFORMED
    assert "escapes the release directory" in result.stderr


def test_the_verifier_never_claims_the_artifacts_are_signed(release: Path) -> None:
    """The release is unsigned; the tool must not let a reader infer otherwise."""

    result = _verify(release)

    assert "unsigned" in result.stdout
    assert "signature" not in result.stdout.lower()
