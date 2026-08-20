# SPDX-License-Identifier: Apache-2.0
"""Read-only deployment rendering: swap renderers without touching the case."""

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from oak.domain import ArtifactReference, OAKError
from oak.ports import WorkspaceRepository
from oak.ports.rendering import DeploymentRendererPort

MANIFEST_MEDIA_TYPE = "application/vnd.oak.component-manifest+json"


class DeploymentRenderService:
    """Render the compiled case's canonical plan through a chosen renderer."""

    def __init__(
        self,
        repository: WorkspaceRepository,
        renderers: Mapping[str, DeploymentRendererPort],
    ) -> None:
        self._repository = repository
        self._renderers = dict(renderers)

    def renderer_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._renderers))

    def render(self, renderer_id: str, output: Path) -> tuple[str, ...]:
        renderer = self._renderers.get(renderer_id)
        if renderer is None:
            raise OAKError("OAK-RENDER-ADAPTER", "deployment renderer is not registered")
        case = self._repository.current_case()
        if case is None:
            raise OAKError("OAK-CASE-NOT-FOUND", "workspace has no design case")
        bundle_value = case.get("deployment_bundle_ref")
        if not isinstance(bundle_value, dict):
            raise OAKError("OAK-DEPENDENCY-MISSING", "rendering requires a compiled bundle")
        bundle = self._repository.read_json_artifact(ArtifactReference.from_document(bundle_value))
        semantic_value = case.get("extensions", {}).get("oak.community/semantic_manifest_ref")
        if not isinstance(semantic_value, dict):
            raise OAKError("OAK-DEPENDENCY-MISSING", "rendering requires a semantic manifest")
        semantic = self._repository.read_json_artifact(
            ArtifactReference.from_document(semantic_value)
        )
        components = tuple(
            self._repository.read_json_artifact(
                ArtifactReference(
                    id=str(entry["manifest_id"]),
                    version=str(entry["version"]),
                    digest=str(entry["digest"]),
                    media_type=MANIFEST_MEDIA_TYPE,
                )
            )
            for entry in semantic["content"]["component_lock"]
        )
        rendered = renderer.render(
            bundle=bundle,
            semantic_manifest=semantic,
            components=components,
        )
        return self._write_output(output, rendered)

    @staticmethod
    def _write_output(destination: Path, rendered: tuple[Any, ...]) -> tuple[str, ...]:
        destination = destination.absolute()
        if destination.exists() or destination.is_symlink():
            raise OAKError("OAK-OUTPUT-EXISTS", "render output directory already exists")
        staging = Path(tempfile.mkdtemp(prefix=".oak-render-", dir=destination.parent))
        written: list[str] = []
        try:
            for item in rendered:
                relative = str(item.path)
                parts = relative.split("/")
                if any(not part or part.startswith(".") or part == ".." for part in parts):
                    raise OAKError("OAK-RENDER-PATH", "rendered file path is unsafe")
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(item.content)
                written.append(relative)
            os.replace(staging, destination)
        except Exception:
            import shutil

            shutil.rmtree(staging, ignore_errors=True)
            raise
        return tuple(sorted(written))
