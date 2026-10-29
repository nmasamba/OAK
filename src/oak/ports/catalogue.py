# SPDX-License-Identifier: Apache-2.0
"""Provider-neutral local catalogue source contract."""

from dataclasses import dataclass, field
from typing import Any, Protocol

from oak.domain import ResearchVocabulary


@dataclass(frozen=True, slots=True)
class CatalogueDocuments:
    manifests: tuple[dict[str, Any], ...]
    patterns: tuple[dict[str, Any], ...]
    #: Where a document came from, by its id, for anything not curated: an activated
    #: extension the trust directory vouched for. Absent means curated.
    provenance: dict[str, dict[str, Any]] = field(default_factory=dict)


class CataloguePort(Protocol):
    def load(self) -> CatalogueDocuments: ...


class ResearchVocabularyPort(Protocol):
    def load(self) -> ResearchVocabulary: ...


__all__ = [
    "CatalogueDocuments",
    "CataloguePort",
    "ResearchVocabulary",
    "ResearchVocabularyPort",
]
