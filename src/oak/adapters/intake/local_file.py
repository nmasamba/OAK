# SPDX-License-Identifier: Apache-2.0
"""Bounded local brief reader for YAML, JSON, Markdown, and text."""

import math
import os
import re
import stat
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from oak.contracts import load_json_document, load_yaml_document
from oak.domain import OAKError
from oak.domain.intake import IngestedBrief

MAXIMUM_BRIEF_BYTES = 262_144
MAXIMUM_STRUCTURE_DEPTH = 20
MAXIMUM_STRUCTURE_NODES = 5_000
SUPPORTED_FORMATS = {
    ".yaml": ("yaml", "application/yaml"),
    ".yml": ("yaml", "application/yaml"),
    ".json": ("json", "application/json"),
    ".md": ("markdown", "text/markdown"),
    ".markdown": ("markdown", "text/markdown"),
    ".txt": ("text", "text/plain"),
}
SAFE_ID = re.compile(r"[^a-z0-9]+")


class LocalBriefIntake:
    def read(self, path: Path) -> IngestedBrief:
        absolute = path.absolute()
        if absolute.is_symlink() or not absolute.is_file():
            raise OAKError("OAK-INTAKE-UNSAFE-PATH", "brief must be a regular non-symlink file")
        raw = self._read_bounded_regular_file(absolute)
        return self.read_content(original_name=absolute.name, content=raw)

    def read_content(self, *, original_name: str, content: bytes) -> IngestedBrief:
        if (
            not original_name
            or Path(original_name).name != original_name
            or "/" in original_name
            or "\\" in original_name
        ):
            raise OAKError("OAK-INTAKE-UNSAFE-PATH", "brief filename must not contain a path")
        if unicodedata.normalize("NFC", original_name) != original_name:
            raise OAKError("OAK-INTAKE-UNICODE-PATH", "brief filename must use NFC Unicode")
        format_details = SUPPORTED_FORMATS.get(Path(original_name).suffix.lower())
        if format_details is None:
            raise OAKError("OAK-INTAKE-TYPE", "brief file type is not supported")
        if not content or len(content) > MAXIMUM_BRIEF_BYTES:
            raise OAKError(
                "OAK-INTAKE-SIZE",
                f"brief must contain 1 to {MAXIMUM_BRIEF_BYTES} bytes",
            )
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise OAKError("OAK-INTAKE-ENCODING", "brief must be valid UTF-8") from error
        self._reject_control_characters(text)
        normalized = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
        normalized_bytes = normalized.encode("utf-8")
        format_name, media_type = format_details
        structured = self._structured_document(format_name, normalized)
        brief_id, version, title = self._identity(Path(original_name), normalized, structured)
        return IngestedBrief(
            id=brief_id,
            version=version,
            title=title,
            format=format_name,
            media_type=media_type,
            original_name=original_name,
            content=normalized_bytes,
            structured=structured,
        )

    @staticmethod
    def _read_bounded_regular_file(path: Path) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            if path.is_symlink():
                raise OAKError(
                    "OAK-INTAKE-UNSAFE-PATH", "brief must be a regular non-symlink file"
                ) from error
            raise OAKError("OAK-INTAKE-READ", "brief could not be read") from error
        with os.fdopen(descriptor, "rb") as stream:
            details = os.fstat(stream.fileno())
            if not stat.S_ISREG(details.st_mode):
                raise OAKError("OAK-INTAKE-UNSAFE-PATH", "brief must be a regular non-symlink file")
            if details.st_size < 1 or details.st_size > MAXIMUM_BRIEF_BYTES:
                raise OAKError(
                    "OAK-INTAKE-SIZE",
                    f"brief must contain 1 to {MAXIMUM_BRIEF_BYTES} bytes",
                )
            content = stream.read(MAXIMUM_BRIEF_BYTES + 1)
        if not content or len(content) > MAXIMUM_BRIEF_BYTES:
            raise OAKError(
                "OAK-INTAKE-SIZE",
                f"brief must contain 1 to {MAXIMUM_BRIEF_BYTES} bytes",
            )
        return content

    def _structured_document(self, format_name: str, text: str) -> dict[str, Any] | None:
        if format_name not in {"yaml", "json"}:
            return None
        try:
            if format_name == "yaml":
                tokens = tuple(yaml.scan(text))
                if any(
                    isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken))
                    for token in tokens
                ):
                    raise OAKError("OAK-INTAKE-ALIAS", "YAML aliases and anchors are not accepted")
                document = load_yaml_document(text)
            else:
                document = load_json_document(text)
        except OAKError:
            raise
        except (ValueError, yaml.YAMLError) as error:
            raise OAKError("OAK-INTAKE-MALFORMED", "structured brief is malformed") from error
        self._validate_json_shape(document)
        return document

    @staticmethod
    def _identity(path: Path, text: str, structured: dict[str, Any] | None) -> tuple[str, str, str]:
        if structured is not None:
            brief_id = structured.get("id")
            version = structured.get("brief_version")
            title = structured.get("title")
            if not all(isinstance(value, str) and value for value in (brief_id, version, title)):
                raise OAKError(
                    "OAK-INTAKE-IDENTITY",
                    "structured brief requires string id, brief_version, and title",
                )
            return str(brief_id), str(version), str(title)
        stem = SAFE_ID.sub("-", path.stem.casefold()).strip("-") or "brief"
        first_line = next((line.strip("# ") for line in text.splitlines() if line.strip()), stem)
        return f"brief.{stem}", "0.1.0", first_line[:240]

    @staticmethod
    def _reject_control_characters(text: str) -> None:
        for character in text:
            if character in "\t\n\r":
                continue
            if unicodedata.category(character).startswith("C"):
                raise OAKError(
                    "OAK-INTAKE-UNICODE-CONTROL",
                    "brief contains a prohibited control or formatting character",
                )

    @staticmethod
    def _validate_json_shape(document: dict[str, Any]) -> None:
        nodes = 0
        active: set[int] = set()

        def visit(value: Any, depth: int) -> None:
            nonlocal nodes
            nodes += 1
            if nodes > MAXIMUM_STRUCTURE_NODES or depth > MAXIMUM_STRUCTURE_DEPTH:
                raise OAKError("OAK-INTAKE-COMPLEXITY", "structured brief is too complex")
            if isinstance(value, dict):
                identity = id(value)
                if identity in active:
                    raise OAKError("OAK-INTAKE-CYCLE", "structured brief contains a cycle")
                active.add(identity)
                for key, child in value.items():
                    if not isinstance(key, str):
                        raise OAKError(
                            "OAK-INTAKE-KEY-TYPE", "structured brief keys must be strings"
                        )
                    visit(child, depth + 1)
                active.remove(identity)
                return
            if isinstance(value, list):
                identity = id(value)
                if identity in active:
                    raise OAKError("OAK-INTAKE-CYCLE", "structured brief contains a cycle")
                active.add(identity)
                for child in value:
                    visit(child, depth + 1)
                active.remove(identity)
                return
            if isinstance(value, float) and not math.isfinite(value):
                raise OAKError("OAK-INTAKE-NUMBER", "structured brief numbers must be finite")
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise OAKError(
                    "OAK-INTAKE-VALUE-TYPE", "structured brief contains a non-JSON value"
                )

        visit(document, 0)
