# SPDX-License-Identifier: Apache-2.0
"""Shared read-only service used by CLI and HTTP interfaces."""

from collections.abc import Sequence

from oak.domain.system_information import Readiness, SystemInformation
from oak.ports.readiness import ReadinessProbe


class SystemInformationService:
    """Return immutable build metadata and coarse process readiness."""

    def __init__(
        self,
        information: SystemInformation,
        readiness_probes: Sequence[ReadinessProbe] = (),
    ) -> None:
        self._information = information
        self._readiness_probes = tuple(readiness_probes)

    def get_information(self) -> SystemInformation:
        return self._information

    def get_readiness(self) -> Readiness:
        ready = all(probe.is_ready() for probe in self._readiness_probes)
        return Readiness(status="ready" if ready else "not_ready")
