# SPDX-License-Identifier: Apache-2.0
"""Immutable content-addressed artifact values."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any


def canonical_json_bytes(document: dict[str, Any]) -> bytes:
    """Serialize a canonical document without presentation-only whitespace."""

    return json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def content_digest(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    id: str
    version: str
    digest: str
    media_type: str
    uri: str | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "digest": self.digest,
            "uri": self.uri,
            "media_type": self.media_type,
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> "ArtifactReference":
        return cls(
            id=str(document["id"]),
            version=str(document["version"]),
            digest=str(document["digest"]),
            media_type=str(document["media_type"]),
            uri=(str(document["uri"]) if document.get("uri") is not None else None),
        )


@dataclass(frozen=True, slots=True)
class Artifact:
    id: str
    version: str
    kind: str
    media_type: str
    content: bytes

    @property
    def digest(self) -> str:
        return content_digest(self.content)

    @property
    def reference(self) -> ArtifactReference:
        return ArtifactReference(
            id=self.id,
            version=self.version,
            digest=self.digest,
            media_type=self.media_type,
        )

    def index_document(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "digest": self.digest,
            "media_type": self.media_type,
            "kind": self.kind,
            "size_bytes": len(self.content),
        }


def json_artifact(
    *,
    artifact_id: str,
    version: str,
    kind: str,
    media_type: str,
    document: dict[str, Any],
) -> Artifact:
    return Artifact(
        id=artifact_id,
        version=version,
        kind=kind,
        media_type=media_type,
        content=canonical_json_bytes(document),
    )
