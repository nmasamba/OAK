# SPDX-License-Identifier: Apache-2.0
"""Words OAK does not put in front of a reader, wherever the words come from.

``ASSURANCE_PATTERNS`` is vocabulary that asserts assurance OAK Community does not have;
`tools/check_repository.py` refuses it in the documentation, the report guard refuses it
in every string of a composed report, and a note a model proposes for a report is dropped
when it matches. The edition word and the raw variant ids are refused in the report for
the reason the web refuses them (Sprint 12 copy rules): a reader sees labels, never ids.
"""

import re

ASSURANCE_PATTERNS = (
    re.compile(r"\bproduction[\s-]ready\b", re.IGNORECASE),
    re.compile(r"\benterprise[\s-]grade\b", re.IGNORECASE),
    re.compile(r"\bbattle[\s-]tested\b", re.IGNORECASE),
    re.compile(r"\b(?:bank|military)[\s-]grade\b", re.IGNORECASE),
    re.compile(r"\bunhackable\b", re.IGNORECASE),
    re.compile(r"\bsecure[\s-]by[\s-]default\b", re.IGNORECASE),
    re.compile(r"\b(?:SOC[\s-]?2|ISO[\s-]?27001|FedRAMP|HIPAA[\s-]compliant)\b"),
    re.compile(r"\bpenetration[\s-]test", re.IGNORECASE),
    re.compile(r"\b(?:externally|independently|third[\s-]party)[\s-]audited\b", re.IGNORECASE),
    re.compile(r"\bthird[\s-]party\s+(?:audit|assurance|review)\b", re.IGNORECASE),
    re.compile(r"\bcertified\b", re.IGNORECASE),
    re.compile(r"\bformally[\s-]verified\b", re.IGNORECASE),
)

EDITION_WORD = re.compile(r"enterprise", re.IGNORECASE)
RAW_VARIANT_IDS = (
    "simpler_baseline",
    "minimum_sufficient",
    "balanced_enterprise",
    "high_assurance_sovereign",
)


def forbidden_words(text: str) -> list[str]:
    """Every assurance claim, edition word and raw variant id in ``text``, in order found."""

    found: list[str] = []
    for pattern in ASSURANCE_PATTERNS:
        found.extend(match.group(0) for match in pattern.finditer(text))
    found.extend(match.group(0) for match in EDITION_WORD.finditer(text))
    found.extend(identifier for identifier in RAW_VARIANT_IDS if identifier in text)
    return found
