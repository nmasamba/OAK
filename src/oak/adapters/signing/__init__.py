# SPDX-License-Identifier: Apache-2.0
"""Local signing adapters."""

from oak.adapters.signing.local_ed25519 import LocalEd25519Signer, initialize_trust_directory

__all__ = ["LocalEd25519Signer", "initialize_trust_directory"]
