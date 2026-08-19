# SPDX-License-Identifier: Apache-2.0
"""Bounded local policy-pack loading from bundled and activated sources."""

import os
import stat
from pathlib import Path
from typing import Any

import yaml

from oak.contracts import SchemaRegistry, load_yaml_document
from oak.domain import OAKError

MAXIMUM_FILES = 128
MAXIMUM_DOCUMENT_BYTES = 524_288
PACK_SCHEMA = "policy-pack.schema.json"


class LocalPolicyPackStore:
    """Read schema-valid packs from explicit local directories, fail closed."""

    def __init__(self, directories: tuple[Path, ...], registry: SchemaRegistry) -> None:
        self._directories = directories
        self._registry = registry

    def list_packs(self) -> tuple[dict[str, Any], ...]:
        packs: dict[str, dict[str, Any]] = {}
        count = 0
        for directory in self._directories:
            if not directory.is_dir() or directory.is_symlink():
                continue
            for path in sorted([*directory.glob("*.yaml"), *directory.glob("*.yml")]):
                count += 1
                if count > MAXIMUM_FILES:
                    raise OAKError("OAK-POLICY-PACK-COUNT", "too many policy pack files")
                document = self._load_document(path)
                pack_id = str(document["id"])
                if pack_id in packs:
                    raise OAKError("OAK-POLICY-PACK-DUPLICATE", "policy pack ID is duplicated")
                packs[pack_id] = document
        return tuple(packs[pack_id] for pack_id in sorted(packs))

    def load(self, pack_id: str) -> dict[str, Any]:
        for document in self.list_packs():
            if str(document["id"]) == pack_id:
                return document
        raise OAKError("OAK-POLICY-PACK-NOT-FOUND", "policy pack is not available")

    def _load_document(self, path: Path) -> dict[str, Any]:
        try:
            if path.is_symlink():
                raise OAKError("OAK-POLICY-PACK-PATH", "policy pack path must not be a symlink")
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode):
                    raise OAKError("OAK-POLICY-PACK-PATH", "policy pack must be a regular file")
                content = os.read(descriptor, MAXIMUM_DOCUMENT_BYTES + 1)
            finally:
                os.close(descriptor)
            if not content or len(content) > MAXIMUM_DOCUMENT_BYTES:
                raise OAKError("OAK-POLICY-PACK-INVALID", "policy pack size is out of bounds")
            text = content.decode("utf-8")
            for token in yaml.scan(text):
                if isinstance(token, (yaml.AliasToken, yaml.AnchorToken)):
                    raise OAKError(
                        "OAK-POLICY-PACK-INVALID", "policy pack must not use YAML aliases"
                    )
            document = load_yaml_document(text)
            self._registry.validate(PACK_SCHEMA, document)
            return document
        except OAKError:
            raise
        except Exception as error:
            raise OAKError(
                "OAK-POLICY-PACK-INVALID", "policy pack failed bounded validation"
            ) from error
