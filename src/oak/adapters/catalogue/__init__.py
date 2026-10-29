# SPDX-License-Identifier: Apache-2.0
"""Local catalogue adapters."""

from oak.adapters.catalogue.extension_catalogue import ExtensionFedCatalogue
from oak.adapters.catalogue.local_catalogue import LocalCatalogue, read_bounded_catalogue_document
from oak.adapters.catalogue.research_vocabulary import ResearchVocabularyLoader

__all__ = [
    "ExtensionFedCatalogue",
    "LocalCatalogue",
    "ResearchVocabularyLoader",
    "read_bounded_catalogue_document",
]
