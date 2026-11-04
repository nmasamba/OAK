# SPDX-License-Identifier: Apache-2.0
"""OAK-V1-043: a hardware proposal's id fits the identifier limit, whatever the case id."""

import re

from oak.application.design_case import DesignCaseService

IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9._:/-]*$")


def test_a_long_case_id_still_gives_a_valid_proposal_id() -> None:
    for case_id in ("design-case.public-manual-qa", "design-case." + "a" * 148):
        proposal_id = DesignCaseService._hardware_proposal_id(
            case_id, "2026-11-02T12:00:00.123456Z", "sha256:" + "0" * 64
        )
        assert 3 <= len(proposal_id) <= 160
        assert IDENTIFIER.fullmatch(proposal_id)
        assert proposal_id.startswith("hardware-proposal.")
