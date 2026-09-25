# SPDX-License-Identifier: Apache-2.0
"""The browser suite (`web/e2e`) starts processes only through its one guarded helper.

The Compose-backed specs and the manual capture used to shell out to a bare
`docker compose` each. From the repository root that resolves to the default
`oak-community` project whatever origins the suite was pointed at, so a run aimed at a
throwaway stack would stop the default stack's worker and delete its stored Hugging Face
token. `compose()` in `web/e2e/support.ts` now owns the only such call and refuses to run
it against a project that does not serve the origins under test. The Playwright suite is
not part of `make check` (`RR-021`), so this is what keeps a new spec from quietly going
back to its own `execSync`. It checks structure, not intent: a deliberate edit to
support.ts itself is reviewed as a change to the guard.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
E2E = ROOT / "web" / "e2e"
HELPER = E2E / "support.ts"
# The extensions Playwright collects test files from (web/playwright.config.ts narrows
# nothing), which also covers the modules those files import.
SCRIPT_SUFFIXES = {
    f".{prefix}{language}s{jsx}"
    for prefix in ("", "m", "c")
    for language in ("j", "t")
    for jsx in ("", "x")
}
THE_ONE_IMPORT = 'import { execSync } from "node:child_process";'


def test_only_the_guarded_helper_starts_processes() -> None:
    scripts = sorted(p for p in E2E.rglob("*") if p.is_file() and p.suffix in SCRIPT_SUFFIXES)
    assert HELPER in scripts, "web/e2e/support.ts moved; update this test"
    spawning = [
        path.relative_to(ROOT).as_posix()
        for path in scripts
        if path != HELPER and "child_process" in path.read_text(encoding="utf-8")
    ]
    assert not spawning, f"start processes through compose() in web/e2e/support.ts: {spawning}"


def test_the_helper_keeps_its_one_runner_private() -> None:
    text = HELPER.read_text(encoding="utf-8")
    imports = [line.strip() for line in text.splitlines() if "child_process" in line]
    assert imports == [THE_ONE_IMPORT], f"support.ts may import only execSync: {imports}"
    assert text.count("execSync(") == 1, "support.ts must run processes in one place only"
    exports = re.findall(r"^export\s*\{[^}]*\}|^export\b[^\n]*", text, re.MULTILINE)
    assert not [e for e in exports if "dockerCompose" in e], (
        "export compose(), which checks the target first, not the raw dockerCompose()"
    )
    assert not re.findall(r"\bdockerCompose\b(?!\()", text), (
        "dockerCompose may only be called, never passed, aliased or exported as a value"
    )
