# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-043: the report counts a native plan's three approvals before any is recorded."""

from oak.application.report.composer import _installs_natively


def _bundle(mode: str | None) -> dict:
    evidence = {} if mode is None else {"mode": mode}
    return {
        "extensions": {
            "oak.community/preflight_results": [
                {"id": "preflight.network", "evidence": {}},
                {"id": "preflight.installation", "evidence": evidence},
            ]
        }
    }


def test_the_bundle_says_whether_its_plan_installs_natively() -> None:
    assert _installs_natively(_bundle("native")) is True
    assert _installs_natively(_bundle(None)) is False
    assert _installs_natively(None) is False
    assert _installs_natively({"extensions": {}}) is False
