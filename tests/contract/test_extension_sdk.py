# SPDX-License-Identifier: Apache-2.0
"""Versioned extension SDK contracts stay pinned and deterministic."""

from oak.domain.extension_sdk import (
    INTERFACE_BY_CLASS,
    RENDERER_IDENTITY_BY_ID,
    SDK_VERSION,
    capability_document,
)
from oak.domain.runner_adapters import ADAPTER_IDENTITY_BY_ID


def test_every_extension_class_declares_a_versioned_interface() -> None:
    assert set(INTERFACE_BY_CLASS) == {
        "policy-pack",
        "deployment-adapter",
        "component-manifest",
        "architecture-pattern",
        "runner-adapter",
    }
    for interface in INTERFACE_BY_CLASS.values():
        assert interface.interface_version == "1.0.0"
        assert interface.capabilities
        assert interface.description


def test_renderer_identities_have_exact_shape_and_derived_digests() -> None:
    assert set(RENDERER_IDENTITY_BY_ID) == {
        "renderer.local-manifests",
        "renderer.helm-kubernetes",
    }
    for identity in RENDERER_IDENTITY_BY_ID.values():
        assert set(identity) == {"id", "version", "digest"}
        assert identity["digest"].startswith("sha256:")


def test_capability_document_is_deterministic_and_complete() -> None:
    first = capability_document()
    second = capability_document()
    assert first == second
    assert first["sdk_version"] == SDK_VERSION
    assert [entry["extension_class"] for entry in first["interfaces"]] == sorted(INTERFACE_BY_CLASS)
    assert {entry["id"] for entry in first["runner_adapters"]} == set(ADAPTER_IDENTITY_BY_ID)
    engine_ids = {entry["id"] for entry in first["policy_engines"]}
    assert engine_ids == {"policy-engine.builtin", "policy-engine.opa"}
    required = {entry["id"]: entry["required"] for entry in first["policy_engines"]}
    assert required["policy-engine.builtin"] is True
    assert required["policy-engine.opa"] is False
