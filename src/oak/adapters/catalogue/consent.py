# SPDX-License-Identifier: Apache-2.0
"""The consent text a user reads before a native installation (ADR-0019)."""

from pathlib import Path
from typing import Any

from oak.adapters.catalogue.local_catalogue import read_bounded_catalogue_document
from oak.contracts import ContractValidationError, SchemaRegistry
from oak.domain import OAKError

NATIVE_CONSENT_PATH = Path("consent") / "native-installation.yaml"


class LocalConsentText:
    """Reads the bundled consent text, bounded like every catalogue document, then validated.

    Called each time a plan is compiled or a consent recorded, so both read the text that
    is installed now: an approval names that text by digest.
    """

    def __init__(self, root: Path, registry: SchemaRegistry) -> None:
        self._root = root
        self._registry = registry

    def __call__(self) -> dict[str, Any]:
        directory = self._root / NATIVE_CONSENT_PATH.parent
        if directory.is_symlink() or not directory.is_dir():
            raise OAKError(
                "OAK-NATIVE-CONSENT", "the native-installation consent text is not installed"
            )
        try:
            document = read_bounded_catalogue_document(self._root / NATIVE_CONSENT_PATH)
            self._registry.validate("native-consent.schema.json", document)
        except (ValueError, ContractValidationError) as error:
            raise OAKError(
                "OAK-NATIVE-CONSENT", "the native-installation consent text is not valid"
            ) from error
        return document
