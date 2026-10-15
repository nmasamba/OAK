# SPDX-License-Identifier: Apache-2.0
"""Sprint 12 Studio UI guards, run by `make validate` before every commit.

G1  `web/src` renders no "enterprise", no raw variant id outside the label map, and no
    Google Fonts URL.
G2  The generated client offers no non-GET call beyond the ones it offered at the
    Sprint 12 kickoff; no button is named for approving, signing, dispatching,
    installing or applying unless its name starts with "Copy"; the copy control runs
    nothing (it imports no API client and makes no request).
G3  Every `<svg>` is decorative (`aria-hidden`) or an image (`role="img"` with an
    `aria-label`); every icon-only button has an `aria-label`.
G4  The bundle page still says that the web workspace holds no runner execution
    authority.
G5  `styles.css` paints no literal colour: every colour is a token in `tokens.css`; and it
    sets no partial opacity (only 0 or 1), because an element fading in lets an
    accessibility scan sample a blended colour and fail contrast at random.

The checks are textual and deliberately simple. They are regression guards for
properties that review established, not a substitute for the browser suite.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
WEB_SRC = WEB / "src"
LABEL_MAP = WEB_SRC / "ui" / "variantLabel.ts"
ICON = WEB_SRC / "ui" / "Icon.tsx"
COPY_PLATE = WEB_SRC / "ui" / "CopyPlate.tsx"
GENERATED_CLIENT = WEB_SRC / "generated" / "api.ts"
STYLES = WEB_SRC / "styles.css"

VARIANT_IDS = (
    "simpler_baseline",
    "minimum_sufficient",
    "balanced_enterprise",
    "high_assurance_sovereign",
)

# The non-GET operations the generated client offered on 2026-10-15, the Sprint 12
# kickoff. The web stays a REST client that mutates only through these; a new one is a
# product decision recorded in the OpenAPI contract, never a side effect of UI work.
KNOWN_MUTATIONS = frozenset(
    {
        "createDesignCase",
        "putModelCredential",
        "deleteModelCredential",
        "putModelSelection",
        "clearModelSelection",
        "verifyModelCredential",
        "discoverModels",
        "interpretDesignCase",
        "confirmDesignCase",
        "generateCandidates",
        "evaluateCandidate",
        "selectCandidate",
        "createAssurancePlan",
        "compileBundle",
        "cancelOperation",
        "importDesignCase",
    }
)

ENTERPRISE = re.compile(r"enterprise", re.IGNORECASE)
GOOGLE_FONTS = re.compile(r"fonts\.googleapis|fonts\.gstatic", re.IGNORECASE)
AUTHORITY_WORDS = re.compile(
    r"\b(?:approv\w*|sign\w*|dispatch\w*|install\w*|appl(?:y|ies|ied))\b",
    re.IGNORECASE,
)
EXPORTED_FUNCTION = re.compile(r"^export (?:async )?function (\w+)\(", re.MULTILINE)
HTTP_METHOD = re.compile(r"method:\s*\"(POST|PUT|PATCH|DELETE)\"")
BUTTON = re.compile(r"<(button|Keycap)\b([^>]*?)(/>|>(.*?)</\1>)", re.DOTALL)
ARIA_LABEL = re.compile(r"aria-label=")
STRING_LITERAL = re.compile(r"[\"'`]([^\"'`]*)[\"'`]")
JSX_EXPRESSION = re.compile(r"\{[^{}]*\}")
TAG = re.compile(r"<[^>]*>")
SVG_OPENING = re.compile(r"<svg\b[^>]*>", re.DOTALL)
PINNED_SENTENCE = re.compile(
    r"the web workspace holds no runner(?:\s|\{\" \"\})+execution authority"
)
HEX_COLOUR = re.compile(r"#(?:[0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})\b", re.IGNORECASE)
COLOUR_FUNCTION = re.compile(r"\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(", re.IGNORECASE)
REQUEST = re.compile(r"\bfetch\(|XMLHttpRequest|sendBeacon|generated/api")
PARTIAL_OPACITY = re.compile(r"\bopacity:\s*(?:0?\.\d+|1\.\d*[1-9]\d*|[2-9]\d*)\b")


def _source_files(suffixes: Iterable[str]) -> list[Path]:
    wanted = set(suffixes)
    return sorted(
        path
        for path in WEB_SRC.rglob("*")
        if path.is_file() and path.suffix in wanted and "node_modules" not in path.parts
    )


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def guard_1_words() -> list[str]:
    failures: list[str] = []
    for path in _source_files((".ts", ".tsx", ".css", ".html")):
        if path == LABEL_MAP or path.is_relative_to(WEB_SRC / "generated"):
            continue
        text = path.read_text(encoding="utf-8")
        for match in ENTERPRISE.finditer(text):
            failures.append(
                f"G1 {_relative(path)}:{_line_of(text, match.start())}: renders the word"
            )
        for variant in VARIANT_IDS:
            for match in re.finditer(re.escape(variant), text):
                failures.append(
                    f"G1 {_relative(path)}:{_line_of(text, match.start())}: raw variant id "
                    f"{variant!r} outside {_relative(LABEL_MAP)}"
                )
    for path in [*_source_files((".ts", ".tsx", ".css")), WEB / "index.html"]:
        text = path.read_text(encoding="utf-8")
        for match in GOOGLE_FONTS.finditer(text):
            failures.append(
                f"G1 {_relative(path)}:{_line_of(text, match.start())}: Google Fonts URL"
            )
    return failures


def _accessible_name(attributes: str, inner: str | None) -> str:
    """The best textual guess at a JSX button's accessible name."""

    label = re.search(r"aria-label=(?:\"([^\"]*)\"|\{`([^`]*)`\}|\{\"([^\"]*)\"\})", attributes)
    if label is not None:
        return next(group for group in label.groups() if group is not None)
    if inner is None:
        return ""
    literals = " ".join(STRING_LITERAL.findall(inner))
    text = TAG.sub(" ", JSX_EXPRESSION.sub(" ", inner))
    return f"{text} {literals}".strip()


def _is_icon_only(inner: str | None, attributes: str) -> bool:
    if inner is None:
        return "icon=" in attributes
    stripped = JSX_EXPRESSION.sub("", TAG.sub("", inner)).strip()
    has_glyph = "<Icon" in inner or "<svg" in inner
    has_expression = JSX_EXPRESSION.search(TAG.sub("", inner)) is not None
    return has_glyph and stripped == "" and not has_expression


def guard_2_authority() -> list[str]:
    failures: list[str] = []
    client = GENERATED_CLIENT.read_text(encoding="utf-8")
    starts = [(match.group(1), match.start()) for match in EXPORTED_FUNCTION.finditer(client)]
    for position, (name, start) in enumerate(starts):
        end = starts[position + 1][1] if position + 1 < len(starts) else len(client)
        body = client[start:end]
        if HTTP_METHOD.search(body) and name not in KNOWN_MUTATIONS:
            failures.append(
                f"G2 {_relative(GENERATED_CLIENT)}: new non-GET call {name!r}; the web is a "
                "REST client and a new mutation is a contract decision, not UI work"
            )
    for path in _source_files((".tsx",)):
        text = path.read_text(encoding="utf-8")
        for match in BUTTON.finditer(text):
            attributes = match.group(2)
            inner = match.group(4)
            name = _accessible_name(attributes, inner)
            if AUTHORITY_WORDS.search(name) and not name.lstrip().startswith("Copy"):
                failures.append(
                    f"G2 {_relative(path)}:{_line_of(text, match.start())}: button named "
                    f"{name.strip()!r} claims an authority the web does not hold"
                )
    plate = COPY_PLATE.read_text(encoding="utf-8")
    for match in REQUEST.finditer(plate):
        failures.append(
            f"G2 {_relative(COPY_PLATE)}:{_line_of(plate, match.start())}: the copy control "
            f"must run nothing, found {match.group(0)!r}"
        )
    return failures


def guard_3_pictures() -> list[str]:
    failures: list[str] = []
    for path in _source_files((".tsx",)):
        text = path.read_text(encoding="utf-8")
        for match in SVG_OPENING.finditer(text):
            opening = match.group(0)
            if path == ICON and "{...accessibility}" in opening:
                # Icon.tsx spreads the one of two attribute sets it computed; both are
                # checked here by their literal source.
                if '"aria-hidden": true' not in text or 'role: "img"' not in text:
                    failures.append(f"G3 {_relative(ICON)}: Icon must be hidden or an image")
                continue
            decorative = "aria-hidden" in opening
            image = 'role="img"' in opening and "aria-label" in opening
            if not decorative and not image:
                failures.append(
                    f"G3 {_relative(path)}:{_line_of(text, match.start())}: <svg> is neither "
                    'aria-hidden nor role="img" with an aria-label'
                )
        for match in BUTTON.finditer(text):
            attributes = match.group(2)
            inner = match.group(4)
            if _is_icon_only(inner, attributes) and not ARIA_LABEL.search(attributes):
                failures.append(
                    f"G3 {_relative(path)}:{_line_of(text, match.start())}: icon-only button "
                    "without an aria-label"
                )
    return failures


def guard_4_sentence() -> list[str]:
    for path in _source_files((".tsx",)):
        if PINNED_SENTENCE.search(path.read_text(encoding="utf-8")):
            return []
    return ["G4 web/src: no page says that the web workspace holds no runner execution authority"]


def guard_5_tokens() -> list[str]:
    failures: list[str] = []
    text = STYLES.read_text(encoding="utf-8")
    for pattern, what in (
        (HEX_COLOUR, "hex colour"),
        (COLOUR_FUNCTION, "colour function"),
        (PARTIAL_OPACITY, "partial opacity"),
    ):
        for match in pattern.finditer(text):
            failures.append(
                f"G5 {_relative(STYLES)}:{_line_of(text, match.start())}: literal {what} "
                f"{match.group(0)!r}; use a token from web/src/tokens.css and an opacity "
                "of 0 or 1"
            )
    return failures


def main() -> int:
    failures = [
        *guard_1_words(),
        *guard_2_authority(),
        *guard_3_pictures(),
        *guard_4_sentence(),
        *guard_5_tokens(),
    ]
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return 1
    print("Studio UI guards G1-G5 passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
