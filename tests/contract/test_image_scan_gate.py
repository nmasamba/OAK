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

from pathlib import Path
from typing import Any

from scripts.scan_images import (
    BLOCKING,
    SCANNER,
    _classify,
    _final_stage_base,
    _from_lines,
    _provenance_document,
    _sbom_name,
)

ROOT = Path(__file__).resolve().parents[2]


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


def test_provenance_records_the_final_stage_base_not_a_build_stage() -> None:
    """The SBOM and provenance must describe the image that ships (RR-038).

    The 0.7.0 scan found `uv` in the runtime layer precisely because nothing separated
    build stages from the shipped stage; evidence that described a build stage would
    repeat that mistake at the paperwork level.
    """

    api = (ROOT / "deploy/images/api.Dockerfile").read_text(encoding="utf-8")
    web = (ROOT / "deploy/images/web.Dockerfile").read_text(encoding="utf-8")

    assert _final_stage_base(api).startswith("python:")
    assert "@sha256:" in _final_stage_base(api)
    assert _final_stage_base(web).startswith("nginxinc/nginx-unprivileged:")
    assert "@sha256:" in _final_stage_base(web)

    api_stages = _from_lines(api)
    assert any(base.startswith("ghcr.io/astral-sh/uv:") for base in api_stages[:-1])
    assert not _final_stage_base(api).startswith("ghcr.io/astral-sh/uv:")
    assert any(base.startswith("node:") for base in _from_lines(web)[:-1])


def test_image_sboms_follow_the_distribution_naming_convention() -> None:
    assert _sbom_name("api", "0.7.1") == "oak-community-api-image-0.7.1.cdx.json"
    assert _sbom_name("web", "0.7.1") == "oak-community-web-image-0.7.1.cdx.json"


def test_image_provenance_is_marked_unsigned_and_unreproducible() -> None:
    """Provenance is a record, not an assurance; it must say so itself."""

    document = _provenance_document(
        version="0.7.1",
        requested_platform="linux/amd64",
        source_commit="deadbeef",
        source_tree_dirty=False,
        docker_server="29.0.0",
        images={"api": {"tag": "oak-community/api:0.7.1", "image_id": "sha256:x"}},
    )

    assert document["signed"] is False
    assert "unsigned" in document["signing_note"]
    assert document["byte_reproducible"] is False
    assert "RR-006" in document["reproducibility_note"]
    assert document["artifact_version"] == "0.7.1"
    assert document["images"]["api"]["tag"] == "oak-community/api:0.7.1"
