# SPDX-License-Identifier: Apache-2.0
"""OAK-S14-003: hostile metadata is kept only by allowlist, and the gates are honest.

ADR-0018, OAK-FR-CAT-004, OAK-FR-CAT-005 and OAK-NFR-SEC-003. The family-token rule and its
cases are the ones the ADR records; the normalisation probes are the ones Sprint 13's review
used to beat a denylist (zero-width characters, lookalikes, direction overrides), plus the
bounds and the forbidden words; every gate reason has its case; and a researched manifest
is schema-valid with every honest value and never `eligible` or `approved_for_context`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oak.adapters.catalogue import ResearchVocabularyLoader
from oak.contracts import SchemaRegistry
from oak.domain.catalogue_rules import catalogue_timestamp, eligibility_reasons
from oak.domain.research_rules import (
    GateFacts,
    as_timestamp,
    claim_names_family,
    evidence_reference,
    family_token,
    licence_entry_for,
    manifest_slug,
    normalise_identifier,
    normalise_notes,
    normalise_text,
    research_gates,
    research_manifest,
    weight_floor_gib,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-10-20T12:00:00Z"
TRUSTED = frozenset({"HuggingFaceTB", "Qwen"})


def _licences() -> dict[str, object]:
    return ResearchVocabularyLoader(ROOT / "catalogue").load().licences


# ----- the family-token rule (ADR-0018) ---------------------------------------------------


@pytest.mark.parametrize(
    ("model_id", "token"),
    [
        ("HuggingFaceTB/Fixturelm-4B", "Fixturelm"),
        ("Qwen/Qwen3-8B", "Qwen3"),
        ("Qwen/Qwen3.5-397B", "Qwen3.5"),
        ("org/Model-0.5B", "Model"),
        ("org/Model-14b", "Model"),
        ("org/Model-700M", "Model"),
        ("org/Model-Instruct", "Model-Instruct"),
        ("org/Model-4B-Instruct", "Model-4B-Instruct"),
        ("org/Plain", "Plain"),
    ],
)
def test_the_family_token_strips_one_trailing_size_segment_only(model_id: str, token: str) -> None:
    assert family_token(model_id) == token


@pytest.mark.parametrize(
    ("notes", "token", "expected"),
    [
        ("Adds Fixturelm support", "Fixturelm", True),
        ("adds fixturelm support", "Fixturelm", True),
        ("Supports the Fixturelm family", "Fixturelm", True),
        ("Supports Fixturelm-4B and Fixturelm-9B", "Fixturelm", False),
        ("Qwen3 is supported", "Qwen3", True),
        ("Qwen3.5 is supported", "Qwen3", False),
        ("Qwen3-Coder is supported", "Qwen3", False),
        ("Qwen3, Qwen3. Qwen3; and (Qwen3)", "Qwen3", True),
        ("MyQwen3 is supported", "Qwen3", False),
        ("Qwen3x is supported", "Qwen3", False),
        ("nothing here", "Qwen3", False),
        ("Qwen3", "", False),
    ],
)
def test_a_claim_names_the_pair_only_as_a_whole_token(
    notes: str, token: str, expected: bool
) -> None:
    assert claim_names_family(notes, token) is expected


# ----- normalisation by allowlist ---------------------------------------------------------


def test_text_is_nfkc_normalised_bounded_and_refused_on_control_or_odd_characters() -> None:
    assert normalise_text("  Apache-2.0 ") == "Apache-2.0"
    assert normalise_text("ｆｕｌｌｗｉｄｔｈ") == "fullwidth"  # noqa: RUF001
    assert normalise_text("a​b") is None  # zero-width space, category Cf
    assert normalise_text("a‮b") is None  # right-to-left override
    assert normalise_text("a\x00b") is None
    assert normalise_text("has <markup>") is None
    assert normalise_text('quote "here"') is None
    assert normalise_text("x" * 81) is None
    assert normalise_text("x" * 80) == "x" * 80
    assert normalise_text("") is None
    assert normalise_text(42) is None


def test_an_identifier_is_refused_when_normalisation_changes_it() -> None:
    assert normalise_identifier("HuggingFaceTB/Fixturelm-4B") == "HuggingFaceTB/Fixturelm-4B"
    assert normalise_identifier("ＨuggingFaceTB/Fixturelm-4B") is None  # noqa: RUF001
    assert normalise_identifier("HuggingFaceTB/Fixture​lm-4B") is None
    assert normalise_identifier("HuggingFaceTB/../etc") is None
    assert normalise_identifier("https://evil.invalid/x") is None
    assert normalise_identifier("single-segment") is None
    assert normalise_identifier("a/b/c") is None
    assert normalise_identifier("x" * 200) is None


def test_notes_keep_line_breaks_as_spaces_and_refuse_other_control_characters() -> None:
    assert normalise_notes("line one\nline two\ttabbed\r\n") == "line one line two tabbed  "
    assert normalise_notes("Fixture​lm") is None
    assert normalise_notes("‮Fixturelm") is None
    assert normalise_notes("x" * 20_001) is None
    assert normalise_notes(None) is None


# ----- the weight floor -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("parameters", "gib", "reason"),
    [
        ({"BF16": 4_000_000_000}, 7.451, "research-weight-floor-1.0.0"),
        ({"F8_E4M3": 1_073_741_824}, 1.0, "research-weight-floor-1.0.0"),
        ({"F32": 268_435_456, "I8": 1_073_741_824}, 2.0, "research-weight-floor-1.0.0"),
        ({"FP4": 120_000_000_000}, None, "The dtype FP4 has no known byte width."),
        ({}, None, "The source publishes no safetensors parameter counts."),
        (None, None, "The source publishes no safetensors parameter counts."),
        ({"BF16": -1}, None, "A parameter count is not a whole number."),
        ({"BF16": True}, None, "A parameter count is not a whole number."),
    ],
)
def test_the_weight_floor_follows_the_dtype_table_and_is_unknown_otherwise(
    parameters: object, gib: float | None, reason: str
) -> None:
    assert weight_floor_gib(parameters) == (gib, reason)


# ----- the research gates -------------------------------------------------------------------


def _facts(**overrides: object) -> GateFacts:
    base: dict[str, object] = {
        "kind": "model",
        "source_id": "HuggingFaceTB/Fixturelm-4B",
        "namespace": "HuggingFaceTB",
        "licence_id": "apache-2.0",
        "gated": False,
        "archived": None,
        "disabled": None,
        "dated_at": "2026-10-19T09:00:00Z",
        "has_digest_or_commit": True,
        "capability_known": True,
        "displayed_strings": ("HuggingFaceTB/Fixturelm-4B", "apache-2.0"),
    }
    base.update(overrides)
    return GateFacts(**base)  # type: ignore[arg-type]


def _gate(facts: GateFacts, *, review: str | None = None, reviewed: frozenset[str] = frozenset()):  # type: ignore[no-untyped-def]
    return research_gates(
        facts,
        licences=_licences(),
        trusted_namespaces=TRUSTED,
        reviewed_harnesses=reviewed,
        review=review,
        occurred_at=NOW,
        freshness_window_days=180,
    )


def test_a_trusted_model_that_passes_every_gate_is_passed() -> None:
    assert _gate(_facts()) == ("trusted", "passed", ())


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"licence_id": "other"}, "OAK-CAT-RESEARCH-LICENCE-UNLISTED"),
        ({"licence_id": "NOASSERTION"}, "OAK-CAT-RESEARCH-LICENCE-UNLISTED"),
        ({"licence_id": None}, "OAK-CAT-RESEARCH-LICENCE-UNLISTED"),
        ({"gated": True}, "OAK-CAT-RESEARCH-GATED"),
        ({"archived": True}, "OAK-CAT-RESEARCH-ARCHIVED"),
        ({"disabled": True}, "OAK-CAT-RESEARCH-DISABLED"),
        ({"dated_at": None}, "OAK-CAT-RESEARCH-UNDATED"),
        ({"dated_at": "2026-04-01T00:00:00Z"}, "OAK-CAT-RESEARCH-STALE"),
        ({"dated_at": "2026-10-21T00:00:00Z"}, "OAK-CAT-RESEARCH-FUTURE"),
        ({"has_digest_or_commit": False}, "OAK-CAT-RESEARCH-UNDIGESTED"),
        ({"capability_known": False}, "OAK-CAT-RESEARCH-CAPABILITY"),
        ({"displayed_strings": ("enterprise-grade",)}, "OAK-CAT-RESEARCH-FORBIDDEN-WORD"),
        ({"displayed_strings": ("Enterprise",)}, "OAK-CAT-RESEARCH-FORBIDDEN-WORD"),
        ({"malformed": True}, "OAK-CAT-RESEARCH-MALFORMED"),
        ({"unreachable": True}, "OAK-CAT-RESEARCH-UNREACHABLE"),
    ],
)
def test_each_gate_failure_has_its_stable_reason(overrides: dict[str, object], reason: str) -> None:
    _tier, verdict, reasons = _gate(_facts(**overrides))
    assert verdict == "failed"
    assert reason in reasons


def test_a_blocked_licence_class_on_the_list_fails_with_its_own_reason() -> None:
    licences = {
        "licences": [
            {
                "spdx_id": "Restricted-1.0",
                "classification": "restricted",
                "github_keyword": "restricted-1.0",
                "hub_tag": "restricted-1.0",
                "source": "https://example.invalid/r",
                "checked_at": "2026-10-21",
            }
        ]
    }
    _tier, verdict, reasons = research_gates(
        _facts(licence_id="Restricted-1.0"),
        licences=licences,
        trusted_namespaces=TRUSTED,
        reviewed_harnesses=frozenset(),
        review=None,
        occurred_at=NOW,
        freshness_window_days=180,
    )
    assert verdict == "failed" and reasons == ("OAK-CAT-RESEARCH-LICENCE-BLOCKED",)


def test_the_unvetted_tier_needs_a_review_and_a_recorded_decision_settles_it() -> None:
    unvetted = _facts(namespace="someone-else", source_id="someone-else/Freshlm-2B")
    assert _gate(unvetted) == ("unvetted", "needs_review", ("OAK-CAT-RESEARCH-UNVETTED",))
    assert _gate(unvetted, review="accept") == ("unvetted", "passed", ())
    assert _gate(unvetted, review="reject") == (
        "unvetted",
        "failed",
        ("OAK-CAT-RESEARCH-REJECTED",),
    )
    # A real failure stays a failure however the review went.
    assert _gate(_facts(namespace="someone-else", gated=True), review="accept")[1] == "failed"


def test_a_harness_is_trusted_only_through_the_reviewed_list() -> None:
    harness = _facts(
        kind="serving_runtime",
        source_id="fixture-forge/fixturelm-serve",
        namespace="fixture-forge",
        licence_id="Apache-2.0",
        gated=None,
        archived=False,
        disabled=False,
        dated_at="2026-10-13T08:30:00Z",
    )
    assert _gate(harness)[:2] == ("unvetted", "needs_review")
    assert _gate(harness, reviewed=frozenset({"fixture-forge/fixturelm-serve"}))[:2] == (
        "trusted",
        "passed",
    )
    assert (
        _gate(harness, reviewed=frozenset({"FIXTURE-FORGE/FIXTURELM-SERVE".casefold()}))[1]
        == "passed"
    )


def test_the_licence_list_is_matched_by_spdx_id_keyword_or_hub_tag_case_insensitively() -> None:
    licences = _licences()
    assert licence_entry_for("Apache-2.0", licences)["spdx_id"] == "Apache-2.0"
    assert licence_entry_for("apache-2.0", licences)["spdx_id"] == "Apache-2.0"
    assert licence_entry_for("MIT", licences)["classification"] == "osi_approved"
    assert licence_entry_for("GPL-3.0", licences) is None
    assert licence_entry_for("", licences) is None
    assert licence_entry_for(None, licences) is None


# ----- the honest manifest -----------------------------------------------------------------


def _manifest() -> dict[str, object]:
    licence = licence_entry_for("apache-2.0", _licences())
    evidence = [
        evidence_reference(
            "evidence.research.huggingfacetb.fixturelm-4b.published_by_source",
            "published_by_source",
            uri="https://huggingface.co/HuggingFaceTB/Fixturelm-4B",
            version="0123456789abcdef0123456789abcdef01234567",
            checked_at=NOW,
            content_digest="sha256:" + "2" * 64,
            source_word="Hugging Face Hub",
        )
    ]
    return research_manifest(
        manifest_id="component.research.hub.huggingfacetb.fixturelm-4b",
        name="HuggingFaceTB/Fixturelm-4B",
        category="model",
        kind="model",
        owner="HuggingFaceTB",
        project_url="https://huggingface.co/HuggingFaceTB/Fixturelm-4B",
        repository_url="https://huggingface.co/HuggingFaceTB/Fixturelm-4B",
        release_version="0123456789ab",
        released_at="2026-10-19T09:00:00Z",
        artifact_reference="huggingface.co/HuggingFaceTB/Fixturelm-4B@0123456789abcdef0123456789abcdef01234567",
        artifact_digest="sha256:" + "2" * 64,
        digest_covers="the Hub's listing of this model, not its weights",
        commit_id="0123456789abcdef0123456789abcdef01234567",
        licence=licence,
        licence_domain="model",
        capabilities=["citation_drafting"],
        evidence=evidence,
        measurements=[],
        occurred_at=NOW,
        freshness_window_days=180,
        research={"source": "huggingface_hub", "source_id": "HuggingFaceTB/Fixturelm-4B"},
    )


def test_a_researched_manifest_is_schema_valid_quarantined_and_honest() -> None:
    manifest = _manifest()
    SchemaRegistry.from_directory(ROOT / "schemas").validate(
        "component-manifest.schema.json", manifest
    )

    assert manifest["status"] == "quarantined"
    assert manifest["availability_class"] == "unknown"
    assert manifest["licensing"]["transitive_review"] == "pending"
    assert manifest["licensing"]["model"]["review_status"] == "pending"
    assert manifest["licensing"]["model"]["classification"] == "osi_approved"
    assert manifest["licensing"]["software"]["classification"] == "not_applicable"
    assert manifest["artifact"]["signature_status"] == "unknown"
    assert manifest["artifact"]["digest"].startswith("sha256:")
    assert (
        manifest["extensions"]["oak.community/research"]["commit_id"]
        == "0123456789abcdef0123456789abcdef01234567"
    )
    assert manifest["targets"]["minimum_resources"] == {}
    assert manifest["targets"]["operating_systems"] == []
    assert manifest["deployment"]["modes"] == []
    assert manifest["maturity"]["lifecycle_stage"] == "unknown"
    assert manifest["release"]["support_until"] is None
    assert manifest["release"]["released_at"] == "2026-10-19"
    assert "oak.community/objectives" not in manifest["extensions"]
    assert all(
        e["source_type"] in {"vendor_claim", "community_claim", "inference"}
        for e in manifest["evidence"]
    )
    # The curated rules still see what they would see, and those reasons are kept as review items.
    assert set(eligibility_reasons(manifest, catalogue_timestamp(NOW))) == {
        "OAK-CAT-STATUS-NOT-ELIGIBLE",
        "OAK-CAT-AVAILABILITY-BLOCKED",
        "OAK-CAT-TRANSITIVE-LICENCE-UNRESOLVED",
        "OAK-CAT-MODEL-LICENCE-UNREVIEWED",
    }


def test_every_free_text_gap_says_the_source_did_not_publish_it() -> None:
    manifest = _manifest()
    texts = [
        manifest["maturity"]["governance"],
        manifest["deployment"]["offline_behavior"],
        manifest["security"]["identity"],
        manifest["operations"]["backup"],
        manifest["data_handling"]["retention"],
    ]
    assert all(text == "Not published by the source." for text in texts)


def test_slugs_and_timestamps_are_bounded_and_canonical() -> None:
    assert manifest_slug("HuggingFaceTB/Fixturelm-4B") == "huggingfacetb.fixturelm-4b"
    assert manifest_slug("Org/Name With Space") == "org.name-with-space"
    assert as_timestamp("2026-10-19T09:00:00.000Z") == "2026-10-19T09:00:00Z"
    assert as_timestamp("2026-10-19T11:00:00+02:00") == "2026-10-19T09:00:00Z"
    assert as_timestamp("2026-10-19") == "2026-10-19T00:00:00Z"
    assert as_timestamp("2026-10-19T09:00:00") is None
    assert as_timestamp("yesterday") is None
    assert as_timestamp(1234) is None
