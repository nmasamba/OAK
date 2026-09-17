# SPDX-License-Identifier: Apache-2.0
"""Local credential storage for the optional model provider.

Nothing in this package is reachable from the deterministic journey. Credentials are
user-supplied provider keys and the per-process capability token; they live in the
operating-system keychain or in owner-only files, and they never enter canonical state.
"""

from oak.adapters.credentials.api_token import (
    TOKEN_FILE_NAME,
    read_api_token,
    write_api_token,
)
from oak.adapters.credentials.configuration_store import ModelConfigurationFileStore
from oak.adapters.credentials.environment_reference import EnvironmentCredentialReference
from oak.adapters.credentials.file_store import FileCredentialStore
from oak.adapters.credentials.keychain_store import KeychainCredentialStore

__all__ = [
    "TOKEN_FILE_NAME",
    "EnvironmentCredentialReference",
    "FileCredentialStore",
    "KeychainCredentialStore",
    "ModelConfigurationFileStore",
    "read_api_token",
    "write_api_token",
]
