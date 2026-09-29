# SPDX-License-Identifier: Apache-2.0
"""Shared adapter identity and parameter contracts for compiler and runner.

The compiler stamps these identities into plans; the runner independently
recomputes them from this module and refuses any operation whose adapter or
parameter-schema digest differs. The allowlist is code, never plan data.
"""

import hashlib
import re
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
CONTAINER_ADAPTER_VERSION = "0.2.0"
# What `isolation` a plan may request, and the target-profile acknowledgement each needs.
# A profile acknowledging only the fixture keeps the never-started behaviour; starting is
# a separate, explicit operator acknowledgement (ADR-0017).
ISOLATION_NEVER_STARTED = "network-none-never-started"
ISOLATION_STARTED_HARDENED = "network-none-started-hardened"
ACKNOWLEDGEMENT_FIXTURE_ONLY = "isolated-non-production-fixture-only"
ACKNOWLEDGEMENT_HARDENED_START = "isolated-non-production-hardened-start"
ISOLATION_BY_ACKNOWLEDGEMENT = {
    ACKNOWLEDGEMENT_FIXTURE_ONLY: ISOLATION_NEVER_STARTED,
    ACKNOWLEDGEMENT_HARDENED_START: ISOLATION_STARTED_HARDENED,
}
# Fixed flags on every started container. They are code, not plan data, and they are
# part of the adapter identity below: a plan compiled against one hardening set does not
# verify against a runner enforcing another.
HARDENING_FLAGS = (
    "--read-only",
    "--cap-drop=ALL",
    "--security-opt=no-new-privileges",
    "--user=65534:65534",
    "--memory=256m",
    "--memory-swap=256m",
    "--cpus=0.5",
    "--pids-limit=64",
    "--restart=no",
    "--log-driver=none",
)
CONTAINER_ADAPTER_DIGEST = content_digest(
    canonical_json_bytes(
        {
            "id": CONTAINER_ADAPTER_ID,
            "version": CONTAINER_ADAPTER_VERSION,
            "authority": "isolated-reversible-topology-installation",
            "network": "none",
            "hardening": list(HARDENING_FLAGS),
        }
    )
)
CONTAINER_NAME_PATTERN = r"^oak-fixture-[a-z0-9][a-z0-9-]{0,62}$"
# The canonical identifier shape (common.schema.json): it cannot begin with "-" and holds
# no whitespace, so a value can never be read as a flag or split into two arguments.
IDENTIFIER_PATTERN = r"^[A-Za-z][A-Za-z0-9._:/-]{2,159}$"
IMAGE_REFERENCE_PATTERN = r"^[a-z0-9][a-zA-Z0-9./_:-]*$"
INSTALLATION_ID_PATTERN = r"^installation\.[a-f0-9]{24}$"
MAXIMUM_CONTAINERS = 16
CONTAINER_PARAMETER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["case_id", "target_id", "installation_id", "isolation", "containers"],
    "properties": {
        "case_id": {"type": "string", "pattern": IDENTIFIER_PATTERN},
        "target_id": {"type": "string", "pattern": IDENTIFIER_PATTERN},
        "installation_id": {"type": "string", "pattern": INSTALLATION_ID_PATTERN},
        "isolation": {"enum": [ISOLATION_NEVER_STARTED, ISOLATION_STARTED_HARDENED]},
        "containers": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAXIMUM_CONTAINERS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "node_id",
                    "manifest_id",
                    "container_name",
                    "image_reference",
                    "image_digest",
                ],
                "properties": {
                    "node_id": {"type": "string", "pattern": IDENTIFIER_PATTERN},
                    "manifest_id": {"type": "string", "pattern": IDENTIFIER_PATTERN},
                    "container_name": {"type": "string", "pattern": CONTAINER_NAME_PATTERN},
                    # A reference may not carry its own digest: the approved digest is the
                    # only pin that reaches the runtime.
                    "image_reference": {
                        "type": "string",
                        "minLength": 3,
                        "maxLength": 300,
                        "pattern": IMAGE_REFERENCE_PATTERN,
                    },
                    "image_digest": {"type": "string", "pattern": "^sha256:[a-f0-9]{64}$"},
                },
            },
        },
    },
}
CONTAINER_PARAMETER_SCHEMA_DIGEST = content_digest(canonical_json_bytes(CONTAINER_PARAMETER_SCHEMA))
CONTAINER_LABEL_FIXTURE = "oak.fixture"
CONTAINER_LABEL_CASE = "oak.case"
CONTAINER_LABEL_NODE = "oak.node"
CONTAINER_LABEL_INSTALLATION = "oak.installation"
CONTAINER_LABEL_ISOLATION = "oak.isolation"


INSTALLATION_SCOPE_EXTENSION = "oak.community/installation_scope"


def installation_id_for(design_case_ref: dict[str, Any], target_id: str, scope: str) -> str:
    """The identity of one compiled installation: this case version, in this workspace,
    on this target.

    Derived from the plan's own ``design_case_ref`` (id and digest) and its installation
    scope (the workspace that compiled it), so two workspaces built from the same brief —
    which share a case id, and at the same instant even the same case bytes — never share
    an installation, and neither can adopt or remove the other's containers. The runner
    re-derives it from the plan it verified.
    """

    material = "\n".join(
        (
            str(design_case_ref.get("id")),
            str(design_case_ref.get("digest")),
            target_id,
            scope,
        )
    )
    return "installation." + hashlib.sha256(material.encode()).hexdigest()[:24]


def container_name_for(installation_id: str, node_id: str) -> str:
    """The one name a node's container may have in this installation.

    Both the compiler and the runner derive it; the runner refuses a plan naming any
    other container, so a plan cannot address a container outside its own installation.
    The hash carries the identity; the node slug is only there so an operator can read
    ``docker ps``.
    """

    slug = re.sub(r"[^a-z0-9]+", "-", node_id.removeprefix("node.").casefold()).strip("-")
    slug = (slug or "node")[:40].strip("-") or "node"
    identity = hashlib.sha256(f"{installation_id}\n{node_id}".encode()).hexdigest()
    return f"oak-fixture-{slug}-{identity[:12]}"


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


def registry_host(reference: str) -> str:
    """Return the registry host a Docker image reference resolves to.

    Docker's own resolution rule: the first path component names a registry when
    it contains a dot or a colon, is exactly ``localhost``, or contains an uppercase
    letter (a repository name cannot); every other reference is a Docker Hub name and
    resolves to ``docker.io``. The runner uses this to enforce a target profile's
    ``execution.allowed_registries`` before any adapter exists (RR-003, TM-08).
    """

    head, separator, _ = reference.partition("/")
    if not separator:
        return "docker.io"
    if head == "localhost" or "." in head or ":" in head or head != head.lower():
        return head
    return "docker.io"


ARCHITECTURE_BINDING_KEY = "oak.community/architecture"


def plan_installation_digest(plan: dict[str, Any]) -> str | None:
    """Digest of what a plan's ``apply`` operation would install, or None without one.

    Computed identically by the control plane when an architecture approval is recorded
    and by the runner when it verifies one, so the approval names the exact installation
    the signed plan carries rather than a description of it.
    """

    operations = plan.get("operations")
    if not isinstance(operations, list):
        return None
    for operation in operations:
        if isinstance(operation, dict) and operation.get("kind") == "apply":
            parameters = operation.get("parameters")
            if not isinstance(parameters, dict):
                return None
            return content_digest(canonical_json_bytes(parameters))
    return None


def architecture_binding_matches(
    approval: dict[str, Any], bundle: dict[str, Any], plan: dict[str, Any]
) -> bool:
    """Whether an architecture approval approves this bundle's decision and install.

    The approval's own plan and bundle digests are checked elsewhere; this compares what
    it says it approves — the architecture decision the bundle compiles and the digest of
    what ``apply`` installs — with the documents actually dispatched.
    """

    extensions = approval.get("extensions")
    binding = extensions.get(ARCHITECTURE_BINDING_KEY) if isinstance(extensions, dict) else None
    if not isinstance(binding, dict):
        return False
    decision = binding.get("decision_ref")
    expected = bundle.get("architecture_decision_ref")
    if not isinstance(decision, dict) or not isinstance(expected, dict):
        return False
    return (
        decision.get("id") == expected.get("id")
        and decision.get("digest") == expected.get("digest")
        and binding.get("installation_digest") == plan_installation_digest(plan)
    )
