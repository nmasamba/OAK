# SPDX-License-Identifier: Apache-2.0
"""OS credential-store backend through the optional `keyring` extra.

`keyring` is imported lazily so the deterministic journey never loads it and so an
installation without the `keychain` extra fails with a stable code rather than an import
error. Two refusals are deliberate: no usable backend (headless hosts, containers) is
reported, never silently downgraded to a file; and the `keyrings.alt` plaintext backends
are refused outright because they would store the key base64-encoded on disk while
claiming to be a keychain.
"""

from __future__ import annotations

import importlib
from typing import Any

from oak.domain import OAKError, SecretValue

SERVICE_NAME = "oak-community"
UNAVAILABLE_CODE = "OAK-MODEL-KEYCHAIN-UNAVAILABLE"
UNSAFE_CODE = "OAK-MODEL-KEYCHAIN-UNSAFE"


class KeychainCredentialStore:
    source = "keychain"

    def __init__(self, module_name: str = "keyring") -> None:
        self._module_name = module_name

    def location(self) -> str:
        return f"operating-system keychain (service {SERVICE_NAME!r})"

    def _keyring(self) -> Any:
        try:
            module = importlib.import_module(self._module_name)
        except ImportError as error:
            raise OAKError(
                UNAVAILABLE_CODE,
                "the OS keychain backend is not installed; install the `keychain` extra "
                "(`oak-community[keychain]`) or use `--store file`",
            ) from error
        try:
            backend = module.get_keyring()
        except Exception as error:  # keyring raises its own error family here
            raise OAKError(
                UNAVAILABLE_CODE,
                "no OS keychain is available to this process (headless session or "
                "container); use `--store file`",
            ) from error
        backend_module = str(type(backend).__module__)
        if backend_module.startswith("keyrings.alt") or backend_module.endswith(".fail"):
            code = UNSAFE_CODE if backend_module.startswith("keyrings.alt") else UNAVAILABLE_CODE
            raise OAKError(
                code,
                (
                    "the selected keyring backend stores secrets in plain text and is refused; "
                    "use `--store file`, which at least enforces owner-only permissions"
                    if code == UNSAFE_CODE
                    else "no OS keychain is available to this process; use `--store file`"
                ),
            )
        return module

    def set(self, family: str, secret: SecretValue) -> None:
        module = self._keyring()
        try:
            module.set_password(SERVICE_NAME, family, secret.reveal())
        except Exception as error:
            raise OAKError(
                UNAVAILABLE_CODE, "the OS keychain refused to store the credential"
            ) from error

    def get(self, family: str) -> SecretValue | None:
        module = self._keyring()
        try:
            value = module.get_password(SERVICE_NAME, family)
        except Exception as error:
            raise OAKError(
                UNAVAILABLE_CODE, "the OS keychain refused to read the credential"
            ) from error
        if not value:
            return None
        return SecretValue(str(value).strip())

    def delete(self, family: str) -> bool:
        module = self._keyring()
        try:
            module.delete_password(SERVICE_NAME, family)
        except Exception:
            return False
        return True
