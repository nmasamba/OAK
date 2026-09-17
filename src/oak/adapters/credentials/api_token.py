# SPDX-License-Identifier: Apache-2.0
"""The per-process capability token that guards model configuration over REST.

`oak-api` and `oak serve` mint a fresh random token every time they start and write it,
owner-only, next to the provider credentials. A browser page or a local process that can
reach the loopback port must present it to store or remove a provider key, to run model
discovery, to change the selection, or to interpret a brief with the configured model. It
is never returned by any endpoint; `oak models token` reads the file for the user.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from oak.adapters.credentials._files import read_private_file, write_private_file

TOKEN_FILE_NAME = "api-token"
TOKEN_FILE_CODE = "OAK-MODEL-TOKEN-FILE"
_TOKEN_BYTES = 32
_MAXIMUM_TOKEN_FILE_BYTES = 256


def write_api_token(directory: Path) -> str:
    """Mint a new token, persist it owner-only, and return it."""

    token = secrets.token_urlsafe(_TOKEN_BYTES)
    write_private_file(directory / TOKEN_FILE_NAME, token.encode("ascii"), code=TOKEN_FILE_CODE)
    return token


def read_api_token(directory: Path) -> str | None:
    """Return the current token, or ``None`` when no server has minted one."""

    content = read_private_file(
        directory / TOKEN_FILE_NAME,
        code=TOKEN_FILE_CODE,
        maximum_bytes=_MAXIMUM_TOKEN_FILE_BYTES,
    )
    if content is None:
        return None
    token = content.decode("ascii", errors="strict").strip()
    return token or None
