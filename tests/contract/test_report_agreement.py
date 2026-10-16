# SPDX-License-Identifier: Apache-2.0
"""OAK-S13-002: the report says what the workspace says, in the same words.

The variant labels, the provenance words and the install steps exist once in the web and
once in Python. These tests read the TypeScript sources and fail when the two drift.
"""

from __future__ import annotations

import re
from pathlib import Path

from oak.application.report.composer import INSTALL_STEPS
from oak.application.report.labels import PROVENANCE_WORDS, VARIANT_LABELS, variant_label

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web" / "src"
ENTRY = re.compile(r'^\s*(\w+):\s*"([^"]+)",?\s*$', re.MULTILINE)


def _object_literal(source: str, name: str) -> dict[str, str]:
    start = source.index(name)
    body = source[source.index("{", start) + 1 : source.index("}", start)]
    return dict(ENTRY.findall(body))


def test_the_variant_labels_match_the_workspace() -> None:
    source = (WEB / "ui" / "variantLabel.ts").read_text(encoding="utf-8")
    assert _object_literal(source, "VARIANT_LABELS") == VARIANT_LABELS
    # The fallback the TypeScript documents: "some_new_kind" → "Some new kind".
    assert variant_label("some_new_kind") == "Some new kind"
    assert variant_label(None) == "Unknown"


def test_the_provenance_words_match_the_workspace() -> None:
    source = (WEB / "claims.tsx").read_text(encoding="utf-8")
    classes = _object_literal(source, "SOURCE_CLASSES")
    labels = _object_literal(source, "CLASS_LABELS")
    for provenance_source, claim_class in classes.items():
        assert PROVENANCE_WORDS[provenance_source] == labels[claim_class]
    assert PROVENANCE_WORDS["unknown"] == labels["unknown"]


def test_the_install_steps_match_the_copy_plate() -> None:
    source = (WEB / "pages" / "BundlePage.tsx").read_text(encoding="utf-8")
    start = source.index("const INSTALL_STEPS = [")
    body = source[start : source.index("].join", start)]
    assert tuple(re.findall(r'"([^"]+)"', body)) == INSTALL_STEPS
