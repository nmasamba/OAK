# SPDX-License-Identifier: Apache-2.0
"""OAK-S5-005/006 adapter argv safety and injection resistance, and the OAK-PL-005
resolved-digest admission check (RR-003)."""

import pytest

from oak.domain import OAKError
from oak.domain.runner_adapters import registry_host
from oak.runner.adapters import CommandResult, ContainerFixtureAdapter, collect_inventory

DIGEST = "sha256:" + "e" * 64


def _recording_executor(
    *, repo_digests: str = f'["postgres@{DIGEST}"]'
) -> tuple[list, ContainerFixtureAdapter]:
    """A fake docker that records argv and answers the post-create inspections."""

    calls: list[tuple[str, ...]] = []

    def executor(argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
        calls.append(argv)
        if argv[:2] == ("docker", "inspect"):
            return CommandResult(returncode=0, stdout="sha256:imageid\n", stderr="")
        if argv[:3] == ("docker", "image", "inspect"):
            return CommandResult(returncode=0, stdout=repo_digests + "\n", stderr="")
        return CommandResult(returncode=0, stdout="", stderr="")

    return calls, ContainerFixtureAdapter(executor)


def test_apply_builds_a_fixed_allowlisted_argv() -> None:
    calls, adapter = _recording_executor()
    adapter.apply(
        {
            "container_name": "oak-fixture-demo",
            "image_reference": "postgres:17.6-alpine",
            "image_digest": DIGEST,
            "isolation": "network-none-never-started",
        },
        120,
    )
    argv = calls[0]
    assert argv[0] == "docker"
    assert "create" in argv and "--network=none" in argv
    assert "--name" in argv and "oak-fixture-demo" in argv
    assert argv[-1] == "postgres:17.6-alpine@" + DIGEST
    assert not any(part.startswith("--rm=") or ";" in part or "&&" in part for part in argv)


def _apply(adapter: ContainerFixtureAdapter) -> dict:
    return adapter.apply(
        {
            "container_name": "oak-fixture-demo",
            "image_reference": "postgres:17.6-alpine",
            "image_digest": DIGEST,
            "isolation": "network-none-never-started",
        },
        120,
    )


def test_apply_verifies_the_resolved_digest_and_reports_it() -> None:
    calls, adapter = _recording_executor()
    result = _apply(adapter)
    assert result["resolved_image_digest"] == DIGEST
    assert ("docker", "inspect", "--format", "{{.Image}}", "oak-fixture-demo") in calls
    assert any(argv[:3] == ("docker", "image", "inspect") for argv in calls)


def test_apply_removes_the_container_when_the_resolved_digest_differs() -> None:
    """The daemon resolving a different image than approved is denial, not evidence."""

    calls, adapter = _recording_executor(repo_digests='["postgres@sha256:' + "f" * 64 + '"]')
    with pytest.raises(OAKError) as caught:
        _apply(adapter)
    assert caught.value.code == "OAK-RUNNER-IMAGE"
    assert calls[-1] == ("docker", "rm", "--force", "oak-fixture-demo")


def test_apply_fails_closed_when_the_image_has_no_repo_digest() -> None:
    """A tarball-loaded image has no RepoDigests and cannot prove its identity."""

    calls, adapter = _recording_executor(repo_digests="[]")
    with pytest.raises(OAKError) as caught:
        _apply(adapter)
    assert caught.value.code == "OAK-RUNNER-IMAGE"
    assert calls[-1] == ("docker", "rm", "--force", "oak-fixture-demo")


def test_apply_fails_closed_when_the_inspection_itself_fails() -> None:
    calls: list[tuple[str, ...]] = []

    def executor(argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
        calls.append(argv)
        if argv[:2] == ("docker", "inspect"):
            return CommandResult(returncode=1, stdout="", stderr="no such container")
        return CommandResult(returncode=0, stdout="", stderr="")

    with pytest.raises(OAKError) as caught:
        _apply(ContainerFixtureAdapter(executor))
    assert caught.value.code == "OAK-RUNNER-IMAGE"
    assert calls[-1] == ("docker", "rm", "--force", "oak-fixture-demo")


def test_an_inspection_timeout_removes_the_container_and_denies() -> None:
    """The audit's enforcement finding, as a regression.

    A TimeoutExpired raised mid-inspection used to escape apply() before any removal
    ran: the unverified container survived and the raw exception killed the runner.
    Now any failure between create and a verified digest removes the container and
    denies with a stable code.
    """

    import subprocess

    calls: list[tuple[str, ...]] = []

    def executor(argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
        calls.append(argv)
        if argv[:2] == ("docker", "inspect"):
            raise subprocess.TimeoutExpired(cmd=argv, timeout=timeout_seconds)
        return CommandResult(returncode=0, stdout="", stderr="")

    with pytest.raises(OAKError) as caught:
        _apply(ContainerFixtureAdapter(executor))
    assert caught.value.code == "OAK-RUNNER-IMAGE"
    assert calls[-1] == ("docker", "rm", "--force", "oak-fixture-demo")


def test_a_subprocess_failure_becomes_a_typed_denial_not_a_traceback() -> None:
    """TimeoutExpired and OSError from any docker call surface as OAK-RUNNER-SUBPROCESS."""

    import subprocess

    def executor(argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
        raise subprocess.TimeoutExpired(cmd=argv, timeout=timeout_seconds)

    with pytest.raises(OAKError) as caught:
        _apply(ContainerFixtureAdapter(executor))
    assert caught.value.code == "OAK-RUNNER-SUBPROCESS"


@pytest.mark.parametrize(
    ("reference", "host"),
    [
        ("postgres:17.6-alpine", "docker.io"),
        ("library/postgres", "docker.io"),
        ("ghcr.io/acme/tool:1", "ghcr.io"),
        ("localhost/tool", "localhost"),
        ("localhost:5000/tool", "localhost:5000"),
        ("registry.example.internal/team/tool", "registry.example.internal"),
        ("host:8443/tool", "host:8443"),
    ],
)
def test_registry_host_follows_docker_resolution_rules(reference: str, host: str) -> None:
    assert registry_host(reference) == host


@pytest.mark.parametrize(
    "container_name",
    ["oak-fixture-a; rm -rf /", "oak-fixture-$(whoami)", "evil", "oak-fixture-A", "../escape"],
)
def test_injection_in_container_name_is_rejected(container_name: str) -> None:
    _, adapter = _recording_executor()
    with pytest.raises(OAKError, match="container name is not permitted"):
        adapter.apply(
            {
                "container_name": container_name,
                "image_reference": "postgres:17.6-alpine",
                "image_digest": "sha256:" + "e" * 64,
                "isolation": "network-none-never-started",
            },
            120,
        )


@pytest.mark.parametrize(
    "image_reference",
    ["--privileged", "postgres; touch /tmp/x", "postgres $(id)", "-v/etc:/etc"],
)
def test_injection_in_image_reference_is_rejected(image_reference: str) -> None:
    _, adapter = _recording_executor()
    with pytest.raises(OAKError, match="image reference is not permitted"):
        adapter.apply(
            {
                "container_name": "oak-fixture-demo",
                "image_reference": image_reference,
                "image_digest": "sha256:" + "e" * 64,
                "isolation": "network-none-never-started",
            },
            120,
        )


def test_rollback_tolerates_a_missing_container() -> None:
    def executor(argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
        return CommandResult(returncode=1, stdout="", stderr="Error: No such container: x")

    adapter = ContainerFixtureAdapter(executor)
    result = adapter.rollback(
        {
            "container_name": "oak-fixture-demo",
            "image_reference": "postgres:17.6-alpine",
            "image_digest": "sha256:" + "e" * 64,
            "isolation": "network-none-never-started",
        },
        120,
    )
    assert result["removed"] is True


def test_inventory_is_bounded_and_secret_free() -> None:
    inventory = collect_inventory()
    assert set(inventory) == {
        "operating_system",
        "architecture",
        "cpu_count",
        "ram_gib",
        "storage_gib",
    }
    serialized = str(inventory).casefold()
    assert "password" not in serialized and "token" not in serialized


def test_renderer_pins_images_to_the_attested_digest_not_the_reference() -> None:
    """A reference carrying a different digest must never be rendered.

    The attested ``artifact.digest`` is the authority; Sprint 5 fixed the same
    class in the container adapter, where a reference-carried digest could run an
    image the approval never covered.
    """

    from oak.adapters.deployment.helm_kubernetes import _pinned_image
    from oak.domain import OAKError

    good = "sha256:" + "b" * 64
    assert _pinned_image({"reference": "registry.example.invalid/x", "digest": good}) == (
        f"registry.example.invalid/x@{good}"
    )
    assert (
        _pinned_image({"reference": f"registry.example.invalid/x@{good}", "digest": good})
        == f"registry.example.invalid/x@{good}"
    )

    with pytest.raises(OAKError) as mismatch:
        _pinned_image(
            {
                "reference": "registry.example.invalid/x@sha256:" + "c" * 64,
                "digest": good,
            }
        )
    assert mismatch.value.code == "OAK-RENDER-IMAGE"
