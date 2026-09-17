# SPDX-License-Identifier: Apache-2.0
"""Runtime support for canonical external contracts."""

from oak.contracts.document import CanonicalDocument
from oak.contracts.intent_paths import (
    ADMISSIBLE_INTENT_PATHS,
    intent_section,
    is_admissible_intent_path,
)
from oak.contracts.registry import (
    ContractValidationError,
    SchemaRegistry,
    payload_safe_reason,
)
from oak.contracts.yaml_document import (
    load_alias_free_yaml_document,
    load_json_document,
    load_yaml_document,
)

__all__ = [
    "ADMISSIBLE_INTENT_PATHS",
    "CanonicalDocument",
    "ContractValidationError",
    "SchemaRegistry",
    "intent_section",
    "is_admissible_intent_path",
    "load_alias_free_yaml_document",
    "load_json_document",
    "load_yaml_document",
    "payload_safe_reason",
]
