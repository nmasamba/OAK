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
        document = _upgrade(document)
        self._registry.validate(CONFIGURATION_SCHEMA, document)
        return document

    def save(self, document: dict[str, Any]) -> None:
        self._registry.validate(CONFIGURATION_SCHEMA, document)
        write_private_file(
            self._directory / CONFIGURATION_FILE_NAME,
            canonical_json_bytes(document) + b"\n",
            code=CONFIGURATION_CODE,
        )


def _upgrade(document: dict[str, Any]) -> dict[str, Any]:
    """Bring a file written by an earlier build to the current shape before validating it.

    Sprint 9 stored one ``selection`` object naming its family, or ``null``; Sprint 10 keeps
    one selection per family and pins nothing by default. Nothing published carries the old
    shape, so this is a courtesy to machines that ran the unreleased build, not a promise;
    a selection for a family that no longer exists is dropped.
    """

    selection = document.get("selection")
    if selection is None:
        document["selection"] = {}
    elif isinstance(selection, dict) and "family" in selection:
        family = selection.get("family")
        upgraded: dict[str, Any] = {}
        if family in {"huggingface", "local"}:
            upgraded[str(family)] = {
                "model_id": selection.get("model_id"),
                "provider_route": selection.get("provider_route"),
                "selected_at": selection.get("selected_at"),
            }
        document["selection"] = upgraded
    return document
