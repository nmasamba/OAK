# SPDX-License-Identifier: Apache-2.0
"""Repository hygiene, documentation policy, assurance-claim, and secret-pattern checks."""

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
# Vocabulary that asserts assurance OAK Community does not have. The corpus was honest
# before this gate existed; the gate makes it stay honest under edits and under future
# contributors who do not know the history. A release that says "production-ready" or
# "independently audited" is making a claim no accountable human has stood behind.
#
# An occurrence can be permitted by putting `<!-- assurance-claim-reviewed: why -->` on the
# same line or the line above. Use it for a sentence that *denies* the claim — the escape
# exists so that documenting what OAK is not stays possible.
ASSURANCE_PATTERNS = (
    re.compile(r"\bproduction[\s-]ready\b", re.IGNORECASE),
    re.compile(r"\benterprise[\s-]grade\b", re.IGNORECASE),
    re.compile(r"\bbattle[\s-]tested\b", re.IGNORECASE),
    re.compile(r"\b(?:bank|military)[\s-]grade\b", re.IGNORECASE),
    re.compile(r"\bunhackable\b", re.IGNORECASE),
    re.compile(r"\bsecure[\s-]by[\s-]default\b", re.IGNORECASE),
    re.compile(r"\b(?:SOC[\s-]?2|ISO[\s-]?27001|FedRAMP|HIPAA[\s-]compliant)\b"),
    re.compile(r"\bpenetration[\s-]test", re.IGNORECASE),
    re.compile(r"\b(?:externally|independently|third[\s-]party)[\s-]audited\b", re.IGNORECASE),
    re.compile(r"\bthird[\s-]party\s+(?:audit|assurance|review)\b", re.IGNORECASE),
    re.compile(r"\bcertified\b", re.IGNORECASE),
    re.compile(r"\bformally[\s-]verified\b", re.IGNORECASE),
)
ASSURANCE_ESCAPE = "<!-- assurance-claim-reviewed:"

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
            failures.extend(_assurance_claims(relative, text))
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                failures.append(f"{relative}: possible committed secret")
    return failures


def _assurance_claims(relative: Path, text: str) -> list[str]:
    """Report unqualified assurance claims in one markdown document."""

    lines = text.splitlines()
    failures: list[str] = []
    for number, line in enumerate(lines, start=1):
        previous = lines[number - 2] if number >= 2 else ""
        if ASSURANCE_ESCAPE in line or ASSURANCE_ESCAPE in previous:
            continue
        for pattern in ASSURANCE_PATTERNS:
            match = pattern.search(line)
            if match:
                failures.append(
                    f"{relative}:{number}: unqualified assurance claim {match.group(0)!r}"
                )
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
