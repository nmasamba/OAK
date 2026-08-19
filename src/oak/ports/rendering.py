# SPDX-License-Identifier: Apache-2.0
"""Deployment renderer port: canonical plan in, deterministic inert files out.

Renderers transform the immutable compiled bundle, semantic manifest, and
component manifests into target-shaped declarative artifacts. They execute
nothing, mutate nothing, and cannot weaken runner rules: rendered files are
review material until the signed/approved runner path applies anything.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class RenderedFile:
    """One deterministic output file with a safe relative path."""

    path: str
    content: bytes


class DeploymentRendererPort(Protocol):
    """Render one compiled case into a target-specific declarative file set."""

    def identity(self) -> dict[str, str]: ...

    def render(
        self,
        *,
        bundle: dict[str, Any],
        semantic_manifest: dict[str, Any],
        components: tuple[dict[str, Any], ...],
    ) -> tuple[RenderedFile, ...]: ...
