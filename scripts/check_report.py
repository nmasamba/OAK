# SPDX-License-Identifier: Apache-2.0
"""Report guards R1 to R4: the architecture report is honest by construction, and stays so.

The guard composes the report for the reference case live, at each step a report can be
recorded from, and checks every string, number and picture in it. It never reads a stored
golden: a composer change that breaks a rule fails here even if someone refreshed the
golden file with it.

R1  No assurance vocabulary, no "enterprise" and no raw variant id in any string.
R2  Every number is a quantity with a unit, a source and a basis; a fixture estimator's
    number is a synthetic estimate; every `unknown` has its reason; and template text
    holds no bare number (counts are words, figures are quantities).
R3  Every section that draws a picture carries its table, and the table covers the picture.
R4  Every text and background pair in the print palette reaches 4.5:1.
"""

from __future__ import annotations

import re
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oak.domain.vocabulary import forbidden_words  # noqa: E402

SOURCE = re.compile(r"^(template|[A-Za-z][A-Za-z0-9._:/-]*@[^#\s]+#(/\S*)?)$")
# A numeral that stands alone. Digits inside identifiers, versions, dates and digests
# (candidate-03, 0.1.7, 2026-08-18, sha256:…, OAK-FR-CAT-001) touch a letter or one of
# these separators and do not count.
BARE_NUMBER = re.compile(r"(?<![\w.:/@~#-])\d+(?:,\d{3})*(?:\.\d+)?(?![\w.:/%-])")
MINIMUM_CONTRAST = 4.5


def _walk(value: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, f"{path}/{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}/{index}")


def guard_r1_words(document: dict[str, Any], label: str) -> list[str]:
    failures = []
    for path, value in _walk(document):
        texts = [value] if isinstance(value, str) else []
        if isinstance(value, dict):
            texts.extend(key for key in value if isinstance(key, str))
        for text in texts:
            for word in forbidden_words(text):
                failures.append(f"R1 {label}{path}: {word!r} in {text[:60]!r}")
    return failures


def _template_strings(section: dict[str, Any]) -> Iterator[tuple[str, str]]:
    yield "title", section["title"]
    yield "subtitle", section["subtitle"]
    for index, block in enumerate(section["blocks"]):
        where = f"blocks/{index}"
        for key in ("heading", "caption", "label", "what", "step", "note"):
            if isinstance(block.get(key), str):
                yield f"{where}/{key}", block[key]
        for column in block.get("columns", []):
            yield f"{where}/columns", column
        if block.get("source") == "template" and isinstance(block.get("text"), str):
            yield f"{where}/text", block["text"]
        for item in block.get("items", []):
            yield f"{where}/items/label", item["label"]


# Records whose figures come from a fixture set: an offline evaluation and a fixture
# component. Their numbers are never "measured" or "counted" in a report.
SYNTHETIC_SOURCES = ("evaluation-result.", "component.fixture-")


def guard_r2_numbers(document: dict[str, Any], label: str) -> list[str]:
    failures = []
    for path, value in _walk(document):
        if not isinstance(value, dict):
            continue
        kind = value.get("type")
        if kind == "quantity":
            if value.get("value") is None:
                failures.append(f"R2 {label}{path}: a quantity with no value must be unknown")
            if not str(value.get("unit") or "").strip():
                failures.append(f"R2 {label}{path}: quantity has no unit")
            elif str(value["unit"]).strip().lower() == "as recorded":
                failures.append(f"R2 {label}{path}: 'as recorded' is not a unit; say unknown")
            if str(value.get("source") or "").startswith(SYNTHETIC_SOURCES) and value.get(
                "basis"
            ) in {"measured", "counted"}:
                failures.append(
                    f"R2 {label}{path}: a figure from a fixture run is labelled "
                    f"{value['basis']}, not synthetic"
                )
            if not SOURCE.match(str(value.get("source") or "")):
                failures.append(f"R2 {label}{path}: quantity has no source")
            estimator = value.get("estimator")
            if isinstance(estimator, str) and estimator.startswith("fixture-"):
                if value.get("basis") != "synthetic estimate":
                    failures.append(
                        f"R2 {label}{path}: a fixture estimate is not labelled synthetic"
                    )
            elif value.get("basis") in {"estimated", "synthetic estimate"} and not estimator:
                failures.append(f"R2 {label}{path}: an estimate names no estimator")
        elif kind == "unknown" and not str(value.get("reason") or "").strip():
            failures.append(f"R2 {label}{path}: unknown without a reason")
        elif (
            kind == "status"
            and value.get("status") == "unknown"
            and not str(value.get("reason") or "").strip()
        ):
            failures.append(f"R2 {label}{path}: an unknown status without a reason")
        if "source" in value and not SOURCE.match(str(value["source"])):
            failures.append(f"R2 {label}{path}: source {value['source']!r} names no record")
    case_title = ""
    for section in document["sections"]:
        if section["id"] == "cover":
            for block in section["blocks"]:
                for item in block.get("items", []):
                    if item["label"] == "Case":
                        case_title = item["value"].get("text", "")
    for index, section in enumerate(document["sections"]):
        for where, text in _template_strings(section):
            scanned = text.replace(case_title, "") if case_title else text
            match = BARE_NUMBER.search(scanned)
            if match:
                failures.append(
                    f"R2 {label}/sections/{index}/{where}: bare number {match.group(0)!r} in "
                    f"template text {text[:60]!r}"
                )
    return failures


def guard_r3_pictures(document: dict[str, Any], label: str) -> list[str]:
    failures = []
    for index, section in enumerate(document["sections"]):
        tables = {block["id"]: block for block in section["blocks"] if block["kind"] == "table"}
        for block in section["blocks"]:
            if block["kind"] not in {"diagram", "chart"}:
                continue
            where = f"R3 {label}/sections/{index} ({section['id']})"
            table = tables.get(block["table_id"])
            if table is None:
                failures.append(f"{where}: {block['kind']} has no table {block['table_id']!r}")
                continue
            cells = (
                " ".join(
                    str(cell.get("text") or cell.get("short") or cell.get("word") or "")
                    for row in table["rows"]
                    for cell in row["cells"]
                )
                + " "
                + " ".join(table["columns"])
            )
            if block["kind"] == "diagram":
                missing = [node["id"] for node in block["nodes"] if node["id"] not in cells]
            else:
                missing = [
                    series["objective"]
                    for series in block["series"]
                    if series["objective"] not in cells
                ]
                missing += [
                    bar["label"]
                    for series in block["series"]
                    for bar in series["bars"]
                    if bar["label"] not in cells
                ]
            if missing:
                failures.append(f"{where}: the table does not list {sorted(set(missing))}")
    return failures


def _luminance(colour: str) -> float:
    channels = [int(colour[position : position + 2], 16) / 255 for position in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground: str, background: str) -> float:
    lighter, darker = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def guard_r4_contrast() -> list[str]:
    try:
        from oak.adapters.report.palette import TEXT_PAIRS
    except ImportError:
        return ["R4 the print palette (oak.adapters.report.palette.TEXT_PAIRS) is missing"]
    failures = []
    for name, foreground, background in TEXT_PAIRS:
        ratio = contrast(foreground, background)
        if ratio < MINIMUM_CONTRAST:
            failures.append(
                f"R4 {name}: {foreground} on {background} is {ratio:.2f}:1, under 4.5:1"
            )
    return failures


def reference_reports() -> dict[str, dict[str, Any]]:
    from tests.report_support import STOPS, build_reference_case, compose_reference

    reports = {}
    for stop in STOPS:
        with tempfile.TemporaryDirectory(prefix=f"oak-report-{stop}-") as directory:
            reports[stop] = compose_reference(build_reference_case(Path(directory), stop))
    return reports


def check(reports: dict[str, dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    for stop, document in reports.items():
        failures += guard_r1_words(document, stop)
        failures += guard_r2_numbers(document, stop)
        failures += guard_r3_pictures(document, stop)
    failures += guard_r4_contrast()
    return failures


def main() -> int:
    failures = check(reference_reports())
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return 1
    print("Report guards R1-R4 passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
