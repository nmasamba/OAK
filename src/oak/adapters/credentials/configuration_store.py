# SPDX-License-Identifier: Apache-2.0
"""Owner-only JSON file holding the non-secret model selection and discovery snapshot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oak.adapters.credentials._files import read_private_file, write_private_file
from oak.contracts import SchemaRegistry
from oak.domain import OAKError, canonical_json_bytes

CONFIGURATION_FILE_NAME = "model-configuration.json"
CONFIGURATION_SCHEMA = "model-configuration.schema.json"
CONFIGURATION_CODE = "OAK-MODEL-CONFIGURATION-FILE"
_MAXIMUM_CONFIGURATION_BYTES = 1_048_576


class ModelConfigurationFileStore:
    def __init__(self, directory: Path, registry: SchemaRegistry) -> None:
        self._directory = directory
        self._registry = registry

    def location(self) -> str:
        return str(self._directory / CONFIGURATION_FILE_NAME)

    def load(self) -> dict[str, Any] | None:
        content = read_private_file(
            self._directory / CONFIGURATION_FILE_NAME,
            code=CONFIGURATION_CODE,
            maximum_bytes=_MAXIMUM_CONFIGURATION_BYTES,
        )
        if content is None:
            return None
        try:
            document = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise OAKError(
                CONFIGURATION_CODE, "the model configuration file is unreadable"
            ) from error
        if not isinstance(document, dict):
            raise OAKError(CONFIGURATION_CODE, "the model configuration file is malformed")
        self._registry.validate(CONFIGURATION_SCHEMA, document)
        return document

    def save(self, document: dict[str, Any]) -> None:
        self._registry.validate(CONFIGURATION_SCHEMA, document)
        write_private_file(
            self._directory / CONFIGURATION_FILE_NAME,
            canonical_json_bytes(document) + b"\n",
            code=CONFIGURATION_CODE,
        )
