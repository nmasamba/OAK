# SPDX-License-Identifier: Apache-2.0
"""Bounded loader for bundled Community catalogue documents."""

import os
import stat
from pathlib import Path
from typing import Any

import yaml

from oak.contracts import ContractValidationError, SchemaRegistry, load_yaml_document
from oak.domain import OAKError
from oak.ports.catalogue import CatalogueDocuments

MAXIMUM_FILES = 128
MAXIMUM_DOCUMENT_BYTES = 524_288


class LocalCatalogue:
    def __init__(self, root: Path, registry: SchemaRegistry) -> None:
        self._root = root
        self._registry = registry

    def load(self) -> CatalogueDocuments:
        manifests = self._load_directory("components", "component-manifest.schema.json")
        patterns = self._load_directory("patterns", "architecture-pattern.schema.json")
        if not manifests or not patterns:
            raise OAKError("OAK-CATALOGUE-EMPTY", "catalogue requires manifests and patterns")
        return CatalogueDocuments(manifests=manifests, patterns=patterns)

    def _load_directory(self, name: str, schema_name: str) -> tuple[dict[str, Any], ...]:
        directory = self._root / name
        if directory.is_symlink() or not directory.is_dir():
            raise OAKError("OAK-CATALOGUE-PATH", "catalogue directory is unsafe or missing")
        paths = sorted((*directory.glob("*.yaml"), *directory.glob("*.yml")))
        if len(paths) > MAXIMUM_FILES:
            raise OAKError("OAK-CATALOGUE-COUNT", "catalogue contains too many documents")
        documents: list[dict[str, Any]] = []
        for path in paths:
            documents.append(self._load_document(path, schema_name))
        identities = [
            (
                str(item["id"]),
                str(
                    item["release"]["version"]
                    if schema_name == "component-manifest.schema.json"
                    else item["version"]
                ),
            )
            for item in documents
        ]
        if len(identities) != len(set(identities)):
            raise OAKError("OAK-CATALOGUE-DUPLICATE", "catalogue identities must be unique")
        return tuple(documents)

    def _load_document(self, path: Path, schema_name: str) -> dict[str, Any]:
        if path.is_symlink() or not path.is_file():
            raise OAKError("OAK-CATALOGUE-PATH", "catalogue documents must be regular files")
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, "rb") as stream:
                details = os.fstat(stream.fileno())
                if not stat.S_ISREG(details.st_mode):
                    raise ValueError("catalogue document is not a regular file")
                source_bytes = stream.read(MAXIMUM_DOCUMENT_BYTES + 1)
            if not source_bytes or len(source_bytes) > MAXIMUM_DOCUMENT_BYTES:
                raise ValueError("catalogue document size is outside the accepted range")
            source = source_bytes.decode("utf-8")
            tokens = tuple(yaml.scan(source))
            if any(
                isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken))
                for token in tokens
            ):
                raise ValueError("YAML aliases are not accepted")
            document = load_yaml_document(source)
            self._registry.validate(schema_name, document)
            return document
        except (
            OSError,
            UnicodeError,
            ValueError,
            yaml.YAMLError,
            ContractValidationError,
        ) as error:
            raise OAKError(
                "OAK-CATALOGUE-INVALID", "catalogue document failed bounded validation"
            ) from error
