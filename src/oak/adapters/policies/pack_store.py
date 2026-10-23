# SPDX-License-Identifier: Apache-2.0
"""Bounded local policy-pack loading from bundled and activated sources."""

import json
import os
import stat
from pathlib import Path
from typing import Any

import yaml

from oak.contracts import SchemaRegistry, load_yaml_document
from oak.domain import OAKError, canonical_json_bytes, content_digest

MAXIMUM_FILES = 128
MAXIMUM_DOCUMENT_BYTES = 524_288
PACK_SCHEMA = "policy-pack.schema.json"


class LocalPolicyPackStore:
    """Read schema-valid packs from explicit local directories, fail closed."""

    def __init__(
        self,
        directories: tuple[Path, ...],
        registry: SchemaRegistry,
        *,
        nested_directories: tuple[Path, ...] = (),
    ) -> None:
        self._directories = directories
        # Each nested root holds one subdirectory per activated extension; the
        # pack is read from the verified extension directory itself so there is
        # no second copy that can drift away from what was signed and checked.
        self._nested_directories = nested_directories
        self._registry = registry

    def list_packs(self) -> tuple[dict[str, Any], ...]:
        packs: dict[str, dict[str, Any]] = {}
        candidates: list[Path] = []
        for directory in self._directories:
            if not directory.is_dir() or directory.is_symlink():
                continue
            candidates.extend(sorted([*directory.glob("*.yaml"), *directory.glob("*.yml")]))
        for root in self._nested_directories:
            if not root.is_dir() or root.is_symlink():
                continue
            candidates.extend(
                path for path in sorted(root.glob("*/pack.yaml")) if self._activated(path)
            )
        for count, path in enumerate(candidates, start=1):
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

    def _activated(self, path: Path) -> bool:
        """Whether this extension's pack is the one verified and activated, unchanged.

        A `pack.yaml` copied under the active root without install, verify and activate is
        not a pack OAK uses, and one edited after activation is refused (F4-13): the pack's
        bytes must still match the digest its manifest lists, and the manifest must still
        be the one the activation record bound.
        """

        directory = path.parent
        activation_path = directory / "activation.json"
        if not activation_path.exists() and not activation_path.is_symlink():
            return False
        try:
            activation = json.loads(_bounded_bytes(activation_path).decode("utf-8"))
            manifest_text = _bounded_bytes(directory / "extension.yaml").decode("utf-8")
            if any(
                isinstance(token, (yaml.AliasToken, yaml.AnchorToken))
                for token in yaml.scan(manifest_text)
            ):
                raise ValueError("aliases")
            manifest = load_yaml_document(manifest_text)
            pack_bytes = _bounded_bytes(path)
        except (OSError, ValueError, yaml.YAMLError, OAKError) as error:
            raise OAKError(
                "OAK-POLICY-PACK-UNVERIFIED", "an activated policy pack's records are unreadable"
            ) from error
        payload = manifest.get("payload") if isinstance(manifest, dict) else None
        files = payload.get("files") if isinstance(payload, dict) else None
        listed = {
            str(item.get("path")): str(item.get("digest"))
            for item in (files if isinstance(files, list) else [])
            if isinstance(item, dict)
        }
        if (
            not isinstance(activation, dict)
            or activation.get("manifest_digest") != content_digest(canonical_json_bytes(manifest))
            or listed.get("pack.yaml") != content_digest(pack_bytes)
        ):
            raise OAKError(
                "OAK-POLICY-PACK-UNVERIFIED",
                "an activated policy pack no longer matches what was verified at activation",
            )
        return True

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


def _bounded_bytes(path: Path) -> bytes:
    if path.is_symlink():
        raise OAKError("OAK-POLICY-PACK-PATH", "policy pack path must not be a symlink")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OAKError("OAK-POLICY-PACK-PATH", "policy pack must be a regular file")
        content = os.read(descriptor, MAXIMUM_DOCUMENT_BYTES + 1)
    finally:
        os.close(descriptor)
    if not content or len(content) > MAXIMUM_DOCUMENT_BYTES:
        raise OAKError("OAK-POLICY-PACK-INVALID", "policy pack size is out of bounds")
    return content
