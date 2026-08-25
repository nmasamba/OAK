# SPDX-License-Identifier: Apache-2.0
"""Regenerate the signed protocol examples from a real compile-sign-dispatch run.

The signed examples (`example-plan-signature`, `example-approval`,
`example-runner-envelope`, `example-runner-plan`, `example-revocation`) embed compiled
digests and real Ed25519 signatures. Hand-editing them after a compiler change leaves
digests that describe documents that no longer exist, so they are regenerated instead:
this script drives the same fixed-clock harness the test suite uses
(`tests.runner_support.build_compiled_case`), signs, approves, dispatches and revokes,
and writes what actually landed in the mailbox. Every written document is round-tripped
through the YAML loader and cryptographically re-verified before the script succeeds.

`example-runner-message.yaml` is not regenerated: it embeds no compiled digest, and its
runner identity is created fresh per run, which would churn the example without making
it truer. `example-deployment-bundle.yaml` and `example-runner-plan.yaml` differ: the
bundle example deliberately uses placeholder digests, while the runner-plan example is
compiled content and is regenerated here.

Usage: uv run python scripts/generate_examples.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oak.contracts import load_yaml_document  # noqa: E402
from oak.contracts.signatures import verify_signed_document  # noqa: E402

SIGNED_OUTPUTS = (
    "example-plan-signature.yaml",
    "example-approval.yaml",
    "example-runner-envelope.yaml",
    "example-revocation.yaml",
    "example-revocation-manifest.yaml",
)


def _write(name: str, document: dict[str, Any]) -> None:
    rendered = yaml.safe_dump(
        document,
        sort_keys=True,
        allow_unicode=True,
        default_flow_style=False,
        width=1000,
    )
    path = ROOT / "examples" / name
    path.write_text("# SPDX-License-Identifier: Apache-2.0\n" + rendered, encoding="utf-8")
    reloaded = load_yaml_document(path.read_text(encoding="utf-8"))
    if reloaded != document:
        raise SystemExit(f"{name}: YAML round-trip does not reproduce the source document")
    if name in SIGNED_OUTPUTS and not verify_signed_document(reloaded):
        raise SystemExit(f"{name}: signature does not verify after rendering")
    print(f"wrote examples/{name}")


def main() -> int:
    import tempfile

    from tests.runner_support import build_compiled_case, read_dispatch

    with tempfile.TemporaryDirectory() as scratch:
        harness = build_compiled_case(Path(scratch))
        harness.release.sign_plan(harness.context("signplan-00000001", "0.1.7"))
        harness.release.approve("dry_run", harness.context("approve-dryrun-0001", "0.1.8"))
        harness.release.dispatch(
            ("inventory", "validate", "render", "plan", "verify"),
            harness.context("dispatch-readonly-1", "0.1.9"),
        )
        envelope, attachments = read_dispatch(harness.mailbox_root)
        harness.release.revoke_approval(
            "dry_run",
            "Example: the dry-run approval is withdrawn.",
            harness.context("revoke-dryrun-00001", "0.1.10"),
        )
        revocation_dir = harness.mailbox_root / "revocations"
        notices = sorted(
            path for path in revocation_dir.glob("*.json") if path.name != "manifest.json"
        )
        if len(notices) != 1:
            raise SystemExit(f"expected exactly one revocation notice, found {len(notices)}")
        import json

        notice = json.loads(notices[0].read_text(encoding="utf-8"))
        manifest = json.loads((revocation_dir / "manifest.json").read_text(encoding="utf-8"))

        _write("example-runner-envelope.yaml", envelope)
        _write("example-plan-signature.yaml", attachments["plan-signature"])
        _write("example-approval.yaml", attachments["approval-dry-run"])
        _write("example-runner-plan.yaml", attachments["plan"])
        _write("example-revocation.yaml", notice)
        _write("example-revocation-manifest.yaml", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
