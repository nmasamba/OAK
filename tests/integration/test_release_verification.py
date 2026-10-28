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


def _verify(directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFIER), str(directory), *arguments],
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


# OAK-V1-027 (RR-005): from 1.0.0 the maintainer's SSH signature over SHA256SUMS is checked
# against the pinned key and nothing else. No real key is created or used: every key here is
# a throwaway generated inside the test.

EXIT_SIGNATURE = 4


def _key(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    key = directory / name
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(key)], check=True
    )
    return key


def _pin(allowed: Path, key: Path, principal: str = "maintainer@example.invalid") -> Path:
    public = key.with_suffix(".pub").read_text(encoding="utf-8").split()
    allowed.write_text(f"# pinned\n{principal} {public[0]} {public[1]}\n", encoding="utf-8")
    return allowed


def _sign(release: Path, key: Path, namespace: str = "oak-release") -> None:
    subprocess.run(
        [
            "ssh-keygen",
            "-q",
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            namespace,
            str(release / "SHA256SUMS"),
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def release_one(tmp_path: Path) -> Path:
    """A well-formed 1.0.0 release directory, not yet signed."""

    directory = tmp_path / "release-1.0.0"
    directory.mkdir()
    contents = {
        "oak_community-1.0.0-py3-none-any.whl": b"wheel-bytes",
        "oak_community-1.0.0.tar.gz": b"sdist-bytes",
    }
    lines = []
    for name, payload in sorted(contents.items()):
        (directory / name).write_bytes(payload)
        lines.append(f"{hashlib.sha256(payload).hexdigest()}  {name}")
    (directory / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return directory


@pytest.fixture
def maintainer(tmp_path: Path) -> tuple[Path, Path]:
    key = _key(tmp_path / "keys", "maintainer")
    return key, _pin(tmp_path / "keys" / "allowed_signers", key)


def test_a_release_signed_by_the_pinned_key_verifies(
    release_one: Path, maintainer: tuple[Path, Path]
) -> None:
    key, allowed = maintainer
    _sign(release_one, key)

    result = _verify(release_one, "--allowed-signers", str(allowed))

    assert result.returncode == EXIT_OK, result.stderr
    assert "signed by maintainer@example.invalid" in result.stdout
    assert "UNLISTED" not in result.stderr


def test_an_unsigned_release_from_1_0_0_on_is_refused(
    release_one: Path, maintainer: tuple[Path, Path]
) -> None:
    result = _verify(release_one, "--allowed-signers", str(maintainer[1]))

    assert result.returncode == EXIT_SIGNATURE
    assert "must be signed" in result.stderr


def test_a_signature_by_another_key_is_refused(
    release_one: Path, maintainer: tuple[Path, Path], tmp_path: Path
) -> None:
    _sign(release_one, _key(tmp_path / "other", "impostor"))

    result = _verify(release_one, "--allowed-signers", str(maintainer[1]))

    assert result.returncode == EXIT_SIGNATURE
    assert "does not verify" in result.stderr


def test_a_signature_over_another_manifest_is_refused(
    release_one: Path, maintainer: tuple[Path, Path]
) -> None:
    """Replacing an artifact and its manifest line together keeps the checksums whole."""

    key, allowed = maintainer
    _sign(release_one, key)
    wheel = release_one / "oak_community-1.0.0-py3-none-any.whl"
    wheel.write_bytes(b"other-wheel-bytes")
    manifest = release_one / "SHA256SUMS"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            hashlib.sha256(b"wheel-bytes").hexdigest(),
            hashlib.sha256(b"other-wheel-bytes").hexdigest(),
        ),
        encoding="utf-8",
    )

    result = _verify(release_one, "--allowed-signers", str(allowed))

    assert result.returncode == EXIT_SIGNATURE
    assert "OK  oak_community-1.0.0-py3-none-any.whl" in result.stdout


def test_a_signature_made_for_another_namespace_is_refused(
    release_one: Path, maintainer: tuple[Path, Path]
) -> None:
    key, allowed = maintainer
    _sign(release_one, key, namespace="file")

    assert _verify(release_one, "--allowed-signers", str(allowed)).returncode == EXIT_SIGNATURE


def test_with_no_key_pinned_a_signed_release_cannot_verify(
    release_one: Path, maintainer: tuple[Path, Path]
) -> None:
    key, allowed = maintainer
    _sign(release_one, key)
    allowed.write_text("# no key pinned yet\n", encoding="utf-8")

    result = _verify(release_one, "--allowed-signers", str(allowed))

    assert result.returncode == EXIT_SIGNATURE
    assert "no release signing key is pinned" in result.stderr


def test_the_repository_pins_no_key_yet_so_a_1_0_0_release_cannot_verify(
    release_one: Path, tmp_path: Path
) -> None:
    """Until the maintainer pins one when cutting 1.0.0, nothing from 1.0.0 verifies."""

    _sign(release_one, _key(tmp_path / "anyone", "anyone"))

    result = _verify(release_one)

    assert result.returncode == EXIT_SIGNATURE


def test_a_key_carried_inside_the_release_is_never_used(release_one: Path, tmp_path: Path) -> None:
    key = _key(tmp_path / "attacker", "attacker")
    _sign(release_one, key)
    carried = _pin(release_one / "allowed_signers", key)

    result = _verify(release_one, "--allowed-signers", str(carried))

    assert result.returncode == EXIT_SIGNATURE
    assert "cannot come from the release being verified" in result.stderr


def test_a_release_before_1_0_0_verifies_unsigned_but_not_with_a_bad_signature(
    release: Path, maintainer: tuple[Path, Path], tmp_path: Path
) -> None:
    """0.7.1 and 0.9.0 were published unsigned; a signature beside one must still verify."""

    unsigned = _verify(release, "--allowed-signers", str(maintainer[1]))
    assert unsigned.returncode == EXIT_OK, unsigned.stderr
    assert "unsigned" in unsigned.stdout

    _sign(release, _key(tmp_path / "other", "impostor"))
    assert _verify(release, "--allowed-signers", str(maintainer[1])).returncode == EXIT_SIGNATURE


def test_a_manifest_naming_no_wheel_must_be_signed(
    release_one: Path, maintainer: tuple[Path, Path]
) -> None:
    """With no version to read, the signature is required: the rule fails closed."""

    manifest = release_one / "SHA256SUMS"
    lines = manifest.read_text(encoding="utf-8").splitlines()
    manifest.write_text("\n".join(line for line in lines if ".whl" not in line) + "\n", "utf-8")
    (release_one / "oak_community-1.0.0-py3-none-any.whl").unlink()

    assert _verify(release_one, "--allowed-signers", str(maintainer[1])).returncode == (
        EXIT_SIGNATURE
    )


def test_checksums_only_says_the_signature_was_not_checked(release_one: Path) -> None:
    result = _verify(release_one, "--checksums-only")

    assert result.returncode == EXIT_OK, result.stderr
    assert "was not checked (--checksums-only)" in result.stdout


def test_without_ssh_keygen_a_signature_cannot_be_checked(
    release_one: Path, maintainer: tuple[Path, Path]
) -> None:
    key, allowed = maintainer
    _sign(release_one, key)

    result = subprocess.run(
        [sys.executable, str(VERIFIER), str(release_one), "--allowed-signers", str(allowed)],
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": "/nonexistent"},
    )

    assert result.returncode == EXIT_SIGNATURE
    assert "ssh-keygen is needed" in result.stderr
