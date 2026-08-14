# SPDX-License-Identifier: Apache-2.0
"""OAK-S0-005 shared application query tests."""

from oak.application import SystemInformationService
from oak.domain import SystemInformation


class FailingProbe:
    def is_ready(self) -> bool:
        return False


def test_information_is_returned_without_transport_logic() -> None:
    expected = SystemInformation(
        name="OAK Community",
        version="1.2.3",
        commit="abc123",
        schema_versions=("0.4.0",),
    )

    service = SystemInformationService(expected)

    assert service.get_information() is expected
    assert service.get_readiness().status == "ready"


def test_failed_required_probe_makes_service_not_ready() -> None:
    information = SystemInformation("OAK Community", "1.2.3", "abc123", ("0.4.0",))

    service = SystemInformationService(information, readiness_probes=(FailingProbe(),))

    assert service.get_readiness().status == "not_ready"
