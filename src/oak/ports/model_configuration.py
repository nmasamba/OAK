# SPDX-License-Identifier: Apache-2.0
"""Ports for the optional model provider's credentials and selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from oak.domain import SecretValue


@dataclass(frozen=True, slots=True)
class CredentialStatus:
    """What may be said about a stored credential: never its value."""

    family: str
    configured: bool
    source: str | None
    fingerprint: str | None
    length: int | None

    def to_document(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "configured": self.configured,
            "source": self.source,
            "fingerprint": self.fingerprint,
            "length": self.length,
        }


class CredentialStorePort(Protocol):
    """One backend (keychain, owner-only file, or environment reference) for keys."""

    source: str

    def set(self, family: str, secret: SecretValue) -> None: ...

    def get(self, family: str) -> SecretValue | None: ...

    def delete(self, family: str) -> bool: ...

    def location(self) -> str: ...


class ModelConfigurationStorePort(Protocol):
    """Persist the non-secret selection document; it can never hold a key."""

    def load(self) -> dict[str, Any] | None: ...

    def save(self, document: dict[str, Any]) -> None: ...

    def location(self) -> str: ...
