# SPDX-License-Identifier: Apache-2.0
"""Provider-neutral local catalogue source contract."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class CatalogueDocuments:
    manifests: tuple[dict[str, Any], ...]
    patterns: tuple[dict[str, Any], ...]


class CataloguePort(Protocol):
    def load(self) -> CatalogueDocuments: ...
