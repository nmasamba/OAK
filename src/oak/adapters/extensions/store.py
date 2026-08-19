# SPDX-License-Identifier: Apache-2.0
"""Bounded local extension store: quarantine by default, explicit activation.

The on-disk directory name (``<id>@<version>``) is authoritative for identity,
mirroring the runner mailbox rule: nothing is trusted because a document says
so. Payload files are copied with bounded sizes, no symlinks, and no traversal.
"""

import json
import os
import shutil
import stat
from pathlib import Path
from typing import Any

import yaml

from oak.contracts import SchemaRegistry, load_yaml_document
from oak.domain import OAKError, content_digest
from oak.ports.extensions import ACTIVE, QUARANTINED, ExtensionEntry

MEDIA_BY_SUFFIX = {
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".json": "application/json",
    ".md": "text/markdown",
}
MANIFEST_NAME = "extension.yaml"
REPORT_NAME = "verification-report.json"
ACTIVATION_NAME = "activation.json"
RESERVED_NAMES = frozenset({MANIFEST_NAME, REPORT_NAME, ACTIVATION_NAME})
MAXIMUM_DOCUMENT_BYTES = 524_288
MAXIMUM_PAYLOAD_BYTES = 4_194_304
MAXIMUM_PAYLOAD_FILES = 64
ACTIVE_PACKS_DIRECTORY = "active-packs"


class LocalExtensionStore:
    """Quarantine/active extension directories under one private root."""

    def __init__(self, root: Path, registry: SchemaRegistry) -> None:
        self._root = root
        self._registry = registry

    def install(self, source: Path) -> ExtensionEntry:
        source = source.absolute()
        if not source.is_dir() or source.is_symlink():
            raise OAKError("OAK-EXTENSION-SOURCE", "extension source must be a plain directory")
        manifest = self._read_manifest(source / MANIFEST_NAME)
        extension_id = str(manifest["id"])
        version = str(manifest["version"])
        directory_name = self._directory_name(extension_id, version)
        for state_dir in (QUARANTINED, ACTIVE):
            if (self._root / state_dir / directory_name).exists():
                raise OAKError("OAK-EXTENSION-EXISTS", "extension version is already installed")
        destination = self._root / QUARANTINED / directory_name
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        staged = destination.parent / f".staging-{directory_name}"
        if staged.exists():
            shutil.rmtree(staged)
        staged.mkdir(mode=0o700)
        try:
            self._copy_bounded(source / MANIFEST_NAME, staged / MANIFEST_NAME)
            names = self._source_payload_names(source)
            for name in names:
                target = staged / name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                self._copy_bounded(source / name, target)
            os.replace(staged, destination)
        except Exception:
            if staged.exists():
                shutil.rmtree(staged, ignore_errors=True)
            raise
        return ExtensionEntry(
            extension_id=extension_id,
            version=version,
            state=QUARANTINED,
            manifest=manifest,
        )

    def list_entries(self) -> tuple[ExtensionEntry, ...]:
        entries: list[ExtensionEntry] = []
        for state in (QUARANTINED, ACTIVE):
            state_root = self._root / state
            if not state_root.is_dir():
                continue
            for directory in sorted(state_root.iterdir()):
                if not directory.is_dir() or directory.name.startswith("."):
                    continue
                entries.append(self._entry_from_directory(directory, state))
        return tuple(entries)

    def entry(self, extension_id: str, version: str | None) -> ExtensionEntry:
        matches = [
            entry
            for entry in self.list_entries()
            if entry.extension_id == extension_id and (version is None or entry.version == version)
        ]
        if not matches:
            raise OAKError("OAK-EXTENSION-NOT-FOUND", "extension is not installed")
        if len(matches) > 1:
            raise OAKError(
                "OAK-EXTENSION-AMBIGUOUS",
                "multiple versions are installed; pass --version",
            )
        return matches[0]

    def payload_names(self, entry: ExtensionEntry) -> tuple[str, ...]:
        directory = self._entry_directory(entry)
        names: list[str] = []
        for path in sorted(directory.rglob("*")):
            if path.is_dir():
                continue
            relative = path.relative_to(directory).as_posix()
            if relative in RESERVED_NAMES or relative.endswith(".md"):
                continue
            names.append(relative)
        if len(names) > MAXIMUM_PAYLOAD_FILES:
            raise OAKError("OAK-EXTENSION-PAYLOAD", "extension payload has too many files")
        return tuple(names)

    def payload_bytes(self, entry: ExtensionEntry, name: str) -> bytes:
        self._check_component_path(name)
        path = self._entry_directory(entry) / name
        return self._read_bounded(path, MAXIMUM_PAYLOAD_BYTES)

    def store_report(self, entry: ExtensionEntry, report: dict[str, Any]) -> None:
        path = self._entry_directory(entry) / REPORT_NAME
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(path, 0o600)

    def activate(self, entry: ExtensionEntry, activation: dict[str, Any]) -> ExtensionEntry:
        if entry.state != QUARANTINED:
            raise OAKError("OAK-EXTENSION-STATE", "only a quarantined extension can activate")
        directory_name = self._directory_name(entry.extension_id, entry.version)
        source = self._root / QUARANTINED / directory_name
        destination = self._root / ACTIVE / directory_name
        if destination.exists():
            raise OAKError("OAK-EXTENSION-EXISTS", "extension version is already active")
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        activation_path = source / ACTIVATION_NAME
        activation_path.write_text(
            json.dumps(activation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(activation_path, 0o600)
        os.replace(source, destination)
        activated = ExtensionEntry(
            extension_id=entry.extension_id,
            version=entry.version,
            state=ACTIVE,
            manifest=entry.manifest,
        )
        self._materialize_pack(activated)
        return activated

    def deactivate(self, extension_id: str, version: str | None) -> ExtensionEntry:
        entry = self.entry(extension_id, version)
        if entry.state != ACTIVE:
            raise OAKError("OAK-EXTENSION-STATE", "extension is not active")
        directory_name = self._directory_name(entry.extension_id, entry.version)
        source = self._root / ACTIVE / directory_name
        destination = self._root / QUARANTINED / directory_name
        if destination.exists():
            raise OAKError("OAK-EXTENSION-EXISTS", "a quarantined copy already exists")
        pack_path = self._root / ACTIVE_PACKS_DIRECTORY / f"{entry.extension_id}.yaml"
        pack_path.unlink(missing_ok=True)
        (source / ACTIVATION_NAME).unlink(missing_ok=True)
        os.replace(source, destination)
        return ExtensionEntry(
            extension_id=entry.extension_id,
            version=entry.version,
            state=QUARANTINED,
            manifest=entry.manifest,
        )

    def activation_record(self, entry: ExtensionEntry) -> dict[str, Any] | None:
        path = self._entry_directory(entry) / ACTIVATION_NAME
        if not path.is_file():
            return None
        document = json.loads(self._read_bounded(path, MAXIMUM_DOCUMENT_BYTES).decode("utf-8"))
        if not isinstance(document, dict):
            raise OAKError("OAK-EXTENSION-CORRUPT", "activation record is not an object")
        return document

    def read_source_manifest(self, source: Path) -> dict[str, Any]:
        source = source.absolute()
        if not source.is_dir() or source.is_symlink():
            raise OAKError("OAK-EXTENSION-SOURCE", "extension source must be a plain directory")
        return self._read_manifest(source / MANIFEST_NAME)

    def write_source_manifest(self, source: Path, manifest: dict[str, Any]) -> None:
        path = source.absolute() / MANIFEST_NAME
        rendered = yaml.safe_dump(manifest, allow_unicode=True, sort_keys=True)
        path.write_text(f"# SPDX-License-Identifier: Apache-2.0\n{rendered}", encoding="utf-8")

    def source_payload_listing(self, source: Path) -> list[dict[str, Any]]:
        source = source.absolute()
        listing: list[dict[str, Any]] = []
        for name in self._source_payload_names(source):
            content = self._read_bounded(source / name, MAXIMUM_PAYLOAD_BYTES)
            suffix = Path(name).suffix.lower()
            listing.append(
                {
                    "path": name,
                    "digest": content_digest(content),
                    "media_type": MEDIA_BY_SUFFIX.get(suffix, "application/octet-stream"),
                }
            )
        return sorted(listing, key=lambda item: str(item["path"]))

    def _materialize_pack(self, entry: ExtensionEntry) -> None:
        if str(entry.manifest.get("extension_class")) != "policy-pack":
            return
        pack_bytes = self.payload_bytes(entry, "pack.yaml")
        packs_root = self._root / ACTIVE_PACKS_DIRECTORY
        packs_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = packs_root / f"{entry.extension_id}.yaml"
        target.write_bytes(pack_bytes)
        os.chmod(target, 0o600)

    def _entry_directory(self, entry: ExtensionEntry) -> Path:
        return self._root / entry.state / self._directory_name(entry.extension_id, entry.version)

    def _entry_from_directory(self, directory: Path, state: str) -> ExtensionEntry:
        manifest = self._read_manifest(directory / MANIFEST_NAME)
        name = directory.name
        if "@" not in name:
            raise OAKError("OAK-EXTENSION-CORRUPT", "extension directory name is invalid")
        directory_id, _, directory_version = name.partition("@")
        if str(manifest["id"]) != directory_id or str(manifest["version"]) != directory_version:
            raise OAKError(
                "OAK-EXTENSION-CORRUPT",
                "extension manifest identity does not match its directory",
            )
        return ExtensionEntry(
            extension_id=directory_id,
            version=directory_version,
            state=state,
            manifest=manifest,
        )

    def _read_manifest(self, path: Path) -> dict[str, Any]:
        content = self._read_bounded(path, MAXIMUM_DOCUMENT_BYTES)
        try:
            text = content.decode("utf-8")
            for token in yaml.scan(text):
                if isinstance(token, (yaml.AliasToken, yaml.AnchorToken)):
                    raise OAKError(
                        "OAK-EXTENSION-MANIFEST", "extension manifest must not use YAML aliases"
                    )
            document = load_yaml_document(text)
        except OAKError:
            raise
        except Exception as error:
            raise OAKError(
                "OAK-EXTENSION-MANIFEST", "extension manifest failed bounded parsing"
            ) from error
        self._registry.validate("extension-manifest.schema.json", document)
        return document

    def _source_payload_names(self, source: Path) -> tuple[str, ...]:
        # Documentation (*.md) travels with templates but is never governed
        # payload: it is not copied into the store, digested, or verified.
        names: list[str] = []
        for path in sorted(source.rglob("*")):
            if path.is_dir():
                continue
            relative = path.relative_to(source).as_posix()
            if relative in RESERVED_NAMES or relative.startswith(".") or relative.endswith(".md"):
                continue
            self._check_component_path(relative)
            names.append(relative)
        if len(names) > MAXIMUM_PAYLOAD_FILES:
            raise OAKError("OAK-EXTENSION-PAYLOAD", "extension payload has too many files")
        return tuple(names)

    def _copy_bounded(self, source: Path, destination: Path) -> None:
        content = self._read_bounded(source, MAXIMUM_PAYLOAD_BYTES)
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)

    @staticmethod
    def _read_bounded(path: Path, maximum: int) -> bytes:
        if path.is_symlink():
            raise OAKError("OAK-EXTENSION-PATH", "extension files must not be symlinks")
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError as error:
            raise OAKError("OAK-EXTENSION-NOT-FOUND", "extension file does not exist") from error
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise OAKError("OAK-EXTENSION-PATH", "extension files must be regular files")
            content = os.read(descriptor, maximum + 1)
        finally:
            os.close(descriptor)
        if not content or len(content) > maximum:
            raise OAKError("OAK-EXTENSION-PAYLOAD", "extension file size is out of bounds")
        return content

    @staticmethod
    def _check_component_path(name: str) -> None:
        parts = name.split("/")
        for part in parts:
            if not part or part.startswith(".") or "\\" in part or part == "..":
                raise OAKError("OAK-EXTENSION-PATH", "extension payload path is unsafe")

    @staticmethod
    def _directory_name(extension_id: str, version: str) -> str:
        for value in (extension_id, version):
            if "/" in value or "\\" in value or value.startswith(".") or "@" in value:
                raise OAKError("OAK-EXTENSION-IDENTITY", "extension identity is unsafe")
        return f"{extension_id}@{version}"
