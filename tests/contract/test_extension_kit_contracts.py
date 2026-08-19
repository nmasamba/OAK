# SPDX-License-Identifier: Apache-2.0
"""The reusable extension kit applied to every shipped engine, pack, and adapter."""

from pathlib import Path
from typing import Any

import jsonschema

from oak.adapters.policies import BuiltinPolicyEngine
from oak.contracts import SchemaRegistry, load_yaml_document
from oak.domain.extension_sdk import RENDERER_IDENTITY_BY_ID
from oak.domain.runner_adapters import (
    ADAPTER_IDENTITY_BY_ID,
    CONTAINER_PARAMETER_SCHEMA,
)
from oak.runner.adapters import CommandResult, ContainerFixtureAdapter
from tests.extension_kit import (
    check_argv_injection_resistance,
    check_engine_determinism,
    check_engine_fails_closed_on_unknown,
    check_pack_embedded_tests,
    check_pack_governance_fields,
    check_pack_lifecycle_dating,
    check_typed_rollback,
)

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = ROOT / "templates" / "extensions"
PAYLOAD_SCHEMA_BY_CLASS = {
    "policy-pack": "policy-pack.schema.json",
    "component-manifest": "component-manifest.schema.json",
    "architecture-pattern": "architecture-pattern.schema.json",
}


def _registry() -> SchemaRegistry:
    return SchemaRegistry.from_directory(ROOT / "schemas")


def _load(path: Path) -> dict[str, Any]:
    return load_yaml_document(path.read_text(encoding="utf-8"))


def test_builtin_engine_passes_the_kit_checks() -> None:
    pack = _load(ROOT / "policy-packs" / "community-baseline.yaml")
    engine = BuiltinPolicyEngine()
    subjects = [dict(test["subject"]) for test in pack["tests"]]
    check_engine_determinism(engine, pack, subjects)
    check_engine_fails_closed_on_unknown(engine)
    check_pack_governance_fields(pack)
    check_pack_lifecycle_dating(pack)
    check_pack_embedded_tests(pack, engine)


def test_every_template_is_schema_valid_and_internally_consistent() -> None:
    registry = _registry()
    directories = sorted(path for path in TEMPLATE_ROOT.iterdir() if path.is_dir())
    assert {path.name for path in directories} == {
        "policy-pack",
        "deployment-adapter",
        "component-manifest",
        "architecture-pattern",
        "runner-adapter",
    }
    for directory in directories:
        manifest = _load(directory / "extension.yaml")
        registry.validate("extension-manifest.schema.json", manifest)
        assert str(manifest["extension_class"]) == directory.name
        assert (directory / "README.md").is_file()
        declared_paths = sorted(str(item["path"]) for item in manifest["payload"]["files"])
        actual_paths = sorted(
            path.name
            for path in directory.iterdir()
            if path.suffix in {".yaml", ".yml"} and path.name != "extension.yaml"
        )
        assert declared_paths == actual_paths, directory.name
        payload_schema = PAYLOAD_SCHEMA_BY_CLASS.get(directory.name)
        if payload_schema is not None:
            for name in actual_paths:
                registry.validate(payload_schema, _load(directory / name))


def test_policy_pack_template_embedded_tests_pass() -> None:
    pack = _load(TEMPLATE_ROOT / "policy-pack" / "pack.yaml")
    check_pack_governance_fields(pack)
    check_pack_embedded_tests(pack, BuiltinPolicyEngine())


def test_adapter_binding_templates_reference_registered_identities() -> None:
    deployment = _load(TEMPLATE_ROOT / "deployment-adapter" / "adapter.yaml")
    assert deployment["renderer_id"] in RENDERER_IDENTITY_BY_ID
    runner = _load(TEMPLATE_ROOT / "runner-adapter" / "adapter.yaml")
    assert runner["runner_adapter_id"] in ADAPTER_IDENTITY_BY_ID


def test_container_adapter_passes_argv_and_rollback_kit_checks() -> None:
    calls: list[tuple[str, ...]] = []

    def recording_executor(argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
        calls.append(argv)
        return CommandResult(returncode=0, stdout="", stderr="")

    adapter = ContainerFixtureAdapter(recording_executor)

    def invoke(parameters: dict[str, Any]) -> Any:
        jsonschema.validate(parameters, CONTAINER_PARAMETER_SCHEMA)
        return adapter.apply(parameters, 60)

    check_argv_injection_resistance(invoke)
    assert calls == [], "an injection fixture reached the executor"

    def apply_then_rollback() -> tuple[list[tuple[str, ...]], list[tuple[str, ...]]]:
        parameters = {
            "container_name": "oak-fixture-kit",
            "image_reference": "registry.example.invalid/fixture",
            "image_digest": "sha256:" + "a" * 64,
            "isolation": "network-none-never-started",
        }
        calls.clear()
        adapter.apply(parameters, 60)
        apply_calls = list(calls)
        calls.clear()
        adapter.rollback(parameters, 60)
        return apply_calls, list(calls)

    check_typed_rollback(apply_then_rollback)
