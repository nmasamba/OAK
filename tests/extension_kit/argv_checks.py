# SPDX-License-Identifier: Apache-2.0
"""Argv-safety and rollback checks for typed runner adapters."""

from collections.abc import Callable
from typing import Any

import pytest

INJECTION_PARAMETER_SETS: tuple[dict[str, Any], ...] = (
    {"container_name": "oak-fixture-a; rm -rf /", "note": "shell metacharacters in name"},
    {"container_name": "oak-fixture-a && true", "note": "command chaining in name"},
    {"container_name": "--privileged", "note": "flag injection through the name"},
    {"image_reference": "-rm", "note": "flag injection through the image"},
    {"image_reference": "busybox; touch /tmp/pwned", "note": "metacharacters in image"},
    {"image_reference": "busybox`id`", "note": "command substitution in image"},
    {"image_reference": "busybox$(id)", "note": "subshell in image"},
    {"image_digest": "sha256:short", "note": "malformed digest"},
    {"image_reference": "busybox@sha256:" + "a" * 64, "note": "reference smuggling a digest"},
    {"command": ["/bin/sh"], "note": "forbidden execution field"},
    {"argv": ["docker", "run"], "note": "forbidden argument vector"},
    {"shell": True, "note": "forbidden shell request"},
    {"executable": "/bin/bash", "note": "forbidden executable selection"},
)

_BASE_PARAMETERS: dict[str, Any] = {
    "container_name": "oak-fixture-kit",
    "image_reference": "registry.example.invalid/fixture",
    "image_digest": "sha256:" + "a" * 64,
    "isolation": "network-none-never-started",
}


def check_argv_injection_resistance(
    invoke: Callable[[dict[str, Any]], Any],
    *,
    base_parameters: dict[str, Any] | None = None,
) -> None:
    """Every injection fixture must be rejected before any execution occurs.

    ``invoke`` receives the poisoned parameter mapping and must raise —
    any exception counts as a rejection, because the paired recording
    executor separately proves nothing was executed. Wire ``invoke`` the way
    your pipeline really runs: schema validation first, then the adapter.
    """

    base = dict(base_parameters or _BASE_PARAMETERS)
    for poison in INJECTION_PARAMETER_SETS:
        parameters = {**base, **{k: v for k, v in poison.items() if k != "note"}}
        with pytest.raises(Exception):  # noqa: B017 - any raise is a rejection
            invoke(parameters)


def check_typed_rollback(
    apply_then_rollback: Callable[[], tuple[list[tuple[str, ...]], list[tuple[str, ...]]]],
) -> None:
    """Rollback must be a typed inverse bound to exactly the applied identity.

    The callable runs an apply followed by a rollback against a recording
    executor and returns ``(apply_argvs, rollback_argvs)``.
    """

    apply_argvs, rollback_argvs = apply_then_rollback()
    assert apply_argvs, "apply must execute through the recorded executor"
    assert rollback_argvs, "rollback must execute through the recorded executor"
    applied_name = apply_argvs[0][-2] if len(apply_argvs[0]) >= 2 else None
    for argv in (*apply_argvs, *rollback_argvs):
        assert argv[0] in {"docker"}, "argv must begin with an allowlisted executable"
    assert applied_name is not None
    assert any(applied_name in argv for argv in rollback_argvs), (
        "rollback must target exactly the applied resource name"
    )
