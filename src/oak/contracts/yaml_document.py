# SPDX-License-Identifier: Apache-2.0
"""Parse YAML into the JSON data model governed by canonical schemas."""

from typing import Any

import yaml


class _JSONDataLoader(yaml.SafeLoader):
    """Safe loader that keeps schema date/time values as JSON strings."""


_JSONDataLoader.yaml_implicit_resolvers = {
    key: [resolver for resolver in resolvers if resolver[0] != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_yaml_document(source: str) -> dict[str, Any]:
    """Load a YAML object without YAML-only date/time coercion."""

    document = yaml.load(source, Loader=_JSONDataLoader)
    if not isinstance(document, dict):
        raise ValueError("canonical YAML document must contain an object")
    return document
