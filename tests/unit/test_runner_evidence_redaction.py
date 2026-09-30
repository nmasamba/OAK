# SPDX-License-Identifier: Apache-2.0
"""RR-023: evidence is redacted by key as well as by value before it leaves the runner.

Until an adapter's own output could reach evidence, value-pattern redaction was enough
because every value was built in code. The topology installer reads the daemon, so a
field *named* like a secret is now withheld whatever its value looks like, and a
credential embedded in a URL is withheld too.
"""

import pytest

from oak.runner.execution import REDACTED, _bounded

POLICY = {
    "allowed_categories": ["status", "test_result"],
    "maximum_bytes": 1_048_576,
    "redact_fields": ["credentials", "secrets", "environment", "operator_note"],
}


def _one(content: dict) -> dict:
    (entry,) = _bounded([{"category": "status", "operation": "apply", "content": content}], POLICY)
    return entry["content"]


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "DB_PASSWORD",
        "api_key",
        "apiKey",
        "Authorization",
        "access_token",
        "client_secret",
        "private_key",
        "connection_string",
        "dsn",
        "env",
        "Environment",
        "credentials",
        "operator_note",
    ],
)
def test_a_field_named_like_a_secret_is_withheld_whatever_its_value(key: str) -> None:
    assert _one({key: "harmless-looking-value", "state": "running"}) == {
        key: REDACTED,
        "state": "running",
    }


def test_nested_secret_keys_are_withheld_at_any_depth() -> None:
    content = {"containers": [{"node_id": "node.retrieval", "labels": {"token": "abc"}}]}
    assert _one(content)["containers"][0]["labels"]["token"] == REDACTED


def test_a_credential_inside_a_url_value_is_withheld() -> None:
    redacted = _one({"endpoint": "postgres://oak:hunter2@db.internal:5432/oak"})["endpoint"]
    assert "hunter2" not in redacted and "oak:" not in redacted
    assert redacted.startswith("postgres://") and redacted.endswith("@db.internal:5432/oak")


def test_value_patterns_still_apply() -> None:
    assert "s3cr3t" not in _one({"detail": "password=s3cr3t"})["detail"]


def test_the_installers_own_fields_pass_through_untouched() -> None:
    content = {
        "node_id": "node.retrieval",
        "container_name": "oak-fixture-retrieval-c53414363f52",
        "resolved_image_digest": "sha256:" + "e" * 64,
        "state": "running",
        "health": "none",
        "exit_code": None,
        "startup_seconds": 0.5,
        "memory_bytes": 1_572_864,
    }
    assert _one(content) == content


def test_a_category_the_plan_does_not_allow_never_leaves() -> None:
    evidence = [{"category": "aggregate_metric", "operation": "apply", "content": {"x": 1}}]
    assert _bounded(evidence, POLICY) == ()


def test_the_docker_child_sees_only_path_and_an_empty_runner_owned_config(
    tmp_path, monkeypatch
) -> None:
    """The operator's Docker config, credential helpers and CLI context are never used."""

    import os
    import subprocess

    from oak.runner.adapters import isolated_executor

    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr("oak.runner.adapters.shutil.which", lambda name: "/usr/local/bin/docker")
    monkeypatch.setattr("oak.runner.adapters.subprocess.run", fake_run)
    config = tmp_path / "docker-config"

    isolated_executor(config)(("docker", "version"), 5)

    assert captured["env"] == {"PATH": os.defpath, "DOCKER_CONFIG": str(config)}
    assert captured["shell"] is False
    assert config.is_dir() and list(config.iterdir()) == []
    assert oct(config.stat().st_mode & 0o777) == "0o700"
