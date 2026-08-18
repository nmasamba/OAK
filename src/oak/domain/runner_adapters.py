# SPDX-License-Identifier: Apache-2.0
"""Shared adapter identity and parameter contracts for compiler and runner.

The compiler stamps these identities into plans; the runner independently
recomputes them from this module and refuses any operation whose adapter or
parameter-schema digest differs. The allowlist is code, never plan data.
"""

from typing import Any

from oak.domain.artifacts import canonical_json_bytes, content_digest

REVIEW_ADAPTER_ID = "adapter.local-review"
REVIEW_ADAPTER_VERSION = "0.1.0"
REVIEW_ADAPTER_DIGEST = content_digest(
    canonical_json_bytes(
        {
            "id": REVIEW_ADAPTER_ID,
            "version": REVIEW_ADAPTER_VERSION,
            "authority": "read-only-planning",
        }
    )
)
REVIEW_PARAMETER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["mode", "target_profile_id", "artifact"],
    "properties": {
        "mode": {"const": "read-only"},
        "target_profile_id": {"type": "string", "minLength": 1, "maxLength": 160},
        "artifact": {"type": "string", "minLength": 1, "maxLength": 240},
    },
}
# The digest predates the runtime schema and is pinned by byte-stable plan
# parity for 0.1.0 target profiles; both sides treat it as an opaque contract id.
REVIEW_PARAMETER_SCHEMA_DIGEST = content_digest(
    canonical_json_bytes(
        {
            "allowed_keys": ["artifact", "mode", "target_profile_id"],
            "additional_properties": False,
        }
    )
)

CONTAINER_ADAPTER_ID = "adapter.local-container"
CONTAINER_ADAPTER_VERSION = "0.1.0"
CONTAINER_ADAPTER_DIGEST = content_digest(
    canonical_json_bytes(
        {
            "id": CONTAINER_ADAPTER_ID,
            "version": CONTAINER_ADAPTER_VERSION,
            "authority": "isolated-reversible-fixture-mutation",
        }
    )
)
CONTAINER_NAME_PATTERN = r"^oak-fixture-[a-z0-9][a-z0-9-]{0,62}$"
CONTAINER_PARAMETER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["container_name", "image_reference", "image_digest", "isolation"],
    "properties": {
        "container_name": {"type": "string", "pattern": CONTAINER_NAME_PATTERN},
        "image_reference": {
            "type": "string",
            "minLength": 3,
            "maxLength": 300,
            "pattern": "^[a-z0-9][a-zA-Z0-9./_:@-]*$",
        },
        "image_digest": {"type": "string", "pattern": "^sha256:[a-f0-9]{64}$"},
        "isolation": {"const": "network-none-never-started"},
    },
}
CONTAINER_PARAMETER_SCHEMA_DIGEST = content_digest(canonical_json_bytes(CONTAINER_PARAMETER_SCHEMA))

PARAMETER_SCHEMA_BY_ADAPTER: dict[str, dict[str, Any]] = {
    REVIEW_ADAPTER_ID: REVIEW_PARAMETER_SCHEMA,
    CONTAINER_ADAPTER_ID: CONTAINER_PARAMETER_SCHEMA,
}

ADAPTER_IDENTITY_BY_ID: dict[str, dict[str, str]] = {
    REVIEW_ADAPTER_ID: {
        "id": REVIEW_ADAPTER_ID,
        "version": REVIEW_ADAPTER_VERSION,
        "digest": REVIEW_ADAPTER_DIGEST,
        "parameter_schema_digest": REVIEW_PARAMETER_SCHEMA_DIGEST,
    },
    CONTAINER_ADAPTER_ID: {
        "id": CONTAINER_ADAPTER_ID,
        "version": CONTAINER_ADAPTER_VERSION,
        "digest": CONTAINER_ADAPTER_DIGEST,
        "parameter_schema_digest": CONTAINER_PARAMETER_SCHEMA_DIGEST,
    },
}

ALLOWED_KINDS_BY_ADAPTER: dict[str, frozenset[str]] = {
    REVIEW_ADAPTER_ID: frozenset({"inventory", "validate", "render", "plan", "verify"}),
    CONTAINER_ADAPTER_ID: frozenset({"apply", "rollback", "destroy"}),
}
