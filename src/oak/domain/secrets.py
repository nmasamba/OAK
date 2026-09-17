# SPDX-License-Identifier: Apache-2.0
"""An opaque wrapper for a secret value that cannot render itself by accident."""

from __future__ import annotations

import hmac
from typing import Any

REDACTED = "<redacted>"


class SecretValue:
    """Holds a credential; every textual rendering is ``<redacted>``.

    The only way to obtain the value is `reveal()`, which callers use at the exact point
    the value is put into a request header or a keychain entry. Equality is constant-time,
    pickling is refused, and the value is not exposed through ``vars()`` because the class
    uses slots.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("a secret value must be a string")
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __len__(self) -> int:
        return len(self._value)

    def __repr__(self) -> str:
        return f"SecretValue({REDACTED})"

    def __str__(self) -> str:
        return REDACTED

    def __format__(self, _format_spec: str) -> str:
        return REDACTED

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SecretValue):
            return NotImplemented
        return hmac.compare_digest(self._value.encode("utf-8"), other._value.encode("utf-8"))

    def __hash__(self) -> int:
        raise TypeError("a secret value is not hashable")

    def __reduce__(self) -> Any:
        raise TypeError("a secret value cannot be pickled")

    def __bool__(self) -> bool:
        return bool(self._value)
