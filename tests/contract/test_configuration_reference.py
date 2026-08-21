# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-006: the configuration reference must not drift from the code.

`docs/configuration.md` is the only place an operator can learn what OAK reads from
the environment — including the variables that change a security property, such as
where private signing keys live and whether the API may bind off loopback. A reference
that silently misses a variable is worse than no reference, so it is pinned here.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "docs" / "configuration.md"
VARIABLE = re.compile(r"OAK_[A-Z0-9_]+")
SOURCE_ROOTS = ("src", "tools", "scripts")

# Read by the browser end-to-end suite rather than by Python, and documented as such.
WEB_ONLY = frozenset({"OAK_E2E_DOCKER"})


def _documented() -> set[str]:
    text = REFERENCE.read_text(encoding="utf-8")
    return {
        match
        for line in text.splitlines()
        if line.startswith("| `OAK_")
        for match in VARIABLE.findall(line.split("|")[1])
    }


def _read_by_source() -> set[str]:
    found: set[str] = set()
    for root in SOURCE_ROOTS:
        for path in (ROOT / root).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            found.update(re.findall(r'"(OAK_[A-Z0-9_]+)"', text))
    return found


def test_every_environment_variable_the_source_reads_is_documented() -> None:
    undocumented = sorted(_read_by_source() - _documented())

    assert not undocumented, (
        "these environment variables are read by the source but absent from "
        f"docs/configuration.md: {undocumented}"
    )


def test_the_reference_documents_nothing_the_source_does_not_read() -> None:
    """A row for a variable nothing reads is a promise OAK does not keep."""

    read_anywhere = _read_by_source() | WEB_ONLY
    # OAK_TEST_DATABASE_URL is read by the test suite, which is not a source root.
    read_anywhere.add("OAK_TEST_DATABASE_URL")

    invented = sorted(_documented() - read_anywhere)

    assert not invented, f"docs/configuration.md documents variables nothing reads: {invented}"


def test_the_safety_relevant_variables_are_marked_as_such() -> None:
    """These four are the ones that move a trust boundary if changed."""

    text = REFERENCE.read_text(encoding="utf-8")
    for name in (
        "OAK_ALLOW_NON_LOOPBACK",
        "OAK_TRUST_DIRECTORY",
        "OAK_RUNNER_TRUST_ANCHORS",
        "OAK_DATABASE_URL",
    ):
        row = next(line for line in text.splitlines() if line.startswith(f"| `{name}`"))
        assert row.rstrip().endswith("| Yes |"), f"{name} must be marked safety-relevant"
