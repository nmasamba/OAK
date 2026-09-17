# SPDX-License-Identifier: Apache-2.0
"""Session-wide test isolation.

The model-provider work stores a user's provider credentials and model selection under
the user's home directory. No test may read a developer's real key or selection, and no
test may leave one behind, so every test runs against throwaway directories.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_model_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OAK_MODELS_DIRECTORY", str(tmp_path / "isolated-models"))
    monkeypatch.setenv("OAK_CREDENTIALS_DIRECTORY", str(tmp_path / "isolated-credentials"))
    for family in ("HUGGINGFACE", "OPENAI", "ANTHROPIC", "GEMINI", "META", "XAI"):
        monkeypatch.delenv(f"OAK_MODEL_KEY_{family}", raising=False)
    monkeypatch.delenv("OAK_MODEL_TOKEN", raising=False)
    monkeypatch.delenv("OAK_MODEL_ENDPOINT_LOCAL", raising=False)
