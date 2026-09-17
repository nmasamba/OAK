# SPDX-License-Identifier: Apache-2.0
"""Model-provider configuration: which family, which model, and where the key lives.

The service owns the non-secret configuration document and delegates credential storage
to whichever backend the user chose. It never logs, echoes or persists a key; the only
values it returns about a credential are whether one is configured, which backend holds
it, a salted fingerprint and its length. Discovery (contacting a provider's catalogue) is
attached in a later milestone through `discoverer`; without one, `discover` reports the
pinned defaults and says so.
"""

from __future__ import annotations

import copy
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from oak.domain import (
    DEFAULT_FAMILY,
    FAMILY_BY_ID,
    FAMILY_IDS,
    FamilyDescriptor,
    OAKError,
    SecretValue,
)
from oak.ports import CredentialStatus, CredentialStorePort, ModelConfigurationStorePort

CONFIGURATION_ID = "model-configuration.local"
MINIMUM_KEY_CHARACTERS = 16
MAXIMUM_KEY_CHARACTERS = 512
CREDENTIAL_SOURCES = ("keychain", "file", "env")
INTERPRETERS = ("model", "deterministic")

Discoverer = Callable[[str, dict[str, Any] | None], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ModelSelection:
    family: str
    model_id: str
    provider_route: str | None
    default_interpreter: str
    data_use_acknowledged: bool

    def to_document(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "model_id": self.model_id,
            "provider_route": self.provider_route,
            "default_interpreter": self.default_interpreter,
            "data_use_acknowledged": self.data_use_acknowledged,
        }


def validate_key_input(value: str) -> SecretValue:
    """Bound and sanitise a key typed or piped by the user; no family prefix rules."""

    candidate = value
    if candidate.endswith("\n"):
        candidate = candidate[:-1]
    if candidate.endswith("\r"):
        candidate = candidate[:-1]
    if not MINIMUM_KEY_CHARACTERS <= len(candidate) <= MAXIMUM_KEY_CHARACTERS:
        raise OAKError(
            "OAK-MODEL-KEY-INPUT",
            f"a provider key must be between {MINIMUM_KEY_CHARACTERS} and "
            f"{MAXIMUM_KEY_CHARACTERS} characters",
        )
    for character in candidate:
        if not (0x21 <= ord(character) <= 0x7E) or unicodedata.category(character).startswith("C"):
            raise OAKError(
                "OAK-MODEL-KEY-INPUT",
                "a provider key must be printable ASCII with no spaces or control characters",
            )
    return SecretValue(candidate)


class ModelConfigurationService:
    def __init__(
        self,
        configuration: ModelConfigurationStorePort,
        credentials: Mapping[str, CredentialStorePort],
        *,
        clock: Callable[[], str],
        families: Mapping[str, FamilyDescriptor] = FAMILY_BY_ID,
        discoverer: Discoverer | None = None,
        token_reader: Callable[[], str | None] | None = None,
        credentials_location: str | None = None,
        under_compose: bool = False,
        discovery_cache_seconds: int = 21_600,
    ) -> None:
        self._configuration = configuration
        self._credentials = dict(credentials)
        self._clock = clock
        self._families = dict(families)
        self._discoverer = discoverer
        self._discovery_cache_seconds = discovery_cache_seconds
        self._token_reader = token_reader
        self._credentials_location = credentials_location
        self._under_compose = under_compose

    # ----- reads -------------------------------------------------------------------

    def families(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "family": descriptor.family,
                "display_name": descriptor.display_name,
                "licence_class": descriptor.licence_class,
                "credential_required": descriptor.credential_required,
                "environment_variable": descriptor.environment_variable,
                "key_hint": descriptor.key_hint,
                "data_use_note": descriptor.data_use_note,
                "token_help_url": descriptor.token_help_url,
                "default": descriptor.family == DEFAULT_FAMILY,
            }
            for descriptor in self._families.values()
        )

    def selection(self) -> ModelSelection | None:
        document = self._document()
        selected = document["selection"]
        if selected is None:
            return None
        return ModelSelection(
            family=str(selected["family"]),
            model_id=str(selected["model_id"]),
            provider_route=selected.get("provider_route"),
            default_interpreter=str(selected["default_interpreter"]),
            data_use_acknowledged=bool(selected["data_use_acknowledged"]),
        )

    def credential_status(self, family: str) -> CredentialStatus:
        self._descriptor(family)
        source = self._document()["credential_sources"].get(family, "none")
        if source == "none":
            return CredentialStatus(
                family=family, configured=False, source=None, fingerprint=None, length=None
            )
        secret = self._credentials[source].get(family)
        if secret is None:
            return CredentialStatus(
                family=family, configured=False, source=source, fingerprint=None, length=None
            )
        return CredentialStatus(
            family=family,
            configured=True,
            source=source,
            fingerprint=self._fingerprint(secret),
            length=len(secret),
        )

    def credential_for(self, family: str) -> SecretValue | None:
        """The stored key for the configured source only; never a guess across backends."""

        source = self._document()["credential_sources"].get(family, "none")
        if source == "none":
            return None
        return self._credentials[source].get(family)

    def status(self) -> dict[str, Any]:
        document = self._document()
        selection = self.selection()
        credentials = {
            family: self.credential_status(family).to_document() for family in FAMILY_IDS
        }
        configured = selection is not None and (
            credentials[selection.family]["configured"]
            or not self._descriptor(selection.family).credential_required
        )
        now = self._clock()
        discovery = {
            family: {
                "fetched_at": snapshot["fetched_at"],
                "source": snapshot["source"],
                "recommended": snapshot["recommended"],
                "model_count": len(snapshot["models"]),
                "stale": self._is_stale(str(snapshot["fetched_at"]), now),
            }
            for family, snapshot in document["discovery"].items()
        }
        return {
            "configured": configured,
            "selection": selection.to_document() if selection is not None else None,
            "provider_policy": document["provider_policy"],
            "credentials": credentials,
            "discovery": discovery,
            "stores": {
                "credentials": self._credentials_location,
                "configuration": self._configuration.location(),
                "under_compose": self._under_compose,
            },
            "token_present": bool(self._token_reader()) if self._token_reader else False,
        }

    def discovery_snapshot(self, family: str) -> dict[str, Any] | None:
        snapshot = self._document()["discovery"].get(family)
        return copy.deepcopy(snapshot) if snapshot is not None else None

    def token(self) -> str | None:
        return self._token_reader() if self._token_reader else None

    # ----- writes ------------------------------------------------------------------

    def set_key(self, family: str, secret: SecretValue, *, source: str) -> CredentialStatus:
        descriptor = self._descriptor(family)
        if source not in CREDENTIAL_SOURCES:
            raise OAKError(
                "OAK-MODEL-CREDENTIAL-SOURCE",
                "the credential source must be keychain, file, or env",
            )
        if source == "env" and descriptor.environment_variable is None:
            raise OAKError(
                "OAK-MODEL-CREDENTIAL-SOURCE",
                f"the {family} family has no documented environment variable",
            )
        store = self._credentials[source]
        store.set(family, secret)
        document = self._document()
        previous = document["credential_sources"].get(family, "none")
        if previous not in {"none", source}:
            # One key per family: a key left behind in another backend would be a second copy
            # nobody remembers.
            self._credentials[previous].delete(family)
        document["credential_sources"][family] = source
        self._configuration.save(document)
        return self.credential_status(family)

    def remove_key(self, family: str) -> bool:
        self._descriptor(family)
        document = self._document()
        source = document["credential_sources"].get(family, "none")
        removed = False
        for candidate in self._credentials.values():
            if candidate.source == "env":
                continue
            try:
                removed = candidate.delete(family) or removed
            except OAKError as error:
                # A backend that is not available here (no keychain in a container or a
                # headless session) cannot be holding a copy; the configured source is
                # what matters and is cleared below.
                if not error.code.startswith("OAK-MODEL-KEYCHAIN-") or source == candidate.source:
                    raise
        if source != "none":
            document["credential_sources"][family] = "none"
            self._configuration.save(document)
            removed = True
        return removed

    def select(
        self,
        family: str,
        model_id: str,
        *,
        provider_route: str | None = None,
        default_interpreter: str = "model",
        acknowledge_data_use: bool = False,
    ) -> ModelSelection:
        descriptor = self._descriptor(family)
        if default_interpreter not in INTERPRETERS:
            raise OAKError(
                "OAK-MODEL-INTERPRETER", "default_interpreter must be model or deterministic"
            )
        if not model_id or len(model_id) > 256:
            raise OAKError("OAK-MODEL-ID", "a model identifier must be 1 to 256 characters")
        snapshot = self.discovery_snapshot(family)
        data_use = self._data_use(snapshot, model_id)
        if data_use == "trains_on_inputs" and not acknowledge_data_use:
            raise OAKError(
                "OAK-MODEL-DATA-USE",
                f"{model_id} permits the provider to train on your prompts; repeat the "
                "selection with --acknowledge-data-use if that is acceptable",
            )
        if descriptor.credential_required and not self.credential_status(family).configured:
            raise OAKError(
                "OAK-MODEL-KEY-MISSING",
                f"no key is stored for the {family} family; run "
                f"`oak models set-key {family}` first",
            )
        document = self._document()
        document["selection"] = {
            "family": family,
            "model_id": model_id,
            "provider_route": provider_route,
            "default_interpreter": default_interpreter,
            "data_use_acknowledged": acknowledge_data_use,
            "selected_at": self._clock(),
        }
        self._configuration.save(document)
        selection = self.selection()
        assert selection is not None
        return selection

    def clear_selection(self) -> None:
        document = self._document()
        document["selection"] = None
        self._configuration.save(document)

    def set_provider_policy(self, policy: str) -> None:
        if policy not in {"cheapest", "fastest"}:
            raise OAKError("OAK-MODEL-POLICY", "provider policy must be cheapest or fastest")
        document = self._document()
        document["provider_policy"] = policy
        self._configuration.save(document)

    def discover(self, family: str) -> dict[str, Any]:
        """Refresh the catalogue snapshot for one family. Explicit only; never implicit."""

        self._descriptor(family)
        if self._discoverer is None:
            raise OAKError(
                "OAK-MODEL-DISCOVERY-UNAVAILABLE",
                "model discovery is not available in this build; select a model identifier "
                "directly",
            )
        snapshot = self._discoverer(family, self.discovery_snapshot(family))
        document = self._document()
        document["discovery"][family] = snapshot
        self._configuration.save(document)
        return copy.deepcopy(snapshot)

    # ----- helpers -----------------------------------------------------------------

    def _document(self) -> dict[str, Any]:
        loaded = self._configuration.load()
        if loaded is not None:
            return loaded
        return {
            "schema_version": "0.1.0",
            "id": CONFIGURATION_ID,
            "selection": None,
            "credential_sources": {},
            "provider_policy": "cheapest",
            "discovery": {},
            "extensions": {},
        }

    def _descriptor(self, family: str) -> FamilyDescriptor:
        try:
            return self._families[family]
        except KeyError as error:
            raise OAKError(
                "OAK-MODEL-FAMILY-UNKNOWN",
                f"unknown model family; choose one of {', '.join(FAMILY_IDS)}",
            ) from error

    def _fingerprint(self, secret: SecretValue) -> str | None:
        store = self._credentials.get("file")
        fingerprint = getattr(store, "fingerprint", None)
        if fingerprint is None:
            return None
        result: str = fingerprint(secret)
        return result

    def _is_stale(self, fetched_at: str, now: str) -> bool:
        """Whether a snapshot is older than the configured cache window.

        An unparsable or future timestamp reads as stale: suggesting a refresh of a good
        snapshot is a smaller error than presenting a bad one as current.
        """

        try:
            taken = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            current = datetime.fromisoformat(now.replace("Z", "+00:00"))
        except ValueError:
            return True
        age = (current - taken).total_seconds()
        return age < 0 or age > self._discovery_cache_seconds

    @staticmethod
    def _data_use(snapshot: dict[str, Any] | None, model_id: str) -> str:
        if snapshot is None:
            return "unknown"
        for model in snapshot.get("models", []):
            if model.get("id") == model_id:
                return str(model.get("data_use", "unknown"))
        return "unknown"
