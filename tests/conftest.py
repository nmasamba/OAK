# SPDX-License-Identifier: Apache-2.0
"""Session-wide test isolation.

The model-provider work stores a user's provider credentials and model selection. No test
may read a developer's real key or selection, and no test may leave one behind. Two things
have to be redirected for that to be true, and only one of them is a directory:

- the credential and model-configuration directories, which move to `tmp_path`; and
- the operating-system keychain, which is not a directory at all. Redirecting the
  directories does nothing to it, so a test that stored a key through a path preferring the
  keychain — `PUT /v1/models/credentials/{family}` does — would write into the developer's
  real login keychain under the service name OAK uses, overwriting whatever was there.

The live provider suite is deliberately exempt: it exists to exercise the keys the machine
actually has, and isolating it would guarantee it always skips.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from oak import bootstrap
from oak.adapters.credentials import keychain_store

# Every PostgreSQL-gated test skips with this reason when OAK_TEST_DATABASE_URL is unset,
# and a skip looks exactly like a pass in pytest's summary line.
DATABASE_SKIP_REASON = "OAK_TEST_DATABASE_URL is required"

# An import that cannot resolve, so every keychain operation reports
# OAK-MODEL-KEYCHAIN-UNAVAILABLE instead of reaching a real keychain.
INERT_KEYCHAIN_MODULE = "oak_tests_no_such_keyring_module"


@pytest.fixture(autouse=True)
def _isolated_model_state(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if "tests/live/" in request.path.as_posix():
        return
    monkeypatch.setenv("OAK_MODELS_DIRECTORY", str(tmp_path / "isolated-models"))
    monkeypatch.setenv("OAK_CREDENTIALS_DIRECTORY", str(tmp_path / "isolated-credentials"))
    monkeypatch.setattr(keychain_store, "DEFAULT_KEYCHAIN_MODULE", INERT_KEYCHAIN_MODULE)
    monkeypatch.delenv("OAK_MODEL_KEY_HUGGINGFACE", raising=False)
    monkeypatch.delenv("OAK_MODEL_TOKEN", raising=False)
    monkeypatch.delenv("OAK_MODEL_ENDPOINT_LOCAL", raising=False)
    # `oak models set-key` verifies by default, which is one request to huggingface.co. No
    # test may make it: the wiring gets a verifier that answers honestly that it did not ask.
    # A test about verification injects its own verifier or patches this one.
    monkeypatch.setattr(bootstrap, "model_verifier", _no_network_verifier)


@pytest.fixture(autouse=True)
def _no_skip_ledger_inside_a_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test that calls the summary hook with made-up reports must not write CI's ledger.

    The hook reads the variable at the end of the session, after monkeypatch has put it
    back, so the run's own skips are still recorded.
    """

    monkeypatch.delenv("OAK_SKIP_LEDGER", raising=False)


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    """Say how many PostgreSQL-gated tests a run skipped, so a skip is not read as a pass."""

    skipped = sum(
        1
        for report in terminalreporter.stats.get("skipped", [])
        if DATABASE_SKIP_REASON in str(report.longrepr)
    )
    if skipped:
        terminalreporter.write_line(
            f"PostgreSQL-gated tests skipped: {skipped} (OAK_TEST_DATABASE_URL is not set). "
            "A sprint's closing gate must run them; see CONTRIBUTING.md.",
            yellow=True,
            bold=True,
        )
    # CI names every skip and its reason here, and scripts/check_skips.py fails the job
    # unless they are exactly what that job expects: a skip that widens is a change to
    # what the job proves, so it has to be a reviewed change (RR-014).
    ledger = os.environ.get("OAK_SKIP_LEDGER")
    if ledger:
        with Path(ledger).open("a", encoding="utf-8") as stream:
            for report in terminalreporter.stats.get("skipped", []):
                stream.write(
                    json.dumps(
                        {"test": getattr(report, "nodeid", ""), "reason": _skip_reason(report)}
                    )
                    + "\n"
                )


def _skip_reason(report: pytest.TestReport) -> str:
    longrepr = report.longrepr
    reason = longrepr[2] if isinstance(longrepr, tuple) and len(longrepr) == 3 else longrepr
    return str(reason).removeprefix("Skipped: ")


def _no_network_verifier(
    family: str, *, deadline_seconds: float | None = None
) -> dict[str, object]:
    del family, deadline_seconds
    return {
        "verdict": "unverifiable",
        "method": "unknown",
        "reason": "verification is not performed in the test suite",
    }
