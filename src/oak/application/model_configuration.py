# SPDX-License-Identifier: Apache-2.0
"""Model-provider configuration: the stored token, the pinned pairs, and what each mode can do.

The service owns the non-secret configuration document and delegates credential storage
to whichever backend the user chose. It never logs, echoes or persists a key; the only
values it returns about a credential are whether one is configured, which backend holds
it, a salted fingerprint and its length. Discovery (contacting a provider's catalogue) is
attached through `discoverer`; without one, `discover` refuses and says so.

Three interpretation modes exist and are chosen per request, never stored here:
``deterministic`` needs nothing; ``online`` calls one Hugging Face model — the pair the
user pinned, or else the preferred one discovery recorded — with the stored token;
``local`` calls the model the user pinned on the loopback server. ``modes()`` says which of
them can run right now and why not otherwise.
"""

from __future__ import annotations

import copy
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
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
MODES = ("deterministic", "online", "local")
MODE_FAMILIES: Mapping[str, str] = {"online": "huggingface", "local": "local"}
DEFAULT_LOCAL_ENDPOINT = "http://127.0.0.1:11434/v1"

Discoverer = Callable[[str, dict[str, Any] | None], dict[str, Any]]
Verifier = Callable[[str], dict[str, Any]]
VERDICTS = ("accepted", "rejected", "scope_limited", "unreachable", "unverifiable")
DEFINITIVE_VERDICTS = frozenset({"accepted", "rejected", "scope_limited"})
VERIFICATION_METHOD_VALUES = frozenset(
    {"hub_whoami_v2", "models_list", "interpretation", "unknown"}
)
RouteChooser = Callable[[dict[str, Any] | None, str], str | None]


@dataclass(frozen=True, slots=True)
class ModelSelection:
    family: str
    model_id: str
    provider_route: str | None
    selected_at: str

    def to_document(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "model_id": self.model_id,
            "provider_route": self.provider_route,
            "selected_at": self.selected_at,
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
        verifier: Verifier | None = None,
        route_chooser: RouteChooser | None = None,
        token_reader: Callable[[], str | None] | None = None,
        credentials_location: str | None = None,
        local_endpoint: str | None = None,
        under_compose: bool = False,
        discovery_cache_seconds: int = 21_600,
        verification_stale_seconds: int = 86_400,
    ) -> None:
        self._configuration = configuration
        self._credentials = dict(credentials)
        self._clock = clock
        self._families = dict(families)
        self._discoverer = discoverer
        self._verifier = verifier
        self._route_chooser = route_chooser
        self._verification_stale_seconds = verification_stale_seconds
        self._discovery_cache_seconds = discovery_cache_seconds
        self._token_reader = token_reader
        self._credentials_location = credentials_location
        self._local_endpoint = local_endpoint or DEFAULT_LOCAL_ENDPOINT
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

    def selection(self, family: str) -> ModelSelection | None:
        self._descriptor(family)
        selected = self._document()["selection"].get(family)
        if selected is None:
            return None
        return ModelSelection(
            family=family,
            model_id=str(selected["model_id"]),
            provider_route=selected.get("provider_route"),
            selected_at=str(selected["selected_at"]),
        )

    def selections(self) -> dict[str, ModelSelection | None]:
        return {family: self.selection(family) for family in FAMILY_IDS}

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

    def online_pair(self) -> dict[str, Any] | None:
        """The model and route Online AI would call now, or ``None`` with nothing to call.

        The pinned pair wins; otherwise the preferred model discovery recorded, on the route
        the provider policy chooses among its structured-output routes. ``source`` says which.
        """

        document = self._document()
        snapshot = document["discovery"].get("huggingface")
        selection = self.selection("huggingface")
        policy = str(document["provider_policy"])
        if selection is not None:
            listed = self._listed(snapshot, selection.model_id)
            capable = self._capable_routes(listed)
            route = selection.provider_route
            valid, reason = True, None
            if listed is None:
                valid, reason = (
                    False,
                    (
                        f"the catalogue does not list {selection.model_id}; run `oak models "
                        "discover` and pin a listed pair, or `oak models clear huggingface`"
                    ),
                )
            elif not capable:
                valid, reason = (
                    False,
                    (
                        f"{selection.model_id} no longer has a live route that supports structured "
                        "output, which the interpretation needs; pin another pair or run "
                        "`oak models clear huggingface`"
                    ),
                )
            elif route is not None and route not in capable:
                valid, reason = (
                    False,
                    (
                        f"the pinned route {route} for {selection.model_id} no longer "
                        "supports structured output (the catalogue lists "
                        f"{', '.join(capable)}); pin another with `oak models select "
                        f"huggingface {selection.model_id} --provider <route>`, or "
                        "`oak models clear huggingface` for the preferred pair"
                    ),
                )
            elif route is None and self._route_chooser is not None:
                route = self._route_chooser(listed, policy)
            if valid and (route is None or route not in capable):
                valid, reason = (
                    False,
                    (f"no structured-output route could be chosen for {selection.model_id}"),
                )
            return {
                "model_id": selection.model_id,
                "provider_route": route,
                "source": "pinned",
                "resolved_at": selection.selected_at,
                "licence": (listed or {}).get("licence"),
                "output_price_per_million": self._price(listed, route),
                "valid": valid,
                "reason": reason,
                "passed_over": [],
            }
        if snapshot is None or not snapshot.get("models"):
            return None
        # The catalogue's order is the Hub's trending order, so the preferred pair is the
        # first model that can actually be called: ungated and structured-output-capable,
        # which discovery already guaranteed, and reachable inside the request budget, which
        # only the chooser knows. A model whose every route is too slow is passed over rather
        # than offered and then timed out on — the cheapest route of a model is routinely its
        # slowest, and a live run proved the top model unusable at its cheapest route.
        passed_over: list[str] = []
        for listed in snapshot["models"]:
            if not isinstance(listed, dict):
                continue
            model_id = str(listed.get("id", ""))
            capable = self._capable_routes(listed)
            route = self._route_chooser(listed, policy) if self._route_chooser is not None else None
            if route is None or route not in capable:
                passed_over.append(model_id)
                continue
            return {
                "model_id": model_id,
                "provider_route": route,
                "source": "preferred",
                "resolved_at": str(snapshot["fetched_at"]),
                "licence": listed.get("licence"),
                "output_price_per_million": self._price(listed, route),
                "valid": True,
                "reason": None,
                "passed_over": passed_over,
            }
        return {
            "model_id": str(snapshot.get("recommended") or (passed_over[0] if passed_over else "")),
            "provider_route": None,
            "source": "preferred",
            "resolved_at": str(snapshot["fetched_at"]),
            "licence": None,
            "output_price_per_million": None,
            "valid": False,
            "reason": (
                f"none of the {len(passed_over)} model(s) in the catalogue has a provider "
                "route that both supports structured output and is fast enough to answer "
                "within OAK_MODEL_TIMEOUT_SECONDS; run `oak models discover`, raise that "
                "budget, or set the provider policy to fastest"
            ),
            "passed_over": passed_over,
        }

    def verification_status(self, family: str) -> dict[str, Any] | None:
        """The stored verdict about the credential now held for a family, with its age.

        ``None`` when nothing was recorded, when no credential is held any more, or when
        the credential held now is not the one the verdict was about (its fingerprint
        differs — a rotated environment variable, a replaced file): a verdict about a
        credential that is gone is not a verdict about this one.
        """

        descriptor = self._descriptor(family)
        stored = self._document()["verification"].get(family)
        if stored is None:
            return None
        if descriptor.credential_required:
            credential = self.credential_status(family)
            if not credential.configured:
                return None
            recorded = stored.get("credential_fingerprint")
            if (
                recorded is not None
                and credential.fingerprint is not None
                and recorded != credential.fingerprint
            ):
                return None
        checked_at = str(stored["checked_at"])
        return {
            **stored,
            "stale": self._older_than(checked_at, self._clock(), self._verification_stale_seconds),
        }

    def is_verification_stale(self, family: str) -> bool:
        """Whether the credential should be asked about again before it is relied on.

        Missing, older than the window, or not a verdict at all: ``unreachable`` and
        ``unverifiable`` say the provider was not heard, so they never count as a check.
        """

        status = self.verification_status(family)
        return (
            status is None
            or bool(status["stale"])
            or str(status["verdict"]) not in DEFINITIVE_VERDICTS
        )

    def modes(self) -> dict[str, dict[str, Any]]:
        """Which of the three modes can run now, and the reason when one cannot."""

        online: dict[str, Any] = {"available": False, "reason": None, "pair": None}
        pair = self.online_pair()
        verification = self.verification_status("huggingface")
        online["verification"] = verification
        if not self.credential_status("huggingface").configured:
            online["reason"] = (
                "no Hugging Face token is stored; run `oak models set-key` or store one in Settings"
            )
        elif verification is not None and verification["verdict"] == "rejected":
            online["reason"] = (
                f"Hugging Face rejected the stored token at {verification['checked_at']}; "
                "store a current one with `oak models set-key`"
            )
        elif pair is not None and not pair["valid"]:
            online["reason"] = pair["reason"]
        elif pair is None:
            online["reason"] = (
                "no model is known yet; run `oak models discover` to read the catalogue "
                "or pin one with `oak models select huggingface <model_id>`"
            )
        else:
            online["available"] = True
        online["pair"] = pair
        local_selection = self.selection("local")
        local: dict[str, Any] = {
            "available": local_selection is not None,
            "reason": (
                None
                if local_selection is not None
                else "no local model is selected; run `oak models select local <model_id>`"
            ),
            "model_id": None if local_selection is None else local_selection.model_id,
            "endpoint": self._local_endpoint,
        }
        return {
            "deterministic": {"available": True, "reason": None},
            "online": online,
            "local": local,
        }

    def status(self) -> dict[str, Any]:
        document = self._document()
        credentials = {
            family: {
                **self.credential_status(family).to_document(),
                "verification": self.verification_status(family),
            }
            for family in FAMILY_IDS
        }
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
            "modes": self.modes(),
            "selections": {
                family: (None if selection is None else selection.to_document())
                for family, selection in self.selections().items()
            },
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

    def provider_policy(self) -> str:
        return str(self._document()["provider_policy"])

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
        # A new key is an unverified key, whatever the last one was.
        document["verification"].pop(family, None)
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
        if source != "none" or family in document["verification"]:
            document["credential_sources"][family] = "none"
            document["verification"].pop(family, None)
            self._configuration.save(document)
            removed = removed or source != "none"
        return removed

    def verify(self, family: str) -> dict[str, Any]:
        """Ask the provider about the stored credential and record what it said, with the time.

        One free, generation-free request. For Hugging Face it needs a stored token and is
        refused before any request when there is none; the local server is asked whether it
        is up. The verdict replaces any earlier one for the family.
        """

        descriptor = self._descriptor(family)
        if descriptor.credential_required and not self.credential_status(family).configured:
            raise OAKError(
                "OAK-MODEL-KEY-MISSING",
                f"no key is stored for the {family} family; run "
                f"`oak models set-key {family}` first",
            )
        if self._verifier is None:
            raise OAKError(
                "OAK-MODEL-VERIFICATION-UNAVAILABLE",
                "credential verification is not available in this build",
            )
        answer = self._verifier(family)
        return self.record_verdict(
            family,
            str(answer.get("verdict")),
            method=str(answer.get("method")),
            reason=answer.get("reason"),
            token_role=answer.get("token_role"),
            inference_permission=answer.get("inference_permission"),
            can_pay=answer.get("can_pay"),
            is_pro=answer.get("is_pro"),
        )

    def record_verdict(
        self,
        family: str,
        verdict: str,
        *,
        method: str,
        reason: str | None = None,
        token_role: str | None = None,
        inference_permission: bool | None = None,
        can_pay: bool | None = None,
        is_pro: bool | None = None,
    ) -> dict[str, Any]:
        """Store a verdict the provider gave — from `verify`, or from a refused interpretation."""

        descriptor = self._descriptor(family)
        if verdict not in VERDICTS:
            raise OAKError("OAK-MODEL-VERIFICATION-UNAVAILABLE", "the verdict is not recognised")
        if method not in VERIFICATION_METHOD_VALUES:
            raise OAKError(
                "OAK-MODEL-VERIFICATION-UNAVAILABLE", "the verification method is not recognised"
            )
        document = self._document()
        now = self._clock()
        fingerprint: str | None = None
        if descriptor.credential_required:
            secret = self.credential_for(family)
            fingerprint = self._fingerprint(secret) if secret is not None else None
        stored = document["verification"].get(family)
        if (
            verdict not in DEFINITIVE_VERDICTS
            and isinstance(stored, dict)
            and stored.get("verdict") in DEFINITIVE_VERDICTS
            and stored.get("credential_fingerprint") == fingerprint
        ):
            # The provider was not heard this time. That is not a verdict, so the last one
            # it gave stands; the attempt is recorded beside it so the surfaces can say so.
            stored["last_attempt"] = {
                "verdict": verdict,
                "at": now,
                "reason": str(reason)[:400] if isinstance(reason, str) and reason else None,
            }
            self._configuration.save(document)
            status = self.verification_status(family)
            assert status is not None
            return status
        document["verification"][family] = {
            "verdict": verdict,
            "checked_at": now,
            "method": method,
            "credential_fingerprint": fingerprint,
            "token_role": token_role if isinstance(token_role, str) else None,
            "inference_permission": (
                inference_permission if isinstance(inference_permission, bool) else None
            ),
            "can_pay": can_pay if isinstance(can_pay, bool) else None,
            "is_pro": is_pro if isinstance(is_pro, bool) else None,
            "reason": str(reason)[:400] if isinstance(reason, str) and reason else None,
        }
        self._configuration.save(document)
        status = self.verification_status(family)
        assert status is not None
        return status

    def record_discovery(self, family: str, snapshot: dict[str, Any]) -> None:
        """Store a snapshot obtained outside `discover` (the pre-flight refresh)."""

        self._descriptor(family)
        document = self._document()
        document["discovery"][family] = snapshot
        self._configuration.save(document)

    def select(
        self,
        family: str,
        model_id: str,
        *,
        provider_route: str | None = None,
    ) -> ModelSelection:
        """Pin a model (and, for Hugging Face, a provider route) for that family's mode."""

        descriptor = self._descriptor(family)
        if not model_id or len(model_id) > 256:
            raise OAKError("OAK-MODEL-ID", "a model identifier must be 1 to 256 characters")
        if descriptor.credential_required and not self.credential_status(family).configured:
            raise OAKError(
                "OAK-MODEL-KEY-MISSING",
                f"no key is stored for the {family} family; run "
                f"`oak models set-key {family}` first",
            )
        if family != "huggingface" and provider_route is not None:
            raise OAKError(
                "OAK-MODEL-ROUTE", "a provider route is meaningful only for Hugging Face"
            )
        listed = self._listed(self.discovery_snapshot(family), model_id)
        if family == "huggingface":
            if ":" in model_id:
                # `model:route` and `model:cheapest` are the router's own spellings; a route
                # is pinned with --provider, where the catalogue can check it, and a
                # server-side policy is never sent because it may pick a provider without
                # structured output.
                raise OAKError(
                    "OAK-MODEL-ID",
                    "a Hugging Face model identifier carries no `:` suffix; pin the provider "
                    "route with --provider instead",
                )
            if listed is None:
                raise OAKError(
                    "OAK-MODEL-ROUTE",
                    f"the catalogue does not list {model_id}; run `oak models discover` and "
                    "pin a listed pair — only a pair the catalogue shows with a "
                    "structured-output route can be pinned",
                )
            capable = self._capable_routes(listed)
            if not capable:
                raise OAKError(
                    "OAK-MODEL-ROUTE",
                    f"{model_id} has no live provider route that supports structured "
                    "output, which the interpretation needs; run `oak models discover` and "
                    "pick a model listed with one",
                )
            if provider_route is not None and provider_route not in capable:
                raise OAKError(
                    "OAK-MODEL-ROUTE",
                    f"{provider_route} is not a live structured-output route for {model_id}; "
                    f"the catalogue lists {', '.join(capable)}",
                )
        document = self._document()
        document["selection"][family] = {
            "model_id": model_id,
            "provider_route": provider_route,
            "selected_at": self._clock(),
        }
        self._configuration.save(document)
        selection = self.selection(family)
        assert selection is not None
        return selection

    def clear_selection(self, family: str) -> bool:
        self._descriptor(family)
        document = self._document()
        if family not in document["selection"]:
            return False
        del document["selection"][family]
        self._configuration.save(document)
        return True

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

    def is_discovery_stale(self, family: str) -> bool:
        """Whether the family's snapshot is missing or older than the cache window."""

        snapshot = self._document()["discovery"].get(family)
        if snapshot is None:
            return True
        return self._is_stale(str(snapshot["fetched_at"]), self._clock())

    # ----- helpers -----------------------------------------------------------------

    def _document(self) -> dict[str, Any]:
        loaded = self._configuration.load()
        if loaded is not None:
            loaded.setdefault("verification", {})
            return loaded
        return {
            "schema_version": "0.1.0",
            "id": CONFIGURATION_ID,
            "selection": {},
            "credential_sources": {},
            "provider_policy": "cheapest",
            "discovery": {},
            "verification": {},
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
        """Whether a snapshot is older than the configured cache window."""

        return self._older_than(fetched_at, now, self._discovery_cache_seconds)

    @staticmethod
    def _older_than(recorded_at: str, now: str, window_seconds: int) -> bool:
        """Whether a timestamp is older than a window.

        An unparsable or future timestamp reads as stale: suggesting a refresh of a good
        record is a smaller error than presenting a bad one as current.
        """

        try:
            taken = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
            current = datetime.fromisoformat(now.replace("Z", "+00:00"))
            if taken.tzinfo is None:
                taken = taken.replace(tzinfo=UTC)
            if current.tzinfo is None:
                current = current.replace(tzinfo=UTC)
            age = (current - taken).total_seconds()
        except (TypeError, ValueError):
            return True
        return age < 0 or age > window_seconds

    @staticmethod
    def _capable_routes(listed: dict[str, Any] | None) -> list[str]:
        if listed is None:
            return []
        return [
            str(route["provider"])
            for route in listed.get("providers", [])
            if isinstance(route, dict) and route.get("supports_structured_output") is True
        ]

    @staticmethod
    def _listed(snapshot: dict[str, Any] | None, model_id: str) -> dict[str, Any] | None:
        if snapshot is None:
            return None
        for model in snapshot.get("models", []):
            if isinstance(model, dict) and model.get("id") == model_id:
                return model
        return None

    @staticmethod
    def _price(listed: dict[str, Any] | None, route: str | None) -> float | None:
        if listed is None or route is None:
            return None
        for candidate in listed.get("providers", []):
            if isinstance(candidate, dict) and candidate.get("provider") == route:
                price = candidate.get("output_price_per_million")
                return float(price) if isinstance(price, (int, float)) else None
        return None
