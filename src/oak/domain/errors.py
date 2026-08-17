# SPDX-License-Identifier: Apache-2.0
"""Stable domain/application error values."""

from dataclasses import dataclass


@dataclass(slots=True)
class OAKError(Exception):
    """A safe error that interfaces may render without exposing internals."""

    code: str
    message: str
    retriable: bool = False

    def __str__(self) -> str:
        return self.message
