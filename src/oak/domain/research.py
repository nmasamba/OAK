# SPDX-License-Identifier: Apache-2.0
"""The closed vocabularies research may draw its terms from (Sprint 14, ADR-0018).

A leaf type: the compiler's pure terms function reads it, the catalogue adapter loads it,
and neither imports the other. Each field is one validated document from
``catalogue/research/``: the capability map, the hardware classes, the licence list, the
owner-reviewed harness list and the research bindings.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ResearchVocabulary:
    capabilities: dict[str, Any]
    hardware_classes: dict[str, Any]
    licences: dict[str, Any]
    harness_repositories: dict[str, Any]
    bindings: tuple[dict[str, Any], ...]
