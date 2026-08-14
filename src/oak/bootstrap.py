# SPDX-License-Identifier: Apache-2.0
"""Composition root for read-only Sprint 0 application services."""

import os

from oak import __version__
from oak.application import SystemInformationService
from oak.domain import SystemInformation

SUPPORTED_SCHEMA_VERSIONS = ("0.3.0", "0.4.0")


def create_system_information_service() -> SystemInformationService:
    """Construct the shared service without a transport-specific dependency."""

    commit = os.getenv("OAK_COMMIT", "unknown")
    information = SystemInformation(
        name="OAK Community",
        version=__version__,
        commit=commit,
        schema_versions=SUPPORTED_SCHEMA_VERSIONS,
    )
    return SystemInformationService(information)
