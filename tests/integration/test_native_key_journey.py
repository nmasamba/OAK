# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-045: a model server's key, through the real runner, reaches no record.

The journey installs a server shaped like `llama-server`, which reads the key file and
refuses a request without its key, then looks through every file the journey wrote: the plan,
the mailbox, the runner's journal and the case's records.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from oak.contracts import load_yaml_document
from oak.runner.native import API_KEY_FILE
from tests.integration import test_native_install
from tests.integration.test_native_install import NativeJourney
from tests.unit.test_native_adapter import LlamaRelease

pytestmark = pytest.mark.integration


def test_the_installations_key_reaches_no_record_and_no_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = LlamaRelease(tmp_path)
    profile = load_yaml_document(test_native_install.EXAMPLE.read_text(encoding="utf-8"))
    for entry in profile["execution"]["native_components"]:
        entry["harness_kind"] = "llama_cpp_server"
        entry["artifacts"] = [
            release.artifact("harness", "https://example.org/llama.tar.gz", "tar.gz"),
            release.artifact("model", "https://example.org/model.gguf", "file"),
        ]
    profile["execution"]["allowed_download_hosts"] = ["example.org"]
    example = tmp_path / "llama-target.yaml"
    example.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(test_native_install, "EXAMPLE", example)
    journey = NativeJourney(tmp_path, monkeypatch)

    payload = journey.install(release.adapter(journey.runner_home / "native"))

    assert payload["outcome"] == "succeeded", payload
    tested = next(item for item in payload["evidence"] if item["category"] == "test_result")
    assert {row["status_without_key"] for row in tested["content"]["smoke_test"]} == {401}
    measures = {item["id"]: item["result"] for item in journey.observe()["deployment_measures"]}
    assert measures["smoke-test"] == "pass"
    key_file = journey.installation / API_KEY_FILE
    key = key_file.read_bytes().strip()
    assert len(key) == 64
    assert list((journey.runner_home / "journals").glob("*.jsonl")), "the journal is looked at"
    holders = [
        path
        for path in tmp_path.rglob("*")
        if path.is_file() and not path.is_symlink() and key in path.read_bytes()
    ]
    assert holders == [key_file]
