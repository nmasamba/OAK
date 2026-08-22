# SPDX-License-Identifier: Apache-2.0
"""OAK-S8-003: the image-scan gate must fail on findings someone can act on.

`make audit` covers the Python and web dependency closures and never looks inside a
built image, which is how the API image came to ship `uv` and `uvx` with advisories in
their vendored Rust dependencies, plus a CRITICAL OpenSSL, unnoticed (`RR-035`).

The gate blocks on *fixable* findings only. That choice is the thing worth testing: a
CRITICAL with no vendor fix is information rather than an action, and a gate that blocked
on it would be silenced within a week. These tests pin both halves — fixable blocks,
unfixable reports — so neither can quietly invert.
"""

from typing import Any

from scripts.scan_images import BLOCKING, SCANNER, _classify


def _document(*vulnerabilities: dict[str, Any]) -> dict[str, Any]:
    return {
        "Results": [{"Target": "image.tar (debian 13.6)", "Vulnerabilities": list(vulnerabilities)}]
    }


def _finding(severity: str, package: str, fixed: str | None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "Severity": severity,
        "PkgName": package,
        "InstalledVersion": "1.0",
        "VulnerabilityID": f"CVE-TEST-{package}",
    }
    if fixed is not None:
        entry["FixedVersion"] = fixed
    return entry


def test_a_fixable_critical_is_reported_as_blocking() -> None:
    classified = _classify(_document(_finding("CRITICAL", "openssl", "3.5.6")))

    assert len(classified["fixable"]) == 1
    assert classified["fixable"][0]["package"] == "openssl"
    assert classified["fixable"][0]["fixed_in"] == "3.5.6"
    assert classified["unfixable"] == {}


def test_an_unfixable_critical_is_reported_but_does_not_block() -> None:
    """perl-base ships three of these in the API image and none has a vendor fix."""

    classified = _classify(_document(_finding("CRITICAL", "perl-base", None)))

    assert classified["fixable"] == []
    assert classified["unfixable"] == {"perl-base": ["CRITICAL CVE-TEST-perl-base"]}


def test_medium_and_low_findings_are_counted_but_never_block() -> None:
    classified = _classify(
        _document(
            _finding("MEDIUM", "libfoo", "2.0"),
            _finding("LOW", "libbar", "3.0"),
        )
    )

    assert classified["fixable"] == []
    assert classified["counts"]["MEDIUM"] == 1
    assert classified["counts"]["LOW"] == 1


def test_the_two_halves_are_separated_within_one_scan() -> None:
    classified = _classify(
        _document(
            _finding("CRITICAL", "perl-base", None),
            _finding("HIGH", "openssl", "3.5.6"),
            _finding("HIGH", "gzip", None),
        )
    )

    assert [f["package"] for f in classified["fixable"]] == ["openssl"]
    assert sorted(classified["unfixable"]) == ["gzip", "perl-base"]
    assert classified["counts"]["CRITICAL"] == 1
    assert classified["counts"]["HIGH"] == 2


def test_an_empty_scan_is_not_treated_as_a_finding() -> None:
    classified = _classify({"Results": [{"Target": "image.tar", "Vulnerabilities": None}]})

    assert classified["fixable"] == []
    assert classified["unfixable"] == {}
    assert sum(classified["counts"].values()) == 0


def test_the_scanner_is_pinned() -> None:
    """A floating scanner tag makes the gate's verdict depend on when it ran."""

    assert SCANNER.count(":") == 1
    assert SCANNER.rsplit(":", 1)[1] != "latest"


def test_only_critical_and_high_block() -> None:
    assert set(BLOCKING) == {"CRITICAL", "HIGH"}
