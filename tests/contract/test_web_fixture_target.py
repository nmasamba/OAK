# SPDX-License-Identifier: Apache-2.0
"""The web's "Use the local fixture" target is the repository fixture, byte for meaning."""

from __future__ import annotations

import json
import re
from pathlib import Path

from oak.contracts import load_yaml_document

ROOT = Path(__file__).resolve().parents[2]


def test_the_web_fixture_target_is_the_repository_fixture() -> None:
    module = (ROOT / "web" / "src" / "targets.ts").read_text(encoding="utf-8")
    match = re.search(r"LOCAL_FIXTURE_TARGET_JSON = `(.*)`;", module, re.DOTALL)
    assert match is not None
    fixture = load_yaml_document(
        (ROOT / "examples" / "targets" / "local-fixture.yaml").read_text(encoding="utf-8")
    )
    assert json.loads(match.group(1)) == fixture
