# SPDX-License-Identifier: Apache-2.0
"""Parse YAML into the JSON data model governed by canonical schemas."""

import json
import math
from typing import Any

import yaml
from yaml.nodes import MappingNode


class _JSONDataLoader(yaml.SafeLoader):
    """Safe loader that keeps schema date/time values as JSON strings."""


_JSONDataLoader.yaml_implicit_resolvers = {
    key: [resolver for resolver in resolvers if resolver[0] != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _construct_unique_mapping(
    loader: _JSONDataLoader, node: MappingNode, deep: bool = False
) -> dict[object, object]:
    loader.flatten_mapping(node)
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise ValueError("YAML mapping keys must be scalar JSON values") from error
        if duplicate:
            raise ValueError("YAML mapping keys must be unique")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_JSONDataLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_yaml_document(source: str) -> dict[str, Any]:
    """Load a YAML object without YAML-only date/time coercion."""

    document = yaml.load(source, Loader=_JSONDataLoader)
    if not isinstance(document, dict):
        raise ValueError("canonical YAML document must contain an object")
    _validate_json_value(document)
    return document


def load_json_document(source: str) -> dict[str, Any]:
    """Load a strict JSON object with unique keys and finite numeric constants."""

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for key, value in pairs:
            if key in document:
                raise ValueError("JSON mapping keys must be unique")
            document[key] = value
        return document

    def reject_constant(value: str) -> None:
        raise ValueError(f"JSON numeric constant {value} is not finite")

    document = json.loads(
        source,
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )
    if not isinstance(document, dict):
        raise ValueError("canonical JSON document must contain an object")
    _validate_json_value(document)
    return document


def _validate_json_value(value: Any, active: set[int] | None = None) -> None:
    active = set() if active is None else active
    if isinstance(value, dict):
        identity = id(value)
        if identity in active:
            raise ValueError("canonical document contains a cycle")
        active.add(identity)
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("canonical document keys must be strings")
            _validate_json_value(child, active)
        active.remove(identity)
        return
    if isinstance(value, list):
        identity = id(value)
        if identity in active:
            raise ValueError("canonical document contains a cycle")
        active.add(identity)
        for child in value:
            _validate_json_value(child, active)
        active.remove(identity)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("canonical document numbers must be finite")
    if value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError("canonical document contains a non-JSON value")


def load_alias_free_yaml_document(source: str) -> dict[str, Any]:
    """Load YAML that must not use anchors or aliases.

    Untrusted YAML gets this reader: anchor expansion lets a small document
    allocate an enormous one, and an alias-bearing document that parses here
    would still be refused by every bounded loader downstream.
    """

    for token in yaml.scan(source):
        if isinstance(token, (yaml.AliasToken, yaml.AnchorToken)):
            raise ValueError("document must not use YAML anchors or aliases")
    return load_yaml_document(source)
