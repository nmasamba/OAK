# SPDX-License-Identifier: Apache-2.0
"""Bounded loader for non-production local target profiles."""

import os
import stat
from pathlib import Path
from typing import Any

import yaml

from oak.contracts import ContractValidationError, SchemaRegistry, load_yaml_document
from oak.domain import OAKError

MAXIMUM_TARGET_BYTES = 65_536


class LocalTargetProfile:
    def __init__(self, registry: SchemaRegistry) -> None:
        self._registry = registry

    def load(self, path: Path) -> dict[str, Any]:
        absolute = path.absolute()
        if absolute.is_symlink() or not absolute.is_file():
            raise OAKError("OAK-TARGET-PATH", "target profile must be a regular file")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(absolute, flags)
            with os.fdopen(descriptor, "rb") as stream:
                details = os.fstat(stream.fileno())
                if not stat.S_ISREG(details.st_mode):
                    raise ValueError("target profile is not a regular file")
                content = stream.read(MAXIMUM_TARGET_BYTES + 1)
            if not content or len(content) > MAXIMUM_TARGET_BYTES:
                raise ValueError("target profile size is outside the accepted range")
            source = content.decode("utf-8")
            tokens = tuple(yaml.scan(source))
            if any(
                isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken))
                for token in tokens
            ):
                raise ValueError("YAML aliases are not accepted")
            document = load_yaml_document(source)
            self._registry.validate("target-profile.schema.json", document)
            return document
        except (
            OSError,
            UnicodeError,
            ValueError,
            yaml.YAMLError,
            ContractValidationError,
        ) as error:
            raise OAKError(
                "OAK-TARGET-INVALID", "target profile failed bounded validation"
            ) from error
