# SPDX-License-Identifier: Apache-2.0
"""Versioned extension SDK contracts and capability discovery.

Every extension class binds to one versioned interface declared here as code.
Extension payloads are governed data; implementations (policy engines,
deployment renderers, runner adapters) are in-tree code whose identities and
digests are pinned constants, mirroring `oak.domain.runner_adapters`: the
allowlist is code, never extension data.
"""

from dataclasses import dataclass
from typing import Any

from oak.domain.artifacts import canonical_json_bytes, content_digest
from oak.domain.runner_adapters import ADAPTER_IDENTITY_BY_ID, ALLOWED_KINDS_BY_ADAPTER

SDK_VERSION = "1.0.0"

POLICY_PACK_CLASS = "policy-pack"
DEPLOYMENT_ADAPTER_CLASS = "deployment-adapter"
COMPONENT_MANIFEST_CLASS = "component-manifest"
ARCHITECTURE_PATTERN_CLASS = "architecture-pattern"
RUNNER_ADAPTER_CLASS = "runner-adapter"


@dataclass(frozen=True, slots=True)
class ExtensionInterface:
    """One extension class's versioned contract."""

    extension_class: str
    interface_version: str
    payload_schema: str | None
    description: str
    capabilities: tuple[str, ...]

    def to_document(self) -> dict[str, Any]:
        return {
            "extension_class": self.extension_class,
            "interface_version": self.interface_version,
            "payload_schema": self.payload_schema,
            "description": self.description,
            "capabilities": list(self.capabilities),
        }


INTERFACE_BY_CLASS: dict[str, ExtensionInterface] = {
    POLICY_PACK_CLASS: ExtensionInterface(
        extension_class=POLICY_PACK_CLASS,
        interface_version="1.0.0",
        payload_schema="policy-pack.schema.json",
        description=(
            "Effective-dated, scoped, reviewable rule packs evaluated through the "
            "policy port into canonical policy decisions."
        ),
        capabilities=("evaluate", "embedded-tests", "effective-dating", "scoping"),
    ),
    DEPLOYMENT_ADAPTER_CLASS: ExtensionInterface(
        extension_class=DEPLOYMENT_ADAPTER_CLASS,
        interface_version="1.0.0",
        payload_schema=None,
        description=(
            "Configuration binding a registered in-tree deployment renderer identity; "
            "renderers emit deterministic declarative artifacts and execute nothing."
        ),
        capabilities=("render", "deterministic-output", "digest-pinned-images"),
    ),
    COMPONENT_MANIFEST_CLASS: ExtensionInterface(
        extension_class=COMPONENT_MANIFEST_CLASS,
        interface_version="1.0.0",
        payload_schema="component-manifest.schema.json",
        description="Governed catalogue component manifests with licence and evidence lineage.",
        capabilities=("catalogue-eligibility", "licence-classes", "evidence-freshness"),
    ),
    ARCHITECTURE_PATTERN_CLASS: ExtensionInterface(
        extension_class=ARCHITECTURE_PATTERN_CLASS,
        interface_version="1.0.0",
        payload_schema="architecture-pattern.schema.json",
        description="Provider-neutral architecture patterns with role capability requirements.",
        capabilities=("candidate-expansion", "role-capability-matching"),
    ),
    RUNNER_ADAPTER_CLASS: ExtensionInterface(
        extension_class=RUNNER_ADAPTER_CLASS,
        interface_version="1.0.0",
        payload_schema=None,
        description=(
            "In-tree typed runner adapters registered in oak.domain.runner_adapters; "
            "extensions may document and configure them but never carry code."
        ),
        capabilities=("typed-operations", "allowlisted-argv", "independent-verification"),
    ),
}

LOCAL_MANIFEST_RENDERER_ID = "renderer.local-manifests"
LOCAL_MANIFEST_RENDERER_VERSION = "0.1.0"
LOCAL_MANIFEST_RENDERER_DIGEST = content_digest(
    canonical_json_bytes(
        {
            "id": LOCAL_MANIFEST_RENDERER_ID,
            "version": LOCAL_MANIFEST_RENDERER_VERSION,
            "authority": "declarative-local-manifest-render",
        }
    )
)
HELM_KUBERNETES_RENDERER_ID = "renderer.helm-kubernetes"
HELM_KUBERNETES_RENDERER_VERSION = "0.1.0"
HELM_KUBERNETES_RENDERER_DIGEST = content_digest(
    canonical_json_bytes(
        {
            "id": HELM_KUBERNETES_RENDERER_ID,
            "version": HELM_KUBERNETES_RENDERER_VERSION,
            "authority": "declarative-kubernetes-chart-render",
        }
    )
)

RENDERER_IDENTITY_BY_ID: dict[str, dict[str, str]] = {
    LOCAL_MANIFEST_RENDERER_ID: {
        "id": LOCAL_MANIFEST_RENDERER_ID,
        "version": LOCAL_MANIFEST_RENDERER_VERSION,
        "digest": LOCAL_MANIFEST_RENDERER_DIGEST,
    },
    HELM_KUBERNETES_RENDERER_ID: {
        "id": HELM_KUBERNETES_RENDERER_ID,
        "version": HELM_KUBERNETES_RENDERER_VERSION,
        "digest": HELM_KUBERNETES_RENDERER_DIGEST,
    },
}

BUILTIN_POLICY_ENGINE_ID = "policy-engine.builtin"
OPA_POLICY_ENGINE_ID = "policy-engine.opa"
POLICY_ENGINE_IDS = (BUILTIN_POLICY_ENGINE_ID, OPA_POLICY_ENGINE_ID)


def capability_document() -> dict[str, Any]:
    """A deterministic snapshot of every SDK interface and registered implementation."""

    return {
        "sdk_version": SDK_VERSION,
        "interfaces": [
            INTERFACE_BY_CLASS[name].to_document() for name in sorted(INTERFACE_BY_CLASS)
        ],
        "policy_engines": [
            {"id": BUILTIN_POLICY_ENGINE_ID, "kind": "builtin", "required": True},
            {"id": OPA_POLICY_ENGINE_ID, "kind": "external-binary", "required": False},
        ],
        "deployment_renderers": [
            RENDERER_IDENTITY_BY_ID[name] for name in sorted(RENDERER_IDENTITY_BY_ID)
        ],
        "runner_adapters": [
            {
                **ADAPTER_IDENTITY_BY_ID[name],
                "allowed_kinds": sorted(ALLOWED_KINDS_BY_ADAPTER[name]),
            }
            for name in sorted(ADAPTER_IDENTITY_BY_ID)
        ],
    }
