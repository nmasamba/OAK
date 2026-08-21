# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-007: every ADR a shipped document cites must resolve inside this repository.

Six architecture ADRs were cited by shipped documentation — the tenant-isolation
disclaimer leans on ADR-0012, the runner authority model on ADR-0015 — while their files
existed only in the governance repository. A reader outside that repository could not
resolve the justification for exactly the claims that most needed one, which weakens the
honesty those citations were supposed to support.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CITATION = re.compile(r"ADR-(\d{4})")
ADR_DIRECTORIES = ("docs/adr", "docs/adr/architecture")
# Historical records of work already done. They cite the ADRs that governed them at the
# time and are not part of the shipped reader-facing documentation set.
EXCLUDED = ("docs/exec-plans",)


def _shipped_documents() -> list[Path]:
    ignored = {".git", ".venv", ".uv-cache", "-.uv-cache", "node_modules", "dist", "sbom"}
    return [
        path
        for path in sorted(ROOT.rglob("*.md"))
        if not any(part in ignored for part in path.parts)
        and not any(str(path.relative_to(ROOT)).startswith(prefix) for prefix in EXCLUDED)
    ]


def _available() -> set[str]:
    numbers: set[str] = set()
    for directory in ADR_DIRECTORIES:
        for path in (ROOT / directory).glob("*.md"):
            match = re.match(r"^(\d{4})-", path.name)
            if match:
                numbers.add(match.group(1))
    return numbers


def test_every_cited_adr_resolves_to_a_file_in_this_repository() -> None:
    available = _available()
    unresolved: dict[str, list[str]] = {}
    for path in _shipped_documents():
        relative = str(path.relative_to(ROOT))
        for number in set(CITATION.findall(path.read_text(encoding="utf-8"))):
            if number not in available:
                unresolved.setdefault(f"ADR-{number}", []).append(relative)

    assert not unresolved, f"cited but not present: {unresolved}"


def test_mirrored_architecture_adrs_declare_where_they_came_from() -> None:
    """A mirrored copy that does not say it is a mirror invites divergent edits."""

    mirrored = sorted((ROOT / "docs" / "adr" / "architecture").glob("*.md"))

    assert mirrored, "no mirrored architecture ADRs were found"
    for path in mirrored:
        header = path.read_text(encoding="utf-8")[:600]
        assert "Mirrored from the OAK governance repository" in header, path.name
        assert "Do not edit this copy" in header, path.name


def test_the_adr_index_lists_every_adr_file() -> None:
    index = (ROOT / "docs" / "adr" / "README.md").read_text(encoding="utf-8")

    for directory in ADR_DIRECTORIES:
        for path in sorted((ROOT / directory).glob("*.md")):
            if path.name == "README.md":
                continue
            assert path.name in index, f"{path.name} is missing from the ADR index"


def test_the_product_reference_exception_is_scoped_to_the_governance_mirror() -> None:
    """The mirror may name other distributions; nothing else may.

    `docs/adr/architecture/0012` is a decision record about the boundary between the
    three distributions, so it necessarily names them. That exception must not become a
    general licence for reader-facing documentation to advertise unshipped editions.
    """

    from tools.check_repository import _is_governance_mirror

    assert _is_governance_mirror(Path("docs/adr/architecture/0012-control-plane-distributions.md"))
    assert not _is_governance_mirror(Path("docs/adr/0002-release-versioning.md"))
    assert not _is_governance_mirror(Path("README.md"))
    assert not _is_governance_mirror(Path("docs/interfaces.md"))
