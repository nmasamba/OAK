# SPDX-License-Identifier: Apache-2.0
"""OAK-S9-001: the secret scan recognises model-provider key shapes.

`tools/check_repository.py` scans every committed text file for credential shapes. Before
Sprint 9 it knew private-key blocks, AWS access keys and GitHub tokens only, so a committed
model-provider key would have passed unnoticed. These tests prove the added shapes match a
realistic key, do not match the fixtures this repository deliberately keeps, and that no
committed file contains a match. Sample keys are assembled at runtime so this file never
contains one itself.
"""

from __future__ import annotations

import pytest

from tools.check_repository import SECRET_PATTERNS, _text_files

# Built by concatenation so the literal never appears in the tree.
REALISTIC = {
    "openai": "sk-" + "A1b2C3d4" * 6,
    "openai-project": "sk-proj-" + "Zy9Xw8Vu" * 8,
    "anthropic": "sk-ant-" + "api03-" + "k7J8h9G0" * 12,
    "gemini": "AIza" + "Sy" + "Q1w2E3r4T5y6U7i8O9p0A1s2D3f4G5h6J",
    "huggingface": "hf_" + "MnBvCxZl" * 5,
    "xai": "xai-" + "P0o9I8u7" * 9,
}

# Values the repository keeps on purpose and must keep being able to keep.
KEPT = (
    "sk-live-DO-NOT-ECHO-THIS-VALUE",
    "oak-test-key-openai-0123456789ab",
    "oak-test-key-huggingface-deadbeefcafe",
    "sk-test-fake",
    "hf_short",
)


def _matches(value: str) -> bool:
    return any(pattern.search(value) for pattern in SECRET_PATTERNS)


@pytest.mark.parametrize("family", sorted(REALISTIC))
def test_each_provider_key_shape_is_recognised(family: str) -> None:
    assert _matches(REALISTIC[family]), family


@pytest.mark.parametrize("value", KEPT)
def test_the_fixture_shapes_the_repository_keeps_are_not_flagged(value: str) -> None:
    assert not _matches(value), value


def test_no_committed_text_file_contains_a_provider_key_shape() -> None:
    offenders: list[str] = []
    for path in _text_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                offenders.append(f"{path}: {pattern.pattern}")
    assert offenders == []
