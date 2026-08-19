# SPDX-License-Identifier: Apache-2.0
"""Control-plane signing port; verification lives in the runner trust domain."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class SignerIdentity:
    """Public identity of one signing role; never contains private material."""

    role: str
    key_id: str
    algorithm: str
    public_key_base64: str
    trust_level: str
    created_at: str

    def to_document(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "key_id": self.key_id,
            "algorithm": self.algorithm,
            "public_key_base64": self.public_key_base64,
            "trust_level": self.trust_level,
            "created_at": self.created_at,
        }


class SigningPort(Protocol):
    def identity(self) -> SignerIdentity: ...

    def sign(self, message: bytes) -> str: ...
