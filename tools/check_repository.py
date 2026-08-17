# SPDX-License-Identifier: Apache-2.0
"""Repository hygiene, documentation policy, and secret-pattern checks."""

import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_PATTERNS = (
    re.compile(r"\bOAK[\s-]+Enterprise\b", re.IGNORECASE),
    re.compile(r"\bOAK[\s-]+Cloud\b", re.IGNORECASE),
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
)
TEXT_SUFFIXES = {".md", ".py", ".toml", ".yaml", ".yml", ".json", ".ts", ".tsx", ".js"}


def _text_files() -> Iterable[Path]:
    ignored_parts = {".git", ".venv", ".uv-cache", "dist", "node_modules"}
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in ignored_parts for part in path.parts):
            continue
        yield path


def _check_patterns() -> list[str]:
    failures: list[str] = []
    for path in _text_files():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        if path.suffix.lower() == ".md":
            for pattern in DOCUMENT_PATTERNS:
                if pattern.search(text):
                    failures.append(f"{relative}: prohibited product reference")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                failures.append(f"{relative}: possible committed secret")
    return failures


def _check_agent_ignores() -> list[str]:
    candidates = (
        "AGENTS.md",
        ".agent/session.json",
        ".agents/state.json",
        ".codex/config.toml",
        ".claude/settings.json",
        ".gemini/settings.json",
        ".mcp/state.json",
        ".windsurf/state.json",
        "CLAUDE.md",
        "GEMINI.md",
        ".github/prompts/local.prompt.md",
    )
    command = ["git", "check-ignore", "--quiet"]
    failures: list[str] = []
    for candidate in candidates:
        result = subprocess.run(
            [*command, candidate],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            failures.append(f".gitignore does not hide {candidate}")
    return failures


def main() -> int:
    failures = [*_check_patterns(), *_check_agent_ignores()]
    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
