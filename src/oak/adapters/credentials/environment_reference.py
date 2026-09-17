# SPDX-License-Identifier: Apache-2.0
"""Credential source that stores nothing: the value lives in a documented variable."""

from __future__ import annotations

import os

from oak.domain import ENVIRONMENT_VARIABLES, OAKError, SecretValue


class EnvironmentCredentialReference:
    """Reads `OAK_MODEL_KEY_<FAMILY>` at call time; never persists a value."""

    source = "env"

    def location(self) -> str:
        return "process environment"

    @staticmethod
    def variable_for(family: str) -> str:
        try:
            return ENVIRONMENT_VARIABLES[family]
        except KeyError as error:
            raise OAKError(
                "OAK-MODEL-CREDENTIAL-SOURCE",
                "this family has no documented environment variable; store the key in the "
                "keychain or file backend instead",
            ) from error

    def set(self, family: str, secret: SecretValue) -> None:
        """Selecting the environment source only checks the variable is present."""

        variable = self.variable_for(family)
        current = os.environ.get(variable)
        if current is None or not current.strip():
            raise OAKError(
                "OAK-MODEL-KEY-MISSING",
                f"{variable} is not set in this process's environment; export it before "
                "choosing the environment source",
            )
        if secret.reveal() and secret.reveal() != current.strip():
            raise OAKError(
                "OAK-MODEL-KEY-INPUT",
                f"the environment source reads {variable}; do not also pass a key value",
            )

    def get(self, family: str) -> SecretValue | None:
        value = os.environ.get(self.variable_for(family))
        if value is None or not value.strip():
            return None
        return SecretValue(value.strip())

    def delete(self, family: str) -> bool:
        return False
