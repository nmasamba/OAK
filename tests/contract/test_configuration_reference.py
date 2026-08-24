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

# Read by the browser end-to-end suite (TypeScript) rather than by Python. The scan below
# covers `src`, `tools` and `scripts`, so these would otherwise look invented.
WEB_ONLY = frozenset({"OAK_E2E_DOCKER", "OAK_WEB_BASE_URL", "OAK_API_BASE_URL"})


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


def test_every_error_code_the_source_mentions_is_in_the_reference() -> None:
    """The reference claims completeness; enforce it rather than trusting the generator.

    The first version of the generator walked only `OAKError("CODE", ...)` call sites,
    so 55 codes never reached the document — eligibility reasons that are returned
    rather than raised, codes passed as a `code=` argument, and the HTTP and CLI mapping
    codes. On REST and MCP the message of a not-found error is opaqued, which leaves the
    code as the operator's only signal, so an absent code is a real supportability hole.
    """

    # Deliberately NOT `source_codes()`: sharing the generator's own regex made this
    # test blind to exactly the codes the generator missed — the six that entrypoints
    # print as `f"OAK-X: message"` rather than raising. A test that inherits the bug it
    # is meant to catch is worse than no test. This scans for the token itself.
    requirement_id = re.compile(r"^OAK-(?:FR|NFR)-")
    mentioned: set[str] = set()
    for root in ("src",):
        for path in (ROOT / root).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            mentioned.update(re.findall(r"OAK-[A-Z0-9-]{2,}", path.read_text(encoding="utf-8")))
    # Trailing-hyphen fragments come from f-string prefixes like `f"OAK-CAT-{domain}"`.
    codes = {
        code for code in mentioned if not requirement_id.match(code) and not code.endswith("-")
    }

    reference = (ROOT / "docs" / "error-codes.md").read_text(encoding="utf-8")
    _, _, index = reference.partition("## Full index")
    documented = set(re.findall(r"^\| `(OAK-[A-Z0-9-]+)`", index, re.M))

    undocumented = sorted(codes - documented)

    assert not undocumented, (
        "these codes are mentioned by the source but absent from docs/error-codes.md: "
        f"{undocumented}"
    )


def test_the_error_reference_is_not_stale() -> None:
    from scripts.generate_error_reference import render

    current = (ROOT / "docs" / "error-codes.md").read_text(encoding="utf-8")

    assert current == render(), (
        "docs/error-codes.md is stale; run python scripts/generate_error_reference.py"
    )


def test_every_make_target_is_documented_and_every_documented_target_exists() -> None:
    """The command table is where a contributor looks; it drifted four targets behind.

    `audit`, `lock`, `scan-images` and `web-build` all existed in the Makefile with no
    row in `docs/development.md`, so the only way to find them was to read the Makefile
    — which is exactly what the table exists to save you from.
    """

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    development = (ROOT / "docs" / "development.md").read_text(encoding="utf-8")

    # `[a-z-]+` would not match `test-e2e` or `web-e2e`, silently exempting the two
    # targets on both sides of a check whose entire purpose is that neither side drifts.
    targets = set(re.findall(r"^([a-z][a-z0-9-]*):", makefile, re.M))
    documented = set(re.findall(r"^\| `make ([a-z0-9-]+)`", development, re.M))

    assert "test-e2e" in targets and "test-e2e" in documented, (
        "the digit-bearing targets must be visible to this check"
    )

    assert targets, "no Make targets were parsed"
    assert not targets - documented, (
        f"Make targets missing from the docs/development.md table: {sorted(targets - documented)}"
    )
    assert not documented - targets, (
        f"documented Make targets that do not exist: {sorted(documented - targets)}"
    )


def test_web_side_environment_variables_are_documented_too() -> None:
    """The Python scan cannot see them, so nothing else would notice their absence.

    `OAK_WEB_BASE_URL` and `OAK_API_BASE_URL` are read by the Playwright suite in
    TypeScript. A reference that claims to list every variable OAK reads has to include
    them, and a check that only greps Python cannot enforce that on its own.
    """

    web_sources = [
        ROOT / "web" / "playwright.config.ts",
        ROOT / "web" / "e2e" / "support.ts",
    ]
    read_by_web: set[str] = set()
    for path in web_sources:
        if path.is_file():
            read_by_web.update(
                re.findall(r'process\.env\["(OAK_[A-Z0-9_]+)"\]', path.read_text(encoding="utf-8"))
            )

    assert read_by_web, "no web-side OAK_* variables were found; update the source list"
    undocumented = sorted(read_by_web - _documented())
    assert not undocumented, f"web-side variables missing from the reference: {undocumented}"


def test_documents_that_quote_the_residual_risk_count_agree_with_the_register() -> None:
    """Four documents quote this number and it drifted three times in one sprint.

    A count restated by hand in four places is a fact with four chances to be wrong.
    Pinning it is cheaper than noticing.
    """

    register = (ROOT / "docs" / "security" / "residual-risk.md").read_text(encoding="utf-8")
    entries = len(re.findall(r"^\| `RR-0\d{2}`", register, re.M))

    assert entries > 0, "no residual-risk entries were parsed"

    quoting = re.compile(r"(\d+) (?:stable-id entries|entries with stable ids)")
    wrong: list[str] = []
    for relative in (
        "STATUS.md",
        "CHANGELOG.md",
        "docs/release/0.7.0/release-decision.md",
        "docs/security/residual-risk.md",
        "docs/exec-plans/completed/OAK-S8-001-009-community-release-hardening.md",
    ):
        path = ROOT / relative
        if not path.is_file():
            continue
        for quoted in quoting.findall(path.read_text(encoding="utf-8")):
            if int(quoted) != entries:
                wrong.append(f"{relative} says {quoted}, register has {entries}")

    assert not wrong, wrong
