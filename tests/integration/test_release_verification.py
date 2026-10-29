# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-004: the published verification procedure must fail closed.

`docs/release-process.md` tells a consumer to verify downloaded artifacts against
`SHA256SUMS`. That instruction is only worth publishing if it actually refuses a
tampered artifact, so these tests tamper with one and require the refusal — rather than
asserting that verification succeeds on a good copy, which proves almost nothing.
"""

import hashlib
import os
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
    result = _verify(release, "--checksums-only")

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


def test_the_verifier_never_claims_unchecked_artifacts_are_signed(release: Path) -> None:
    """Checked by checksum alone, the release is not called signed."""

    result = _verify(release, "--checksums-only")

    assert "was not checked" in result.stdout
    assert "signed by" not in result.stdout


# OAK-V1-027 (RR-005): for every release after 0.9.0 the maintainer's SSH signature over
# SHA256SUMS is checked against the pinned key and nothing else. No real key is created or
# used: every key here is a throwaway generated inside the test.

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


@pytest.mark.parametrize(
    "wheel",
    [
        "oak_community-1.0.0-py3-none-any.whl",
        "oak_community-1.0-py3-none-any.whl",
        "oak_community-1!0.1.0-py3-none-any.whl",
        "oak_community-0.9.1-py3-none-any.whl",
        "oak_community-0.9.0-py3-none-any.whl",
    ],
)
def test_an_unsigned_release_is_refused_whatever_version_its_files_name(
    tmp_path: Path, maintainer: tuple[Path, Path], wheel: str
) -> None:
    """FC-1: an unsigned release is known only by its published manifest, never by a name."""

    directory = tmp_path / "unsigned"
    directory.mkdir()
    (directory / wheel).write_bytes(b"wheel-bytes")
    (directory / "SHA256SUMS").write_text(
        f"{hashlib.sha256(b'wheel-bytes').hexdigest()}  {wheel}\n", encoding="utf-8"
    )

    result = _verify(directory, "--allowed-signers", str(maintainer[1]))

    assert result.returncode == EXIT_SIGNATURE
    assert "SHA256SUMS.sig: not found" in result.stderr


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


def test_the_repository_pins_no_key_yet_so_a_signed_release_cannot_verify(
    release_one: Path, tmp_path: Path
) -> None:
    """Until the maintainer pins one when cutting 1.0.0, no new release verifies."""

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


def test_only_the_two_releases_published_unsigned_are_exempt() -> None:
    from scripts.verify_release import UNSIGNED_RELEASES

    assert sorted(UNSIGNED_RELEASES.values()) == ["0.7.1", "0.9.0"]
    assert all(re.fullmatch(r"[0-9a-f]{64}", digest) for digest in UNSIGNED_RELEASES)


def test_a_known_unsigned_manifest_verifies_but_not_with_a_bad_signature(
    release: Path,
    maintainer: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """0.7.1 and 0.9.0 were published unsigned; a signature beside one must still verify."""

    from scripts import verify_release

    manifest = hashlib.sha256((release / "SHA256SUMS").read_bytes()).hexdigest()
    monkeypatch.setattr(verify_release, "UNSIGNED_RELEASES", {manifest: "0.7.0-test"})

    assert verify_release.verify(release, allowed_signers=maintainer[1]) == EXIT_OK
    assert "unsigned manifest 0.7.0-test was published with" in capsys.readouterr().out

    _sign(release, _key(tmp_path / "other", "impostor"))
    assert verify_release.verify(release, allowed_signers=maintainer[1]) == EXIT_SIGNATURE


def test_a_principal_with_a_space_verifies(release_one: Path, tmp_path: Path) -> None:
    key = _key(tmp_path / "keys", "spaced")
    _sign(release_one, key)
    public = key.with_suffix(".pub").read_text(encoding="utf-8").split()
    allowed = tmp_path / "keys" / "allowed_signers"
    allowed.write_text(f'"OAK maintainer" {public[0]} {public[1]}\n', encoding="utf-8")

    result = _verify(release_one, "--allowed-signers", str(allowed))

    assert result.returncode == EXIT_OK, result.stderr
    assert "signed by OAK maintainer" in result.stdout


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


def test_a_key_hard_linked_out_of_the_release_is_never_used(
    release_one: Path, tmp_path: Path
) -> None:
    """The guard compares files, not spellings: a link out of the download is still in it
    (and so is a differently cased path on a case-insensitive file system)."""

    key = _key(tmp_path / "attacker", "attacker")
    _sign(release_one, key)
    (release_one / "nested").mkdir()
    for index, carried in enumerate(
        (
            _pin(release_one / "allowed_signers", key),
            _pin(release_one / "nested" / "allowed_signers", key),
        )
    ):
        linked = tmp_path / f"elsewhere-{index}" / "allowed_signers"
        linked.parent.mkdir()
        os.link(carried, linked)

        result = _verify(release_one, "--allowed-signers", str(linked))

        assert result.returncode == EXIT_SIGNATURE, carried
        assert "cannot come from the release being verified" in result.stderr


def test_an_ssh_keygen_that_cannot_look_up_the_signer_is_not_called_a_bad_signature(
    release_one: Path, maintainer: tuple[Path, Path], tmp_path: Path
) -> None:
    """OpenSSH 8.1 verifies but has no `-Y find-principals`; that is not a forgery."""

    key, allowed = maintainer
    _sign(release_one, key)
    old = tmp_path / "openssh-8.1" / "ssh-keygen"
    old.parent.mkdir()
    old.write_text("#!/bin/sh\necho 'unknown option -- Y find-principals' >&2\nexit 1\n")
    old.chmod(0o755)

    result = subprocess.run(
        [sys.executable, str(VERIFIER), str(release_one), "--allowed-signers", str(allowed)],
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": str(old.parent)},
    )

    assert result.returncode == EXIT_SIGNATURE
    assert "OpenSSH 8.2 or later is needed" in result.stderr
    assert "Do not install" not in result.stderr
