# SPDX-License-Identifier: Apache-2.0
"""Extension store port: quarantined-by-default governed extension entries."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

QUARANTINED = "quarantined"
ACTIVE = "active"


@dataclass(frozen=True, slots=True)
class ExtensionEntry:
    """One installed extension version and its store state."""

    extension_id: str
    version: str
    state: str
    manifest: dict[str, Any]


class ExtensionStorePort(Protocol):
    """File mechanics for the local extension store; policy lives above it."""

    def install(self, source: Path) -> ExtensionEntry: ...

    def list_entries(self) -> tuple[ExtensionEntry, ...]: ...

    def entry(self, extension_id: str, version: str | None) -> ExtensionEntry: ...

    def payload_names(self, entry: ExtensionEntry) -> tuple[str, ...]: ...

    def payload_bytes(self, entry: ExtensionEntry, name: str) -> bytes: ...

    def store_report(self, entry: ExtensionEntry, report: dict[str, Any]) -> None: ...

    def activate(self, entry: ExtensionEntry, activation: dict[str, Any]) -> ExtensionEntry: ...

    def deactivate(self, extension_id: str, version: str | None) -> ExtensionEntry: ...

    def activation_record(self, entry: ExtensionEntry) -> dict[str, Any] | None: ...

    def read_source_manifest(self, source: Path) -> dict[str, Any]: ...

    def write_source_manifest(self, source: Path, manifest: dict[str, Any]) -> None: ...

    def source_payload_listing(self, source: Path) -> list[dict[str, Any]]: ...
