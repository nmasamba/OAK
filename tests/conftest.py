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

from pathlib import Path

import pytest

from oak import bootstrap
from oak.adapters.credentials import keychain_store

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


def _no_network_verifier(
    family: str, *, deadline_seconds: float | None = None
) -> dict[str, object]:
    del family, deadline_seconds
    return {
        "verdict": "unverifiable",
        "method": "unknown",
        "reason": "verification is not performed in the test suite",
    }
