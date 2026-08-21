# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-003: the no-assurance-claim property must be enforced, not reviewed once.

The documentation corpus was honest when this gate was written — no document claimed
production readiness, certification or an external audit. That is a property worth
keeping under future edits by people who do not know the history, and a reviewer cannot
be the mechanism: nobody re-reads thirty markdown files for one adjective.

The escape hatch exists so that *denying* a claim stays possible; these tests prove the
gate is neither vacuous nor unescapable.
"""

from pathlib import Path

import pytest

from tools.check_repository import _assurance_claims

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "sentence",
    [
        "OAK Community is production-ready today.",
        "A production ready control plane for your estate.",
        "Enterprise-grade assurance out of the box.",
        "This build is battle-tested.",
        "Bank-grade cryptography protects every plan.",
        "The runner is secure by default.",
        "We are SOC 2 compliant.",
        "ISO 27001 certification is complete.",
        "A penetration test was performed in August.",
        "The release was independently audited.",
        "Third-party assurance covers the runner.",
        "The signing path is formally verified.",
    ],
)
def test_the_gate_rejects_an_unqualified_assurance_claim(sentence: str) -> None:
    failures = _assurance_claims(Path("docs/example.md"), sentence)

    assert failures, f"the gate missed: {sentence}"
    assert "unqualified assurance claim" in failures[0]


def test_a_denial_can_be_written_with_the_documented_escape() -> None:
    """Saying what OAK is *not* must stay possible, or the gate is unusable."""

    same_line = (
        "Nothing here is third-party assurance. "
        "<!-- assurance-claim-reviewed: this sentence denies the claim -->"
    )
    preceding_line = (
        "<!-- assurance-claim-reviewed: this sentence denies the claim -->\n"
        "OAK Community is not production-ready."
    )

    assert _assurance_claims(Path("docs/example.md"), same_line) == []
    assert _assurance_claims(Path("docs/example.md"), preceding_line) == []


def test_the_escape_does_not_leak_to_unrelated_lines() -> None:
    """The marker covers its own line and the one below it, not a whole file."""

    text = (
        "<!-- assurance-claim-reviewed: reason -->\n"
        "OAK Community is not production-ready.\n"
        "\n"
        "OAK Community is production-ready.\n"
    )

    failures = _assurance_claims(Path("docs/example.md"), text)

    assert len(failures) == 1
    assert failures[0].startswith("docs/example.md:4:")


def test_the_shipped_corpus_makes_no_unqualified_assurance_claim() -> None:
    """The property the gate exists to protect, asserted over the real tree."""

    ignored = {".git", ".venv", ".uv-cache", "-.uv-cache", "dist", "node_modules", "sbom"}
    failures: list[str] = []
    for path in sorted(ROOT.rglob("*.md")):
        if any(part in ignored for part in path.parts):
            continue
        failures.extend(_assurance_claims(path.relative_to(ROOT), path.read_text(encoding="utf-8")))

    assert not failures, failures
