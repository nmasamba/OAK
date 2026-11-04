# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-040/041: the consent text a native installation is approved against.

Its digest is part of every native plan and every `native_consent` approval, so an edit to
the text must come with a new version: a plan compiled against one text is never approved
against another that shares its id and version. The pin below moves with the version.
"""

from __future__ import annotations

import pytest

from oak.adapters.catalogue import LocalConsentText
from oak.bootstrap import canonical_catalogue_directory, load_native_consent
from oak.contracts import SchemaRegistry
from oak.domain import OAKError
from oak.domain.runner_adapters import (
    NATIVE_CONSENT_ID,
    NATIVE_RELAXED_CONTROLS,
    native_consent_problem,
    native_consent_reference,
)
from tests.runner_support import ROOT

# The installed text, by version. Once a version is released, an edit bumps the version and
# adds a pin; `0.1.0` is the unreleased draft awaiting the owner's sign-off, so its pin moves
# with each edit until then.
PINNED = {
    "0.1.0": "sha256:d2b8b60dd3004eb9d98204a6a0293879a4be302de4bcaa1f3b92d296519b3b2c",
}


def test_the_installed_text_is_pinned_for_its_version() -> None:
    reference = native_consent_reference(load_native_consent())

    assert reference["id"] == NATIVE_CONSENT_ID
    assert PINNED.get(reference["version"]) == reference["digest"], (
        "the consent text changed without a new version, or its new version has no pin"
    )


def test_the_installed_text_names_exactly_what_the_adapter_relaxes() -> None:
    document = load_native_consent()

    assert native_consent_problem(document) is None
    assert [entry["id"] for entry in document["relaxed_controls"]] == list(NATIVE_RELAXED_CONTROLS)


def test_a_missing_or_invalid_text_is_refused(tmp_path) -> None:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    (tmp_path / "components").mkdir()
    with pytest.raises(OAKError) as missing:
        LocalConsentText(tmp_path, registry)()
    assert missing.value.code == "OAK-NATIVE-CONSENT"

    (tmp_path / "consent").mkdir()
    (tmp_path / "consent" / "native-installation.yaml").write_text(
        "schema_version: 0.1.0\nid: consent.native-installation\n", encoding="utf-8"
    )
    with pytest.raises(OAKError) as invalid:
        LocalConsentText(tmp_path, registry)()
    assert invalid.value.code == "OAK-NATIVE-CONSENT"


def test_the_bundled_text_is_found_where_the_catalogue_is() -> None:
    assert (canonical_catalogue_directory() / "consent" / "native-installation.yaml").is_file()
