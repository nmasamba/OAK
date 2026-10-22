# SPDX-License-Identifier: Apache-2.0
"""OAK-S14-007 (closing review D-7): the documents say what the code sends, no more.

`docs/research.md` names, in its "Sent" cell, exactly the term groups `derive_research_terms`
puts under `sent`, and names the local-only groups as never sent; the README and the manual
say research runs before candidates exist and on each consent, not once per case.
"""

from __future__ import annotations

from pathlib import Path

from oak.adapters.catalogue import LocalCatalogue, ResearchVocabularyLoader
from oak.compiler import derive_research_terms
from oak.contracts import SchemaRegistry, load_yaml_document

ROOT = Path(__file__).resolve().parents[2]
SENT_WORDS = {
    "pipeline_tags": "pipeline tags",
    "filters": "filters",
    "sort": "sort order",
    "inference_provider": "inference-provider flag",
    "topics": "topics",
    "archived": "archived flag",
    "pushed_within_days": "freshness window",
}
LOCAL_WORDS = ("capability keywords", "hardware class", "licence ids")


def _sent_cell() -> str:
    for line in (ROOT / "docs/research.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("| Search terms drawn from closed vocabularies"):
            return line.split("|")[1]
    raise AssertionError("docs/research.md has no 'Sent' row")


def test_the_sent_cell_names_what_leaves_and_only_that() -> None:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    intent = load_yaml_document((ROOT / "examples/example-intent.yaml").read_text(encoding="utf-8"))
    terms = derive_research_terms(
        intent,
        ResearchVocabularyLoader(ROOT / "catalogue").load(),
        LocalCatalogue(ROOT / "catalogue", registry).load().patterns,
    )
    sent_keys = set(terms["sent"]["hub"]) | set(terms["sent"]["github"])
    assert sent_keys == set(SENT_WORDS)
    cell = _sent_cell().lower()
    for key, words in SENT_WORDS.items():
        assert words in cell, f"the Sent cell does not name {key} ({words})"
    for words in LOCAL_WORDS:
        assert words not in cell, f"the Sent cell names a local-only group: {words}"
    page = (ROOT / "docs/research.md").read_text(encoding="utf-8")
    assert "applied on this machine only" in page


def test_the_documents_never_say_research_runs_once_per_case() -> None:
    for path in ("README.md", "docs/research.md", "docs/manual/manual.html"):
        text = (ROOT / path).read_text(encoding="utf-8").lower()
        assert "runs once per case" not in text, path
    assert "licence keywords" not in (ROOT / "docs/security/residual-risk.md").read_text(
        encoding="utf-8"
    )
