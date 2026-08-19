# SPDX-License-Identifier: Apache-2.0
"""Deterministic Helm/Kubernetes chart-shaped renderer.

The second deployment backend recorded by ADR-0005 and `OAK-FR-DEP-007`:
fully rendered, digest-pinned, deny-all-egress Kubernetes manifests inside a
chart layout that any external Kubernetes tooling can consume out-of-band.
Nothing here executes helm or kubectl, contacts a cluster, or makes
Kubernetes a requirement.
"""

import re
from typing import Any

import yaml

from oak.domain import OAKError
from oak.domain.extension_sdk import HELM_KUBERNETES_RENDERER_ID, RENDERER_IDENTITY_BY_ID
from oak.ports.rendering import RenderedFile

_NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
_IMAGE_PATTERN = re.compile(r"^[a-z0-9][A-Za-z0-9./_:@-]*@sha256:[a-f0-9]{64}$")


class HelmKubernetesRenderer:
    """Render the semantic manifest into a chart of pinned, egress-free manifests."""

    def identity(self) -> dict[str, str]:
        return dict(RENDERER_IDENTITY_BY_ID[HELM_KUBERNETES_RENDERER_ID])

    def render(
        self,
        *,
        bundle: dict[str, Any],
        semantic_manifest: dict[str, Any],
        components: tuple[dict[str, Any], ...],
    ) -> tuple[RenderedFile, ...]:
        identity = self.identity()
        content = semantic_manifest["content"]
        candidate = content["candidate"]
        namespace = _safe_name(f"oak-{str(candidate['id']).removeprefix('candidate-')}")
        component_by_id = {str(component["id"]): component for component in components}
        workloads: list[tuple[str, str]] = []
        for lock_entry in candidate["components"]:
            manifest_id = str(lock_entry["manifest_id"])
            component = component_by_id.get(manifest_id)
            if component is None:
                raise OAKError(
                    "OAK-RENDER-COMPONENT",
                    "component manifest for the lock entry is not available",
                )
            image = str(component["artifact"]["reference"])
            if not _IMAGE_PATTERN.fullmatch(image):
                raise OAKError(
                    "OAK-RENDER-IMAGE",
                    "component image reference must be digest-pinned",
                )
            workloads.append((_safe_name(manifest_id.removeprefix("component.")), image))

        files: list[RenderedFile] = [
            _yaml_file(
                "chart/Chart.yaml",
                {
                    "apiVersion": "v2",
                    "appVersion": str(candidate["id"]),
                    "description": ("Deterministic OAK Community render; review material only."),
                    "name": namespace,
                    "type": "application",
                    "version": str(bundle["version"]),
                },
            ),
            _yaml_file(
                "chart/values.yaml",
                {
                    "namespace": namespace,
                    "workloads": [
                        {"image": image, "name": name, "replicas": 1} for name, image in workloads
                    ],
                },
            ),
            _yaml_file(
                "chart/templates/namespace.yaml",
                {
                    "apiVersion": "v1",
                    "kind": "Namespace",
                    "metadata": {
                        "labels": _labels(bundle, identity),
                        "name": namespace,
                    },
                },
            ),
            _yaml_file(
                "chart/templates/networkpolicy.yaml",
                {
                    "apiVersion": "networking.k8s.io/v1",
                    "kind": "NetworkPolicy",
                    "metadata": {
                        "labels": _labels(bundle, identity),
                        "name": "deny-all-egress",
                        "namespace": namespace,
                    },
                    "spec": {
                        "podSelector": {},
                        "policyTypes": ["Egress", "Ingress"],
                        "egress": [],
                        "ingress": [
                            {"from": [{"podSelector": {}}]},
                        ],
                    },
                },
            ),
        ]
        for name, image in workloads:
            files.append(
                _yaml_file(
                    f"chart/templates/deployment-{name}.yaml",
                    {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "metadata": {
                            "labels": _labels(bundle, identity),
                            "name": name,
                            "namespace": namespace,
                        },
                        "spec": {
                            "replicas": 1,
                            "selector": {"matchLabels": {"app.kubernetes.io/name": name}},
                            "template": {
                                "metadata": {
                                    "labels": {
                                        **_labels(bundle, identity),
                                        "app.kubernetes.io/name": name,
                                    }
                                },
                                "spec": {
                                    "automountServiceAccountToken": False,
                                    "containers": [
                                        {
                                            "image": image,
                                            "imagePullPolicy": "IfNotPresent",
                                            "name": name,
                                            "securityContext": {
                                                "allowPrivilegeEscalation": False,
                                                "readOnlyRootFilesystem": True,
                                                "runAsNonRoot": True,
                                            },
                                        }
                                    ],
                                },
                            },
                        },
                    },
                )
            )
        summary = "\n".join(
            [
                "# Rendered Kubernetes chart",
                "",
                f"- Renderer: `{identity['id']}` `{identity['version']}`",
                f"- Renderer digest: `{identity['digest']}`",
                f"- Bundle: `{bundle['id']}` (digest-bound canonical source)",
                f"- Semantic manifest: `{semantic_manifest['id']}`",
                f"- Namespace: `{namespace}` with a default deny-all egress policy",
                "",
                "Fully rendered chart-shaped manifests with digest-pinned images.",
                "Nothing executed helm or kubectl and no cluster was contacted;",
                "Kubernetes remains optional and apply authority stays with the",
                "signed, approved, independently verified runner path.",
                "",
            ]
        )
        files.append(RenderedFile(path="RENDERING.md", content=summary.encode("utf-8")))
        return tuple(files)


def _labels(bundle: dict[str, Any], identity: dict[str, str]) -> dict[str, str]:
    return {
        "app.kubernetes.io/managed-by": "oak-community",
        "oak.example/bundle-id": _safe_label(str(bundle["id"])),
        "oak.example/renderer": _safe_label(identity["id"]),
    }


def _safe_name(value: str) -> str:
    candidate = re.sub(r"[^a-z0-9-]", "-", value.lower()).strip("-")[:63]
    if not candidate or not _NAME_PATTERN.fullmatch(candidate):
        raise OAKError("OAK-RENDER-NAME", "rendered resource name is unsafe")
    return candidate


def _safe_label(value: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9._-]", "-", value)[:63].strip("-_.")
    if not candidate:
        raise OAKError("OAK-RENDER-NAME", "rendered label value is unsafe")
    return candidate


def _yaml_file(path: str, document: dict[str, Any]) -> RenderedFile:
    rendered = yaml.safe_dump(
        document,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=True,
    )
    return RenderedFile(path=path, content=rendered.encode("utf-8"))
