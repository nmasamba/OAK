# SPDX-License-Identifier: Apache-2.0
"""The research run as the application sees it: a runner the adapter provides (ADR-0018)."""

from collections.abc import Callable
from typing import Any, Protocol

from oak.domain import Artifact


class ResearchRun(Protocol):
    """What one run returns: the snapshot document and the manifests it names."""

    @property
    def snapshot(self) -> dict[str, Any]: ...

    @property
    def manifests(self) -> tuple[Artifact, ...]: ...


# `run_research` in `oak.adapters.models.research_sources`, injected so the application
# never imports an adapter; bootstrap wires the real one and tests may wire a fake.
ResearchRunner = Callable[..., ResearchRun]
# `(fetch, source_mode, hosts)` for one run, built at the moment of use.
ResearchSourceFactory = Callable[[str], tuple[Any, str, frozenset[str]]]
ResearchSourceMode = Callable[[], tuple[str, frozenset[str]]]

__all__ = ["ResearchRun", "ResearchRunner", "ResearchSourceFactory", "ResearchSourceMode"]
