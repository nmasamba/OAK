# SPDX-License-Identifier: Apache-2.0
"""Deployment-renderer contract checks: determinism, safety, replacement."""

from typing import Any

import yaml

from oak.ports.rendering import DeploymentRendererPort, RenderedFile

FORBIDDEN_KEYS = frozenset({"command", "shell", "executable", "argv"})


def check_renderer_determinism(
    renderer: DeploymentRendererPort,
    *,
    bundle: dict[str, Any],
    semantic_manifest: dict[str, Any],
    components: tuple[dict[str, Any], ...],
) -> None:
    """Identical canonical inputs must render byte-identical file sets."""

    first = renderer.render(
        bundle=bundle, semantic_manifest=semantic_manifest, components=components
    )
    second = renderer.render(
        bundle=bundle, semantic_manifest=semantic_manifest, components=components
    )
    assert [(item.path, item.content) for item in first] == [
        (item.path, item.content) for item in second
    ], f"renderer {renderer.identity()['id']} is nondeterministic"


def check_renderer_output_safety(files: tuple[RenderedFile, ...]) -> None:
    """No unsafe paths, no execution fields, no empty artifacts."""

    assert files, "a renderer must produce at least one file"
    seen: set[str] = set()
    for item in files:
        assert item.path not in seen, f"duplicate rendered path {item.path}"
        seen.add(item.path)
        parts = item.path.split("/")
        assert all(part and part != ".." and not part.startswith(".") for part in parts), (
            f"rendered path {item.path!r} is unsafe"
        )
        assert not item.path.startswith("/"), f"rendered path {item.path!r} is absolute"
        assert item.content, f"rendered file {item.path} is empty"
        if item.path.endswith((".yaml", ".yml", ".json")):
            _scan_forbidden(yaml.safe_load(item.content.decode("utf-8")), item.path)


def check_renderer_replaceability(
    renderers: dict[str, DeploymentRendererPort],
    *,
    bundle: dict[str, Any],
    semantic_manifest: dict[str, Any],
    components: tuple[dict[str, Any], ...],
) -> None:
    """Every registered renderer must serve the same port on the same inputs."""

    assert len(renderers) >= 2, "replacement needs at least two renderers"
    for renderer_id, renderer in sorted(renderers.items()):
        identity = renderer.identity()
        assert identity["id"] == renderer_id, "renderer identity must match its registration"
        assert set(identity) == {"id", "version", "digest"}
        files = renderer.render(
            bundle=bundle, semantic_manifest=semantic_manifest, components=components
        )
        check_renderer_output_safety(files)


def _scan_forbidden(value: Any, path: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            assert str(key).casefold() not in FORBIDDEN_KEYS, (
                f"rendered file {path} contains forbidden execution key {key!r}"
            )
            _scan_forbidden(nested, path)
    elif isinstance(value, list):
        for nested in value:
            _scan_forbidden(nested, path)
