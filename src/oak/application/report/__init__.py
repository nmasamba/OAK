# SPDX-License-Identifier: Apache-2.0
"""The architecture report: composed from a case's records, recorded beside it.

The composer is pure; recording it (`ReportService`) revises the case at its own status
and authorizes nothing. Rendering it to a PDF happens behind `ReportRendererPort`.
"""

from oak.application.report.composer import (
    COMPOSER_VERSION,
    INSTALL_STEPS,
    MAIN_SECTIONS,
    NOTE_LABEL,
    RECORDABLE_STATUSES,
    Narrative,
    ReportRecords,
    narrator_facts,
    report_document,
)

__all__ = [
    "COMPOSER_VERSION",
    "INSTALL_STEPS",
    "MAIN_SECTIONS",
    "NOTE_LABEL",
    "RECORDABLE_STATUSES",
    "Narrative",
    "ReportRecords",
    "narrator_facts",
    "report_document",
]
