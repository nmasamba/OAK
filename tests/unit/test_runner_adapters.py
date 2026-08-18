# SPDX-License-Identifier: Apache-2.0
"""OAK-S5-005/006 adapter argv safety and injection resistance."""

import pytest

from oak.domain import OAKError
from oak.runner.adapters import CommandResult, ContainerFixtureAdapter, collect_inventory


def _recording_executor() -> tuple[list, ContainerFixtureAdapter]:
    calls: list[tuple[str, ...]] = []

    def executor(argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
        calls.append(argv)
        return CommandResult(returncode=0, stdout="", stderr="")

    return calls, ContainerFixtureAdapter(executor)


def test_apply_builds_a_fixed_allowlisted_argv() -> None:
    calls, adapter = _recording_executor()
    adapter.apply(
        {
            "container_name": "oak-fixture-demo",
            "image_reference": "postgres:17.6-alpine",
            "image_digest": "sha256:" + "e" * 64,
            "isolation": "network-none-never-started",
        },
        120,
    )
    argv = calls[0]
    assert argv[0] == "docker"
    assert "create" in argv and "--network=none" in argv
    assert "--name" in argv and "oak-fixture-demo" in argv
    assert argv[-1] == "postgres:17.6-alpine@sha256:" + "e" * 64
    assert not any(part.startswith("--rm=") or ";" in part or "&&" in part for part in argv)


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
