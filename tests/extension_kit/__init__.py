# SPDX-License-Identifier: Apache-2.0
"""Reusable contract checks for OAK extension contributors.

Import these from your own test modules to prove an extension or adapter
honors the SDK contracts: determinism, canonical decisions, error mapping,
licence/evidence fields, parameter validation, argv safety, rollback, and
offline behavior. Every check raises ``AssertionError`` with a specific
message on violation, so they compose directly with pytest.
"""

from tests.extension_kit.argv_checks import (
    INJECTION_PARAMETER_SETS,
    check_argv_injection_resistance,
    check_typed_rollback,
)
from tests.extension_kit.engine_checks import (
    check_engine_determinism,
    check_engine_fails_closed_on_unknown,
    check_engine_matches_reference,
)
from tests.extension_kit.pack_checks import (
    check_pack_embedded_tests,
    check_pack_governance_fields,
    check_pack_lifecycle_dating,
)
from tests.extension_kit.renderer_checks import (
    check_renderer_determinism,
    check_renderer_output_safety,
    check_renderer_replaceability,
)

__all__ = [
    "INJECTION_PARAMETER_SETS",
    "check_argv_injection_resistance",
    "check_engine_determinism",
    "check_engine_fails_closed_on_unknown",
    "check_engine_matches_reference",
    "check_pack_embedded_tests",
    "check_pack_governance_fields",
    "check_pack_lifecycle_dating",
    "check_renderer_determinism",
    "check_renderer_output_safety",
    "check_renderer_replaceability",
    "check_typed_rollback",
]
