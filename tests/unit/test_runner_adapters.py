# SPDX-License-Identifier: Apache-2.0
"""The topology installer: argv safety, idempotent install, the smoke test, verified
removal, and the resolved-digest admission check (RR-003).

OAK-S5-005/006 established the fixed argv and injection resistance; OAK-S11-002/003
make the adapter install one container per node, adopt only its own, deny a foreign
one, start and smoke-test only where the profile acknowledges it, and prove removal.
"""

from datetime import UTC, datetime, timedelta

import pytest

from oak.domain import OAKError
from oak.domain.runner_adapters import (
    HARDENING_FLAGS,
    ISOLATION_NEVER_STARTED,
    ISOLATION_STARTED_HARDENED,
    container_name_for,
    registry_host,
)
from oak.runner.adapters import (
    AdapterFailureError,
    CommandResult,
    ContainerFixtureAdapter,
    collect_inventory,
)
from tests.container_support import (
    CASE_ID,
    DIGEST,
    IMAGE,
    INSTALLATION_ID,
    FakeClock,
    FakeDocker,
    names,
    owned_labels,
    parameters,
)

FORBIDDEN_ARGUMENTS = {
    "exec",
    "logs",
    "run",
    "cp",
    "commit",
    "attach",
    "-p",
    "--publish",
    "-e",
    "--env",
    "--env-file",
    "-v",
    "--volume",
    "--mount",
    "--privileged",
    "--network=host",
    "--pid=host",
    "--cap-add",
}


def _adapter(docker: FakeDocker, clock: FakeClock | None = None) -> ContainerFixtureAdapter:
    clock = clock or FakeClock()
    return ContainerFixtureAdapter(docker, clock=clock, sleeper=clock.sleep)


def _no_forbidden_arguments(docker: FakeDocker) -> None:
    for argv in docker.calls:
        assert not FORBIDDEN_ARGUMENTS & set(argv), argv


# -- install --------------------------------------------------------------------------


def test_a_never_started_install_creates_each_node_and_starts_nothing() -> None:
    docker = FakeDocker()
    document = parameters(ISOLATION_NEVER_STARTED)

    evidence = _adapter(docker).apply(document, 120)

    creates = [argv for argv in docker.calls if argv[1] == "create"]
    first = document["containers"][0]
    assert creates[0] == (
        "docker",
        "create",
        "--network=none",
        "--label",
        "oak.fixture=true",
        "--label",
        f"oak.case={CASE_ID}",
        "--label",
        "oak.node=node.retrieval",
        "--label",
        f"oak.installation={INSTALLATION_ID}",
        "--label",
        "oak.isolation=network-none-never-started",
        "--name",
        first["container_name"],
        f"{IMAGE}@{DIGEST}",
    )
    assert len(creates) == 2
    assert "start" not in docker.verbs() and "stats" not in docker.verbs()
    status, test = evidence
    assert status["category"] == "status"
    assert [row["outcome"] for row in status["content"]["installation"]] == ["created"] * 2
    assert test["category"] == "test_result"
    assert test["content"]["started"] is False
    assert test["content"]["passed"] is True
    assert {row["state"] for row in test["content"]["smoke_test"]} == {"created"}
    _no_forbidden_arguments(docker)


def test_a_started_install_uses_exactly_the_hardening_flags_and_measures_each_node() -> None:
    docker = FakeDocker()
    document = parameters(ISOLATION_STARTED_HARDENED)

    status, test, metric = _adapter(docker).apply(document, 120)

    create = next(argv for argv in docker.calls if argv[1] == "create")
    assert create[2:3] == ("--network=none",)
    assert create[3 : 3 + len(HARDENING_FLAGS)] == HARDENING_FLAGS
    assert [argv for argv in docker.calls if argv[1] == "start"] == [
        ("docker", "start", name) for name in names(document)
    ]
    rows = test["content"]["smoke_test"]
    assert test["content"]["passed"] is True and test["content"]["started"] is True
    assert all(row["ready"] is True and row["state"] == "running" for row in rows)
    assert all(isinstance(row["startup_seconds"], float) for row in rows)
    assert metric["category"] == "aggregate_metric"
    assert [row["memory_bytes"] for row in metric["content"]["memory"]] == [1_572_864] * 2
    _no_forbidden_arguments(docker)
    # The health block's probe output never leaves the adapter.
    assert "secret" not in str((status, test, metric))


def test_re_apply_adopts_only_this_cases_own_containers() -> None:
    docker = FakeDocker()
    document = parameters()
    for entry in document["containers"]:
        docker.add(entry["container_name"], owned_labels(entry["node_id"]))

    status, _test = _adapter(docker).apply(document, 120)

    assert "create" not in docker.verbs()
    assert [row["outcome"] for row in status["content"]["installation"]] == ["already_present"] * 2


@pytest.mark.parametrize(
    "labels",
    [
        {},
        {"oak.fixture": "true"},
        owned_labels("node.retrieval", case_id="design-case.someone-else"),
        owned_labels("node.generation"),
        # The same case and node from another workspace's installation of the same brief.
        owned_labels("node.retrieval", installation_id="installation." + "9" * 24),
    ],
)
def test_a_foreign_container_with_the_planned_name_is_denied_never_adopted_or_removed(
    labels: dict[str, str],
) -> None:
    docker = FakeDocker()
    document = parameters()
    docker.add(document["containers"][0]["container_name"], labels)

    with pytest.raises(AdapterFailureError) as caught:
        _adapter(docker).apply(document, 120)

    assert caught.value.code == "OAK-RUNNER-FOREIGN"
    assert caught.value.created == ()
    assert "create" not in docker.verbs() and "rm" not in docker.verbs()
    assert document["containers"][0]["container_name"] in docker.containers


def test_a_partial_failure_reports_exactly_what_it_created() -> None:
    document = parameters()
    first, second = names(document)
    docker = FakeDocker(fail_create_for={second})

    with pytest.raises(AdapterFailureError) as caught:
        _adapter(docker).apply(document, 120)

    assert caught.value.code == "OAK-RUNNER-APPLY"
    assert caught.value.created == (first,)
    status = caught.value.evidence[0]
    assert [row["container_name"] for row in status["content"]["installation"]] == [first]


def test_a_created_container_with_the_wrong_digest_is_denied_and_named_for_removal() -> None:
    docker = FakeDocker(repo_digests=[f"{IMAGE}@sha256:" + "f" * 64])
    document = parameters()

    with pytest.raises(AdapterFailureError) as caught:
        _adapter(docker).apply(document, 120)

    assert caught.value.code == "OAK-RUNNER-IMAGE"
    assert caught.value.created == (names(document)[0],)


def test_an_adopted_container_with_the_wrong_digest_is_denied_but_left_alone() -> None:
    docker = FakeDocker(repo_digests=[])
    document = parameters()
    entry = document["containers"][0]
    docker.add(entry["container_name"], owned_labels(entry["node_id"]))

    with pytest.raises(AdapterFailureError) as caught:
        _adapter(docker).apply(document, 120)

    assert caught.value.code == "OAK-RUNNER-IMAGE"
    assert caught.value.created == ()


def test_an_unreadable_daemon_is_never_read_as_absent() -> None:
    docker = FakeDocker(fail_inspect=True)

    with pytest.raises(AdapterFailureError) as caught:
        _adapter(docker).apply(parameters(), 120)

    assert caught.value.code == "OAK-RUNNER-APPLY"
    assert "create" not in docker.verbs()


def test_an_expired_lease_stops_the_install_before_any_side_effect() -> None:
    docker = FakeDocker()
    now = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    adapter = ContainerFixtureAdapter(docker, wall_clock=lambda: now)

    with pytest.raises(AdapterFailureError) as caught:
        adapter.apply(parameters(), 120, deadline=now - timedelta(seconds=1))

    assert caught.value.code == "OAK-RUNNER-LEASE"
    assert docker.calls == []


def test_a_lease_that_lapses_mid_install_stops_before_the_next_node() -> None:
    docker = FakeDocker()
    moments = iter(
        [
            datetime(2026, 9, 29, 12, 0, tzinfo=UTC),
            datetime(2026, 9, 29, 12, 10, tzinfo=UTC),
        ]
    )
    adapter = ContainerFixtureAdapter(docker, wall_clock=lambda: next(moments))
    document = parameters()

    with pytest.raises(AdapterFailureError) as caught:
        adapter.apply(document, 120, deadline=datetime(2026, 9, 29, 12, 5, tzinfo=UTC))

    assert caught.value.code == "OAK-RUNNER-LEASE"
    assert caught.value.created == (names(document)[0],)


# -- smoke test ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("docker", "reason"),
    [
        (FakeDocker(start_status="exited", exit_code=3), "exited"),
        (FakeDocker(health="unhealthy"), "unhealthy"),
        (FakeDocker(start_status="restarting"), "readiness_timeout"),
        (FakeDocker(health="starting"), "readiness_timeout"),
        (FakeDocker(status_after_settle="exited"), "stopped_after_start"),
    ],
)
def test_a_node_that_does_not_come_up_fails_the_smoke_test(docker: FakeDocker, reason: str) -> None:
    document = parameters(ISOLATION_STARTED_HARDENED)

    with pytest.raises(AdapterFailureError) as caught:
        _adapter(docker).apply(document, 120)

    assert caught.value.code == "OAK-RUNNER-SMOKE-TEST"
    assert caught.value.created == tuple(names(document))
    test = next(item for item in caught.value.evidence if item["category"] == "test_result")
    assert test["content"]["passed"] is False
    assert test["content"]["smoke_test"][0]["reason"] == reason
    assert test["content"]["smoke_test"][0]["ready"] is False
    if reason == "exited":
        assert test["content"]["smoke_test"][0]["exit_code"] == 3


def test_the_readiness_wait_is_bounded() -> None:
    docker = FakeDocker(start_status="restarting")
    clock = FakeClock()

    with pytest.raises(AdapterFailureError):
        _adapter(docker, clock).apply(
            parameters(
                ISOLATION_STARTED_HARDENED,
                nodes=(("node.retrieval", "component.fixture-lexical-search"),),
            ),
            120,
        )

    assert clock.now - 100.0 <= 16.0


def test_a_healthcheck_must_report_healthy() -> None:
    docker = FakeDocker(health="healthy")

    _status, test, _metric = _adapter(docker).apply(parameters(ISOLATION_STARTED_HARDENED), 120)

    assert {row["health"] for row in test["content"]["smoke_test"]} == {"healthy"}


def test_an_unreadable_memory_reading_is_unknown_not_zero() -> None:
    docker = FakeDocker(stats="--")

    _status, _test, metric = _adapter(docker).apply(parameters(ISOLATION_STARTED_HARDENED), 120)

    assert {row["memory_bytes"] for row in metric["content"]["memory"]} == {None}


# -- removal -------------------------------------------------------------------------


def test_rollback_removes_owned_containers_with_their_volumes_and_proves_it() -> None:
    docker = FakeDocker()
    document = parameters()
    for entry in document["containers"]:
        docker.add(entry["container_name"], owned_labels(entry["node_id"]))

    result = _adapter(docker).rollback(document, 120)

    assert docker.containers == {}
    assert [argv for argv in docker.calls if argv[1] == "rm"] == [
        ("docker", "rm", "--force", "--volumes", name) for name in reversed(names(document))
    ]
    assert result["category"] == "rollback_result"
    assert result["content"]["removed_all"] is True
    assert all(row["absent_after"] for row in result["content"]["containers"])


def test_rollback_of_an_absent_installation_is_verified_not_assumed() -> None:
    docker = FakeDocker()

    result = _adapter(docker).destroy(parameters(), 120)

    assert "rm" not in docker.verbs()
    rows = result["content"]["containers"]
    assert all(row["present_before"] is False and row["absent_after"] is True for row in rows)


def test_rollback_refuses_to_remove_a_foreign_container() -> None:
    docker = FakeDocker()
    document = parameters()
    docker.add(document["containers"][1]["container_name"], {"oak.fixture": "true"})

    with pytest.raises(AdapterFailureError) as caught:
        _adapter(docker).rollback(document, 120)

    assert caught.value.code == "OAK-RUNNER-FOREIGN"
    assert "rm" not in docker.verbs()


def test_a_removal_that_leaves_the_container_behind_is_a_failure() -> None:
    docker = FakeDocker(keep_after_rm=True)
    document = parameters()
    entry = document["containers"][0]
    docker.add(entry["container_name"], owned_labels(entry["node_id"]))

    with pytest.raises(AdapterFailureError) as caught:
        _adapter(docker).rollback(document, 120)

    assert caught.value.code == "OAK-RUNNER-ROLLBACK"
    row = caught.value.evidence[0]["content"]["containers"][-1]
    assert row["absent_after"] is False


def test_compensation_removes_only_what_the_failed_apply_created() -> None:
    docker = FakeDocker()
    document = parameters()
    first, second = names(document)
    for entry in document["containers"]:
        docker.add(entry["container_name"], owned_labels(entry["node_id"]))

    result = _adapter(docker).compensate(document, (second,), 120)

    assert list(docker.containers) == [first]
    assert [row["container_name"] for row in result["content"]["containers"]] == [second]
    assert result["operation"] == "compensation"


# -- parameters ----------------------------------------------------------------------


def _poisoned(field: str, value: object, *, top: bool = False) -> dict:
    document = parameters()
    if top:
        document[field] = value
    else:
        document["containers"][0][field] = value
    return document


@pytest.mark.parametrize(
    "document",
    [
        _poisoned("container_name", "oak-fixture-a; rm -rf /"),
        _poisoned("container_name", "evil"),
        _poisoned("container_name", "oak-fixture-" + "0" * 12),
        _poisoned("node_id", "-v"),
        _poisoned("node_id", "node retrieval"),
        _poisoned("manifest_id", "$(id)"),
        _poisoned("image_reference", "--privileged"),
        _poisoned("image_reference", "pause; touch /tmp/x"),
        _poisoned("image_reference", f"{IMAGE}@sha256:" + "b" * 64),
        _poisoned("image_digest", "sha256:short"),
        _poisoned("case_id", "--label=x", top=True),
        _poisoned("isolation", "host", top=True),
        _poisoned("containers", [], top=True),
    ],
)
def test_poisoned_parameters_are_refused_before_anything_executes(document: dict) -> None:
    docker = FakeDocker()

    with pytest.raises(OAKError):
        _adapter(docker).apply(document, 120)
    with pytest.raises(OAKError):
        _adapter(docker).rollback(document, 120)

    assert docker.calls == []


def test_a_name_not_derived_for_this_installation_is_refused() -> None:
    document = parameters()
    document["containers"][0]["container_name"] = container_name_for(
        "installation." + "f" * 24, "node.retrieval"
    )

    with pytest.raises(OAKError, match="derived for this installation"):
        _adapter(FakeDocker()).apply(document, 120)


def test_a_subprocess_failure_becomes_a_typed_denial_not_a_traceback() -> None:
    import subprocess

    def executor(argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
        raise subprocess.TimeoutExpired(argv, timeout_seconds)

    with pytest.raises(OAKError) as caught:
        ContainerFixtureAdapter(executor).apply(parameters(), 120)
    assert caught.value.code == "OAK-RUNNER-SUBPROCESS"


# -- unchanged helpers ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("reference", "host"),
    [
        ("postgres", "docker.io"),
        ("library/postgres", "docker.io"),
        ("rancher/mirrored-pause", "docker.io"),
        ("localhost/tool", "localhost"),
        ("localhost:5000/tool", "localhost:5000"),
        ("registry.example.internal/team/tool", "registry.example.internal"),
        ("host:8443/tool", "host:8443"),
    ],
)
def test_registry_host_follows_docker_resolution_rules(reference: str, host: str) -> None:
    assert registry_host(reference) == host


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


# -- audit regressions (Sprint 11 closing audit) ---------------------------------------


def test_a_never_started_container_is_never_adopted_into_a_hardened_start() -> None:
    """S1/S5: adoption must not start a container that was created without hardening."""

    docker = FakeDocker()
    document = parameters(ISOLATION_STARTED_HARDENED)
    for entry in document["containers"]:
        docker.add(entry["container_name"], owned_labels(entry["node_id"]))

    with pytest.raises(AdapterFailureError) as caught:
        _adapter(docker).apply(document, 120)

    assert caught.value.code == "OAK-RUNNER-ISOLATION"
    assert "start" not in docker.verbs()


def test_labels_claiming_hardening_are_checked_against_the_real_configuration() -> None:
    """S1/S5: a label is a claim; the daemon's HostConfig is read back before any start."""

    docker = FakeDocker()
    document = parameters(ISOLATION_STARTED_HARDENED)
    for entry in document["containers"]:
        docker.add(
            entry["container_name"],
            owned_labels(entry["node_id"], isolation=ISOLATION_STARTED_HARDENED),
            hardened=False,
        )

    with pytest.raises(AdapterFailureError) as caught:
        _adapter(docker).apply(document, 120)

    assert caught.value.code == "OAK-RUNNER-ISOLATION"
    assert "start" not in docker.verbs()


def test_a_properly_hardened_container_is_adopted_and_already_running_has_no_startup_time() -> None:
    """S20: a re-apply over a running installation reports no startup time."""

    docker = FakeDocker()
    document = parameters(ISOLATION_STARTED_HARDENED)
    for entry in document["containers"]:
        docker.add(
            entry["container_name"],
            owned_labels(entry["node_id"], isolation=ISOLATION_STARTED_HARDENED),
            status="running",
            hardened=True,
        )

    status, test, _metric = _adapter(docker).apply(document, 120)

    assert {row["outcome"] for row in status["content"]["installation"]} == {"already_present"}
    rows = test["content"]["smoke_test"]
    assert all(row["already_running"] is True and row["startup_seconds"] is None for row in rows)
    assert test["content"]["passed"] is True


def test_a_created_container_that_is_not_network_none_is_refused() -> None:
    docker = FakeDocker()
    document = parameters()
    entry = document["containers"][0]
    docker.add(entry["container_name"], owned_labels(entry["node_id"]))
    docker.containers[entry["container_name"]]["host"]["NetworkMode"] = "bridge"

    with pytest.raises(AdapterFailureError) as caught:
        _adapter(docker).apply(document, 120)

    assert caught.value.code == "OAK-RUNNER-ISOLATION"


def test_a_create_that_failed_after_making_the_container_is_still_compensated() -> None:
    """S4/S8: a timed-out create can leave a container behind; it is named for removal."""

    document = parameters()
    first = names(document)[0]
    docker = FakeDocker(create_then_fail_for={first})

    with pytest.raises(AdapterFailureError) as caught:
        _adapter(docker).apply(document, 120)

    assert caught.value.code == "OAK-RUNNER-APPLY"
    assert caught.value.created == (first,)


def test_memory_with_no_accounting_is_unknown_not_zero() -> None:
    """S7: '0B / 0B' means the daemon keeps no memory accounting."""

    docker = FakeDocker(stats="0B / 0B")

    _status, _test, metric = _adapter(docker).apply(parameters(ISOLATION_STARTED_HARDENED), 120)

    assert {row["memory_bytes"] for row in metric["content"]["memory"]} == {None}


def test_a_smoke_test_cut_short_is_incomplete_and_not_passed() -> None:
    """S16: a lapsed lease between starts leaves a test that covered only some nodes."""

    docker = FakeDocker()
    moments = iter(
        [datetime(2026, 9, 29, 12, 0, tzinfo=UTC)] * 3 + [datetime(2026, 9, 29, 13, 0, tzinfo=UTC)]
    )
    clock = FakeClock()
    adapter = ContainerFixtureAdapter(
        docker, clock=clock, sleeper=clock.sleep, wall_clock=lambda: next(moments)
    )

    with pytest.raises(AdapterFailureError) as caught:
        adapter.apply(
            parameters(ISOLATION_STARTED_HARDENED),
            120,
            deadline=datetime(2026, 9, 29, 12, 30, tzinfo=UTC),
        )

    assert caught.value.code == "OAK-RUNNER-LEASE"
    test = next(item for item in caught.value.evidence if item["category"] == "test_result")
    assert test["content"]["complete"] is False and test["content"]["passed"] is False


def test_a_removal_that_fails_part_way_records_the_container_it_did_not_remove() -> None:
    """S15: the failing container is in the record, and removed_all is false."""

    document = parameters()
    first, second = names(document)
    docker = FakeDocker(fail_rm_for={first})
    for entry in document["containers"]:
        docker.add(entry["container_name"], owned_labels(entry["node_id"]))

    with pytest.raises(AdapterFailureError) as caught:
        _adapter(docker).rollback(document, 120)

    content = caught.value.evidence[0]["content"]
    assert content["removed_all"] is False
    rows = {row["container_name"]: row for row in content["containers"]}
    assert rows[second]["absent_after"] is True
    assert rows[first]["absent_after"] is False


@pytest.mark.parametrize(
    ("reference", "host"),
    [("Registry/tool", "Registry"), ("myHost/team/tool", "myHost")],
)
def test_an_uppercase_first_component_is_a_registry_host(reference: str, host: str) -> None:
    """S6: Docker reads a first component with an uppercase letter as a registry."""

    assert registry_host(reference) == host


def test_a_container_created_for_another_isolation_is_not_adopted() -> None:
    """Adoption is for a re-apply under the same isolation; the label says which."""

    docker = FakeDocker()
    document = parameters(ISOLATION_NEVER_STARTED)
    for entry in document["containers"]:
        docker.add(
            entry["container_name"],
            owned_labels(entry["node_id"], isolation=ISOLATION_STARTED_HARDENED),
            hardened=True,
        )

    with pytest.raises(AdapterFailureError) as caught:
        _adapter(docker).apply(document, 120)

    assert caught.value.code == "OAK-RUNNER-ISOLATION"
