# SPDX-License-Identifier: Apache-2.0
"""Composition root shared by local interfaces."""

import os
from pathlib import Path

from oak import __version__
from oak.adapters.intake import LocalBriefIntake
from oak.adapters.persistence import FileWorkspaceRepository
from oak.application import DesignCaseService, SystemInformationService
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry
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


def canonical_schema_directory() -> Path:
    """Locate canonical schemas in an installed wheel or source checkout."""

    configured = os.getenv("OAK_SCHEMA_DIRECTORY")
    candidates = [
        Path(configured) if configured else None,
        Path(__file__).resolve().parent / "canonical_schemas",
        Path(__file__).resolve().parents[2] / "schemas",
    ]
    for candidate in candidates:
        if candidate is not None and (candidate / "common.schema.json").is_file():
            return candidate
    raise RuntimeError("canonical OAK schemas are not installed")


def create_design_case_service(workspace: Path) -> DesignCaseService:
    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    repository = FileWorkspaceRepository(workspace, registry)
    return DesignCaseService(
        repository,
        LocalBriefIntake(),
        DeterministicBriefInterpreter(),
        registry,
    )
