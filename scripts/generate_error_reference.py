# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-006: generate the operator-facing OAK-* error-code reference.

`docs/compatibility.md` makes stable `OAK-*` codes part of the public surface, and both
REST and MCP replace a not-found message with an opaque string — so on those transports
the code is the operator's only signal. Until this release, 245 of the 267 codes appeared
in no documentation at all.

The reference is generated from the source rather than written by hand, for the same
reason the OpenAPI document is: a hand-maintained list of 260-odd codes drifts within one
sprint. Messages are read out of the raise sites, never invented, so a code whose message
is built at runtime is reported as dynamic instead of being given a plausible-looking one.

    python scripts/generate_error_reference.py           # rewrite the document
    python scripts/generate_error_reference.py --check    # fail if it is stale
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "oak"
REFERENCE = ROOT / "docs" / "error-codes.md"
CODE_LITERAL = re.compile(r'"(OAK-[A-Z0-9-]+)"')
REQUIREMENT_ID = re.compile(r"^OAK-(?:FR|NFR)-")

# Families are matched in order; the first prefix that matches wins, so more specific
# prefixes come first. The catch-all keeps a new code visible rather than dropped.
FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Workspace, artifacts and import/export",
        ("OAK-WORKSPACE-", "OAK-ARTIFACT-", "OAK-IMPORT-", "OAK-EXPORT-"),
    ),
    (
        "Design case: intake, interpretation, confirmation",
        (
            "OAK-BRIEF-",
            "OAK-INTAKE-",
            "OAK-SOURCE-",
            "OAK-INTENT-",
            "OAK-CASE-",
            "OAK-CONFIRM-",
            "OAK-QUESTION-",
            "OAK-DESIGN-",
            "OAK-PROPOSAL-",
        ),
    ),
    (
        "Candidates, evaluation, selection and planning",
        (
            "OAK-CANDIDATE-",
            "OAK-CANDIDATES-",
            "OAK-EVALUATION-",
            "OAK-EVALUATE-",
            "OAK-SELECT-",
            "OAK-ASSURE-",
            "OAK-ASSURANCE-",
            "OAK-PLAN-",
            "OAK-BUNDLE-",
            "OAK-TARGET-",
            "OAK-OBJECTIVE-",
        ),
    ),
    ("Catalogue", ("OAK-CAT-", "OAK-CATALOGUE-")),
    ("Policy", ("OAK-POLICY-",)),
    ("Extensions", ("OAK-EXTENSION-", "OAK-SDK-")),
    (
        "Runner, signing, approval and dispatch",
        (
            "OAK-RUNNER-",
            "OAK-SIGN-",
            "OAK-SIGNATURE-",
            "OAK-APPROVAL-",
            "OAK-APPROVE-",
            "OAK-REVOKE-",
            "OAK-DISPATCH-",
            "OAK-INGEST-",
            "OAK-KEYS-",
            "OAK-KEY-",
            "OAK-TRUST-",
            "OAK-GITOPS-",
        ),
    ),
    ("Rendering and deployment", ("OAK-RENDER-", "OAK-DEPLOYMENT-")),
    ("Remote CLI", ("OAK-REMOTE-",)),
    ("MCP", ("OAK-TOOL-", "OAK-MCP-")),
    ("Headless validation", ("OAK-VALIDATE-",)),
    (
        "Durable operations and the outbox",
        (
            "OAK-OPERATION-",
            "OAK-OUTBOX-",
            "OAK-JOB-",
            "OAK-WORKER-",
            "OAK-PROJECTION-",
            "OAK-CONSUMER-",
        ),
    ),
    (
        "Concurrency, identity and requests",
        (
            "OAK-IDEMPOTENCY-",
            "OAK-EXPECTED-",
            "OAK-PRECONDITION-",
            "OAK-CORRELATION-",
            "OAK-ACTOR-",
            "OAK-TENANT-",
            "OAK-REQUEST-",
            "OAK-DIRECTORY-",
            "OAK-TIME-",
            "OAK-INTERFACE-",
        ),
    ),
    (
        "Configuration and process startup",
        ("OAK-DATABASE-", "OAK-CONFIG-", "OAK-SERVER-", "OAK-BIND-"),
    ),
    ("Everything else", ("OAK-",)),
)

PREAMBLE = """<!-- SPDX-License-Identifier: Apache-2.0 -->

# Error-code reference

Every `OAK-*` code the source can raise, what it means, and which surfaces it reaches.

**This file is generated.** Run `python scripts/generate_error_reference.py` after
changing a code; `make validate` fails if it is stale. Messages are read out of the raise
sites, so a code whose message is built at runtime shows as *dynamic* rather than being
given an invented description.

## How codes reach you

| Surface | Where the code appears |
|---|---|
| CLI | `CODE: message` on stderr. Exit `0` success, `2` refusal or invalid input, `4` version or idempotency conflict |
| REST | The `code` field of the problem-details body. For a not-found code the `detail` is replaced with an opaque string, so **the code is your only signal** |
| MCP | The `code` field of the tool result's `structuredContent`, with `isError: true`. Not-found codes are opaqued as on REST |
| Runner | `CODE: message` on stderr, exit `70` |

Codes are a public surface governed by [compatibility.md](compatibility.md): new codes may
be added freely, but an existing code may not change meaning or disappear while a
documented flow uses it.

## The ones you are most likely to meet

| Code | What happened | What to do |
|---|---|---|
| `OAK-EXPECTED-VERSION` | The case advanced since you read it | Re-read the case and retry with the current version. A normal concurrency refusal, not a fault |
| `OAK-PRECONDITION-INVALID` | Your `If-Match` header is unusable — weak entity tag, or empty | Send a strong ETag. **Retrying will not help**; this is deliberately not a 409 for that reason |
| `OAK-IDEMPOTENCY-CONFLICT` | An idempotency key was reused with different input | Use a new key, or resend the original input |
| `OAK-IDEMPOTENCY-KEY` | The key is shorter than 16 characters | Lengthen it. Longer keys are fine |
| `OAK-WORKSPACE-NOT-FOUND` | There is no workspace at this location | Check the working directory, or run `oak init` |
| `OAK-ARTIFACT-NOT-FOUND` | The workspace is present; this artifact reference did not match | Check the id, version and digest triple. The workspace is fine |
| `OAK-WORKSPACE-CORRUPT` | The manifest or an indexed object failed verification | Run `python scripts/verify_deployment.py --workspace <dir>`. See [operations.md](operations.md#restore) |
| `OAK-REMOTE-UNSUPPORTED` | A local-only command was run with `--server` | Signing, approval, dispatch, keys, extensions and policy are local-only by design |
| `OAK-REMOTE-UNAVAILABLE` | The control plane could not be reached | Check the URL and that `oak-api` is running |
| `OAK-TENANT-MISMATCH` | A different tenant was requested | Reported as not-found on purpose, so it leaks no existence information |
| `OAK-ACTOR-DENIED` | A different actor was claimed | The local actor is bound by `OAK_LOCAL_ACTOR` |

## Full index

"""


def source_codes() -> set[str]:
    """Every `OAK-*` identifier the source mentions, excluding requirement IDs.

    Requirement identifiers (`OAK-FR-*`, `OAK-NFR-*`) share the prefix but are
    traceability references to the governance repository, not error codes.
    """

    found: set[str] = set()
    for path in _source_files():
        found.update(CODE_LITERAL.findall(path.read_text(encoding="utf-8")))
    return {code for code in found if not REQUIREMENT_ID.match(code)}


def _source_files() -> list[Path]:
    return [path for path in sorted(SOURCE.rglob("*.py")) if "__pycache__" not in path.parts]


def _codes() -> dict[str, dict[str, object]]:
    """Every `OAK-*` code the source can surface, with its site and message forms.

    Two passes, because raise sites are not the whole story. The AST pass finds
    `OAKError("CODE", "message")` and recovers the message text. A second literal pass
    catches every other code the source can surface — eligibility reasons like
    `OAK-CAT-EVIDENCE-STALE` that are returned rather than raised, codes passed as a
    `code=` argument, and the HTTP and CLI mapping codes. Leaving those out made the
    reference's own completeness claim false for 55 codes.
    """

    found: dict[str, dict[str, object]] = {}

    def entry_for(code: str) -> dict[str, object]:
        return found.setdefault(code, {"sites": [], "messages": set(), "dynamic": False})

    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else None
            if name != "OAKError" or not node.args:
                continue
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                continue
            entry = entry_for(first.value)
            sites = entry["sites"]
            assert isinstance(sites, list)
            sites.append(f"{path.relative_to(ROOT)}:{node.lineno}")
            if len(node.args) > 1:
                message = node.args[1]
                if isinstance(message, ast.Constant) and isinstance(message.value, str):
                    messages = entry["messages"]
                    assert isinstance(messages, set)
                    messages.add(message.value)
                else:
                    entry["dynamic"] = True

        for number, line in enumerate(text.splitlines(), start=1):
            for code in CODE_LITERAL.findall(line):
                if REQUIREMENT_ID.match(code):
                    continue
                entry = entry_for(code)
                sites = entry["sites"]
                assert isinstance(sites, list)
                sites.append(f"{path.relative_to(ROOT)}:{number}")

    return found


def _family(code: str) -> str:
    for name, prefixes in FAMILIES:
        if any(code.startswith(prefix) for prefix in prefixes):
            return name
    return "Everything else"


def render() -> str:
    codes = _codes()
    grouped: dict[str, list[str]] = defaultdict(list)
    for code in codes:
        grouped[_family(code)].append(code)

    lines = [PREAMBLE.rstrip("\n"), ""]
    lines.append(f"{len(codes)} codes across {len([k for k in grouped if grouped[k]])} families.")
    lines.append("")
    for name, _ in FAMILIES:
        members = sorted(grouped.get(name, []))
        if not members:
            continue
        lines.append(f"### {name} ({len(members)})")
        lines.append("")
        lines.append("| Code | Meaning | First raise site |")
        lines.append("|---|---|---|")
        for code in members:
            entry = codes[code]
            raw_messages = entry["messages"]
            assert isinstance(raw_messages, set)
            messages = sorted(str(message) for message in raw_messages)
            raw_sites = entry["sites"]
            assert isinstance(raw_sites, list)
            sites = sorted(str(site) for site in raw_sites)
            if not messages and entry["dynamic"]:
                meaning = "*dynamic message*"
            elif not messages:
                # Surfaced without a literal message: an eligibility reason, a mapping
                # target, or a code passed in as an argument.
                meaning = "*reason or mapping code; carries no fixed message*"
            elif len(messages) == 1 and not entry["dynamic"]:
                meaning = messages[0]
            else:
                shown = "; ".join(messages[:3])
                extra = len(messages) - 3
                suffix = f"; and {extra} more" if extra > 0 else ""
                dynamic = " (some dynamic)" if entry["dynamic"] else ""
                meaning = f"{shown}{suffix}{dynamic}"
            meaning = meaning.replace("|", r"\|")
            lines.append(f"| `{code}` | {meaning} | `{sites[0]}` |")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the document is stale")
    arguments = parser.parse_args()

    rendered = render()
    if arguments.check:
        current = REFERENCE.read_text(encoding="utf-8") if REFERENCE.is_file() else ""
        if current != rendered:
            print(
                "docs/error-codes.md is stale; run python scripts/generate_error_reference.py",
                file=sys.stderr,
            )
            return 1
        return 0

    REFERENCE.write_text(rendered, encoding="utf-8")
    print(f"wrote {REFERENCE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
