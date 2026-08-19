# SPDX-License-Identifier: Apache-2.0
"""The first-party local manifest renderer: canonical JSON review files."""

from typing import Any

from oak.domain import canonical_json_bytes
from oak.domain.extension_sdk import LOCAL_MANIFEST_RENDERER_ID, RENDERER_IDENTITY_BY_ID
from oak.ports.rendering import RenderedFile


class LocalManifestRenderer:
    """Emit the provider-neutral canonical documents as reviewable files."""

    def identity(self) -> dict[str, str]:
        return dict(RENDERER_IDENTITY_BY_ID[LOCAL_MANIFEST_RENDERER_ID])

    def render(
        self,
        *,
        bundle: dict[str, Any],
        semantic_manifest: dict[str, Any],
        components: tuple[dict[str, Any], ...],
    ) -> tuple[RenderedFile, ...]:
        identity = self.identity()
        component_lock = semantic_manifest["content"]["component_lock"]
        summary = "\n".join(
            [
                "# Rendered deployment artifacts",
                "",
                f"- Renderer: `{identity['id']}` `{identity['version']}`",
                f"- Renderer digest: `{identity['digest']}`",
                f"- Bundle: `{bundle['id']}` (digest-bound canonical source)",
                f"- Semantic manifest: `{semantic_manifest['id']}`",
                "",
                "These files are inert review artifacts. Nothing was executed, and",
                "no target was contacted; apply authority stays with the signed,",
                "approved, independently verified runner path.",
                "",
            ]
        )
        return (
            RenderedFile(
                path="manifests/deployment-bundle.json",
                content=canonical_json_bytes(bundle) + b"\n",
            ),
            RenderedFile(
                path="manifests/semantic-manifest.json",
                content=canonical_json_bytes(semantic_manifest) + b"\n",
            ),
            RenderedFile(
                path="manifests/component-lock.json",
                content=canonical_json_bytes({"component_lock": component_lock}) + b"\n",
            ),
            RenderedFile(path="RENDERING.md", content=summary.encode("utf-8")),
        )
