# SPDX-License-Identifier: Apache-2.0
"""Temporary end-to-end PoC for adversarial refutation - delete after use."""

import json
import shutil
from pathlib import Path

from tests.e2e.test_runner_journey import (
    OAK,
    OAK_RUNNER,
    ROOT,
    _compile_case,
    _environment,
    _run,
)


def test_poc_wedge(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    workspace = tmp_path / "workspace"
    _compile_case(workspace, environment, ROOT / "examples/targets/local-fixture.yaml")
    for step in (["keys", "init"], ["sign"], ["approve", "dry_run"]):
        assert _run([str(OAK), *step], workspace, environment).returncode == 0
    assert (
        _run([str(OAK), "dispatch", "inventory", "verify"], workspace, environment).returncode == 0
    )

    mailbox = Path(environment["OAK_DISPATCH_MAILBOX"])
    dispatch_dir = next((mailbox / "dispatches").iterdir())
    print("LEGIT DISPATCH DIR:", dispatch_dir.name)

    poison = mailbox / "dispatches" / "aaa-poison"
    shutil.copytree(dispatch_dir, poison)
    envelope_path = poison / "envelope.json"
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    envelope["approval_refs"][0]["id"] = "approvalpending"
    envelope["signature"]["value"] = "AAAA"
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")

    runner_environment = dict(environment)
    runner_environment.update(
        {
            "OAK_RUNNER_MAILBOX": environment["OAK_DISPATCH_MAILBOX"],
            "OAK_RUNNER_HOME": str(tmp_path / "runner"),
            "OAK_RUNNER_TRUST_ANCHORS": environment["OAK_TRUST_DIRECTORY"],
            "OAK_RUNNER_TARGET_PROFILE": str(ROOT / "examples/targets/local-fixture.yaml"),
        }
    )
    for attempt in (1, 2):
        ran = _run([str(OAK_RUNNER), "run-once"], ROOT, runner_environment)
        print(f"=== RUN {attempt} rc={ran.returncode}")
        print("STDOUT:", ran.stdout)
        print("STDERR:", ran.stderr[-2000:])

    print("MESSAGES:", sorted(p.name for p in (mailbox / "messages").glob("*")) if (mailbox / "messages").is_dir() else "none")
    print("PROCESSED MARKERS:", sorted(str(p.relative_to(mailbox)) for p in mailbox.rglob(".processed")))

    # second variant: lease as a string
    poison2 = mailbox / "dispatches" / "aaa-poison2"
    shutil.copytree(dispatch_dir, poison2)
    e2 = json.loads((poison2 / "envelope.json").read_text(encoding="utf-8"))
    e2["lease"] = "x"
    (poison2 / "envelope.json").write_text(json.dumps(e2), encoding="utf-8")
    shutil.rmtree(poison)
    ran = _run([str(OAK_RUNNER), "run-once"], ROOT, runner_environment)
    print("=== LEASE-STRING RUN rc=", ran.returncode)
    print("STDERR:", ran.stderr[-1500:])
    raise SystemExit(0)
