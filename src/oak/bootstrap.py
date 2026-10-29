# SPDX-License-Identifier: Apache-2.0
"""Composition root shared by local interfaces."""

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from oak import __version__
from oak.adapters.catalogue import (
    ExtensionFedCatalogue,
    LocalCatalogue,
    ResearchVocabularyLoader,
)
from oak.adapters.credentials import (
    EnvironmentCredentialReference,
    FileCredentialStore,
    KeychainCredentialStore,
    ModelConfigurationFileStore,
    read_api_token,
    write_api_token,
)
from oak.adapters.deployment import HelmKubernetesRenderer, LocalManifestRenderer
from oak.adapters.dispatch import FilesystemMailbox
from oak.adapters.extensions import LocalExtensionStore
from oak.adapters.intake import LocalBriefIntake
from oak.adapters.persistence import (
    FileWorkspaceRepository,
    PostgreSQLCaseDirectory,
    PostgreSQLOperationStore,
    PostgreSQLOutboxStore,
    PostgreSQLReadinessProbe,
    PostgreSQLWorkspaceRepository,
    create_postgresql_engine,
)
from oak.adapters.policies import BuiltinPolicyEngine, LocalPolicyPackStore
from oak.adapters.signing import (
    LocalEd25519Signer,
    enroll_runner,
    initialize_trust_directory,
    load_runner_identities,
    read_trust_directory,
)
from oak.adapters.targets import LocalTargetProfile
from oak.application import (
    DEFAULT_MODEL_REQUESTS_PER_CASE_PER_DAY,
    DEFAULT_OPERATIONS_PER_TENANT,
    CandidatePlanningService,
    CommunityControlPlane,
    CommunityWorker,
    DesignCaseService,
    ExtensionService,
    ModelConfigurationService,
    OperationService,
    OperationWorker,
    PolicyService,
    ReleaseService,
    ReportService,
    ResearchService,
    SystemInformationService,
    pack_summaries,
)
from oak.application.design_case import ModelInterpreterFactory
from oak.application.gitops import GitOpsRenderer
from oak.application.rendering import DeploymentRenderService
from oak.application.workspace_format import WorkspaceFormatService
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry
from oak.domain import RESEARCH_HOSTS, OAKError, SystemInformation
from oak.domain.extension_sdk import (
    HELM_KUBERNETES_RENDERER_ID,
    LOCAL_MANIFEST_RENDERER_ID,
)
from oak.ports.interpreter import ModelInterpreterPort, ProposalLimits
from oak.ports.policy import PolicyEnginePort
from oak.ports.readiness import ReadinessProbe
from oak.ports.report import ReportNarratorPort, ReportRendererPort

SUPPORTED_SCHEMA_VERSIONS = ("0.3.0", "0.4.0")


class _UnconfiguredDatabase:
    """A readiness probe that fails because there is nothing to probe.

    Deliberately not an empty probe tuple: "nothing to check" and "everything checked
    and healthy" must not produce the same answer at `/readyz`.
    """

    def is_ready(self) -> bool:
        return False


def create_system_information_service() -> SystemInformationService:
    """Construct the shared service without a transport-specific dependency."""

    commit = os.getenv("OAK_COMMIT", "unknown")
    information = SystemInformation(
        name="OAK Community",
        version=__version__,
        commit=commit,
        schema_versions=SUPPORTED_SCHEMA_VERSIONS,
    )
    database_url = os.getenv("OAK_DATABASE_URL")
    # An unconfigured database is *not ready*, and must not be silently ready. With no
    # probes at all, `all(())` is True, so `/readyz` answered "ready" on an `oak-api`
    # started without OAK_DATABASE_URL while every `/v1` request returned a 500. A
    # readiness endpoint that reports ready for a service that cannot serve is worse than
    # no readiness endpoint: it is what an orchestrator routes traffic on.
    probes: tuple[ReadinessProbe, ...] = (
        (PostgreSQLReadinessProbe(create_postgresql_engine(database_url)),)
        if database_url
        else (_UnconfiguredDatabase(),)
    )
    return SystemInformationService(information, readiness_probes=probes)


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


def model_proposal_limits() -> ProposalLimits:
    """Proposal bounds whose deadline follows ``OAK_MODEL_TIMEOUT_SECONDS``.

    The adapter spends the smaller of this and the transport's own deadline, so leaving the
    default here would silently cap every interpretation at 30 seconds however the variable
    was set — and `docs/configuration.md` says the variable is what decides.
    """

    return ProposalLimits(timeout_seconds=model_timeout_seconds())


def create_design_case_service(
    workspace: Path, *, model_interpreter_factory: ModelInterpreterFactory | None = None
) -> DesignCaseService:
    """The file-workspace design service. Provider-free unless a factory is passed in."""

    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    repository = FileWorkspaceRepository(workspace, registry)
    return DesignCaseService(
        repository,
        LocalBriefIntake(),
        DeterministicBriefInterpreter(),
        registry,
        model_interpreter_factory=model_interpreter_factory,
        proposal_limits=model_proposal_limits(),
        model_requests_per_day=model_requests_per_case_per_day(),
    )


def create_workspace_format_service(workspace: Path) -> WorkspaceFormatService:
    """The explicit format commands over a file workspace: status and migrate."""

    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    return WorkspaceFormatService(FileWorkspaceRepository(workspace, registry), registry)


def model_timeout_seconds() -> float:
    """The total budget for one provider request, capped below the shipped proxy timeout.

    The default is 35 seconds, not 30: a live run of the preferred pair returned a valid
    proposal in 29.1 seconds, which left under a second of margin, and a longer brief
    produces more claims and more tokens. 35 is the largest default that still leaves the
    20 seconds of headroom the online pre-flight needs under the 55-second ceiling.
    """

    raw = os.getenv("OAK_MODEL_TIMEOUT_SECONDS", "").strip()
    try:
        value = float(raw) if raw else 35.0
    except ValueError:
        value = 35.0
    return max(1.0, min(value, 55.0))


def model_verification_stale_seconds() -> int:
    """How long a credential verdict is believed before the surfaces call it stale."""

    raw = os.getenv("OAK_MODEL_VERIFICATION_STALE_SECONDS", "").strip()
    try:
        value = int(raw) if raw else 86_400
    except ValueError:
        value = 86_400
    return max(0, value)


def model_discovery_cache_seconds() -> int:
    raw = os.getenv("OAK_MODEL_DISCOVERY_CACHE_SECONDS", "").strip()
    try:
        value = int(raw) if raw else 21_600
    except ValueError:
        value = 21_600
    return max(0, value)


MAXIMUM_LIMIT = 1_000_000


def read_limit(name: str, default: int) -> int:
    """An `OAK_*` limit: a whole number from 0 to a million, `0` switching the limit off;
    unset or blank is the default, and anything else is refused (`OAK-LIMIT-CONFIG`), so a
    typo never runs the process with a limit it did not ask for."""

    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = -1
    if value < 0 or value > MAXIMUM_LIMIT:
        raise OAKError(
            "OAK-LIMIT-CONFIG",
            f"{name} must be a whole number from 0 to {MAXIMUM_LIMIT}; 0 switches the limit off",
        )
    return value


def model_requests_per_case_per_day() -> int:
    return read_limit(
        "OAK_MODEL_REQUESTS_PER_CASE_PER_DAY", DEFAULT_MODEL_REQUESTS_PER_CASE_PER_DAY
    )


def operations_per_tenant() -> int:
    return read_limit("OAK_OPERATIONS_PER_TENANT", DEFAULT_OPERATIONS_PER_TENANT)


# A provider's chat answer is bounded by the proposal limits; its *catalogue* is a different
# size of thing — the Hugging Face router alone lists well over a hundred models with per
# provider pricing — so discovery gets its own budget. Sharing the interpretation cap made
# every real discovery exceed it and silently fall back to the pinned chain.
MAXIMUM_CATALOGUE_BYTES = 4_194_304
# A verification answer is a small JSON object; a catalogue is not.
MAXIMUM_VERIFICATION_BYTES = 65_536
# The pre-flight before an online interpretation: a stale verdict is re-checked and a stale
# catalogue refreshed, each under its own budget, and only when the interpretation's own
# budget leaves this much headroom below the 55-second ceiling the shipped proxy imposes.
VERIFICATION_BUDGET_SECONDS = 5.0
PREFLIGHT_DISCOVERY_BUDGET_SECONDS = 15.0
PREFLIGHT_HEADROOM_SECONDS = 20.0
INTERPRETATION_CEILING_SECONDS = 55.0


def _model_transport(profile: Any, *, maximum_response_bytes: int | None = None) -> Any:
    """Build the one outbound client, scoped to this provider's own hosts."""

    from oak.adapters.models.transport import ModelTransport

    return ModelTransport(
        allowed_hosts=profile.allowed_hosts,
        deadline_seconds=model_timeout_seconds(),
        maximum_response_bytes=(
            maximum_response_bytes
            if maximum_response_bytes is not None
            else ProposalLimits().maximum_output_bytes
        ),
        allow_plain_http_loopback=profile.plain_http_loopback,
    )


def model_discoverer(family: str, previous: dict[str, Any] | None) -> dict[str, Any]:
    """Refresh one family's catalogue. Called only by an explicit `oak models discover`."""

    del previous  # a refresh always asks the provider; the cache age is the caller's concern
    from oak.adapters.models.huggingface_catalogue import discover_huggingface
    from oak.adapters.models.providers import discover_models, profile_for

    profile = profile_for(family, local_endpoint=os.getenv("OAK_MODEL_ENDPOINT_LOCAL"))
    transport = _model_transport(profile, maximum_response_bytes=MAXIMUM_CATALOGUE_BYTES)
    fetched_at = _utc_now()
    budget = model_timeout_seconds()
    if family == "huggingface":
        return discover_huggingface(transport.send, fetched_at=fetched_at, deadline_seconds=budget)
    configuration = create_model_configuration_service()
    secret = configuration.credential_for(family)
    return discover_models(
        profile,
        transport.send,
        key=secret.reveal() if secret is not None else None,
        fetched_at=fetched_at,
        deadline_seconds=budget,
    )


def model_verifier(family: str, *, deadline_seconds: float | None = None) -> dict[str, Any]:
    """One free request that asks the provider about the stored credential.

    Called by `ModelConfigurationService.verify` and by the pre-flight. The key travels in
    the request header only; the answer is parsed into a verdict and every other byte of
    it is dropped. A transport failure is an ``unreachable`` verdict, not an exception,
    because it says nothing about the credential.
    """

    from oak.adapters.models.providers import (
        VERIFICATION_METHODS,
        key_verification_request,
        parse_verification,
        profile_for,
    )

    profile = profile_for(family, local_endpoint=os.getenv("OAK_MODEL_ENDPOINT_LOCAL"))
    configuration = create_model_configuration_service()
    secret = configuration.credential_for(family)
    key = secret.reveal() if secret is not None else None
    if profile.credential_required and key is None:
        raise OAKError(
            "OAK-MODEL-KEY-MISSING",
            f"no key is stored for the {family} family; run `oak models set-key {family}` first",
        )
    request = key_verification_request(profile, key)
    del key, secret
    if request is None:
        return {
            "verdict": "unverifiable",
            "method": "unknown",
            "reason": f"the {family} provider documents no free way to check a credential",
        }
    transport = _model_transport(profile, maximum_response_bytes=MAXIMUM_VERIFICATION_BYTES)
    budget = min(
        transport.deadline_seconds,
        VERIFICATION_BUDGET_SECONDS if deadline_seconds is None else float(deadline_seconds),
    )
    try:
        response = transport.send(request, deadline_seconds=budget)
    except OAKError as error:
        if error.code in {"OAK-INTERPRETER-UNAVAILABLE", "OAK-INTERPRETER-OUTPUT-LIMIT"}:
            return {
                "verdict": "unreachable",
                "method": VERIFICATION_METHODS[profile.key_verification],
                "reason": "the provider could not be reached for verification",
            }
        raise
    return parse_verification(profile, response).to_document()


def _preflight_discover(configuration: ModelConfigurationService) -> None:
    """Refresh a stale Hugging Face catalogue before an online interpretation, if it can."""

    from oak.adapters.models.huggingface_catalogue import discover_huggingface
    from oak.adapters.models.providers import profile_for

    profile = profile_for("huggingface")
    transport = _model_transport(profile, maximum_response_bytes=MAXIMUM_CATALOGUE_BYTES)
    try:
        snapshot = discover_huggingface(
            transport.send,
            fetched_at=_utc_now(),
            deadline_seconds=PREFLIGHT_DISCOVERY_BUDGET_SECONDS,
        )
    except OAKError:
        # The stored snapshot, or none, is what the interpretation will work from; the
        # refusal it then meets is the honest one.
        return
    if snapshot.get("source") != "live" and configuration.discovery_snapshot("huggingface"):
        # `discover_huggingface` answers with the pinned chain when it cannot read the
        # catalogues. Recording that over a real snapshot would stamp a constant as today's
        # catalogue and could invalidate the user's pinned pair on nothing but a timeout.
        return
    try:
        configuration.record_discovery("huggingface", snapshot)
    except OSError:
        # The refresh is a convenience; a model-state directory that cannot be written is
        # not a reason to abandon an interpretation the stored state can still serve.
        return


def preflight_allowed() -> bool:
    """Whether the interpretation budget leaves room for the pre-flight under the proxy limit."""

    return model_timeout_seconds() + PREFLIGHT_HEADROOM_SECONDS <= INTERPRETATION_CEILING_SECONDS


def _online_preflight(configuration: ModelConfigurationService) -> None:
    """Corroborate the token and refresh the catalogue when either is stale; refuse a bad token.

    Nothing here spends: the verification is generation-free and the catalogue reads are
    anonymous. A token the Hub rejected is refused before any request that could spend.
    """

    # The Hub's last word stands until a new token is stored: a rejection is not re-asked
    # about, and a later attempt that cannot reach the Hub never erases it.
    _refuse_if_rejected(configuration)
    if preflight_allowed():
        if configuration.is_verification_stale("huggingface"):
            try:
                configuration.verify("huggingface")
            except OAKError as error:
                if error.code != "OAK-MODEL-VERIFICATION-UNAVAILABLE":
                    raise
            except OSError:
                # The verdict could not be written. The stored one still governs the
                # refusal below; a read-only model-state directory is not a verdict.
                pass
        if configuration.is_discovery_stale("huggingface"):
            _preflight_discover(configuration)
    _refuse_if_rejected(configuration)


def _refuse_if_rejected(configuration: ModelConfigurationService) -> None:
    verification = configuration.verification_status("huggingface")
    if verification is not None and verification["verdict"] == "rejected":
        raise OAKError(
            "OAK-MODEL-KEY-REJECTED",
            f"Hugging Face rejected the stored token at {verification['checked_at']}; store a "
            "current one with `oak models set-key` (nothing was sent to a model)",
        )


class _VerdictRecordingInterpreter:
    """Wrap the adapter so a token the provider refuses mid-interpretation is remembered."""

    def __init__(
        self, inner: ModelInterpreterPort, configuration: ModelConfigurationService, family: str
    ) -> None:
        self._inner = inner
        self._configuration = configuration
        self._family = family

    def propose(
        self, source_record: dict[str, Any], source_content: bytes, limits: Any
    ) -> dict[str, Any]:
        from oak.adapters.models.providers import KEY_REJECTED_MARKER

        try:
            return self._inner.propose(source_record, source_content, limits)
        except OAKError as error:
            # Only a 401 — the credential itself refused — is a verdict about the token; a
            # 403 on one request (a route, a gated model) is not, and the local server has
            # no credential to record a verdict about.
            if (
                error.code == "OAK-MODEL-KEY-REJECTED"
                and self._family == "huggingface"
                and KEY_REJECTED_MARKER in error.message
            ):
                self._configuration.record_verdict(
                    self._family,
                    "rejected",
                    method="interpretation",
                    reason="the provider rejected the stored credential during an interpretation",
                )
            raise


def _model_route(mode: str) -> tuple[ModelConfigurationService, str, str, str | None] | None:
    """The configuration, family, model and provider route one model mode calls, or ``None``.

    ``online`` is the Hugging Face pair the user pinned, else the preferred one discovery
    recorded; ``local`` is the model pinned for the loopback server.
    """

    if mode not in {"online", "local"}:
        return None
    configuration = create_model_configuration_service()
    if mode == "local":
        selection = configuration.selection("local")
        if selection is None:
            return None
        family, model_id, route = "local", selection.model_id, None
    else:
        if not configuration.credential_status("huggingface").configured:
            return None
        _online_preflight(configuration)
        pair = configuration.online_pair()
        if pair is None:
            return None
        if not pair["valid"]:
            # A pinned pair the current catalogue no longer supports is refused with the
            # reason, never called on the off chance: only structured-output routes are sent.
            raise OAKError("OAK-MODEL-ROUTE", str(pair["reason"]))
        family, model_id, route = "huggingface", str(pair["model_id"]), pair.get("provider_route")
    return configuration, family, model_id, route


def create_model_interpreter(mode: str) -> ModelInterpreterPort | None:
    """The adapter for one model mode, or ``None`` when that mode has nothing to call.

    ``None`` makes the service refuse with ``OAK-MODEL-NOT-CONFIGURED`` and commit nothing.
    Nothing is imported from the provider modules, and no socket is opened, until one of
    them is asked for.
    """

    chosen = _model_route(mode)
    if chosen is None:
        return None
    configuration, family, model_id, route = chosen
    from oak.adapters.models.hosted_interpreter import HostedModelInterpreter, build_path_hints
    from oak.adapters.models.providers import profile_for

    profile = profile_for(family, local_endpoint=os.getenv("OAK_MODEL_ENDPOINT_LOCAL"))
    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    adapter = HostedModelInterpreter(
        profile,
        model_id,
        provider_route=route,
        credential_provider=lambda: configuration.credential_for(family),
        transport=_model_transport(profile),
        path_hints=build_path_hints(registry.schema("system-intent.schema.json")),
    )
    return _VerdictRecordingInterpreter(adapter, configuration, family)


def create_report_narrator(mode: str) -> ReportNarratorPort | None:
    """The note proposer for one model mode, or ``None`` when that mode has nothing to call.

    The same model the user configured for interpretation, asked once per recording for
    notes on the report's main slides. A deterministic recording never reaches here.
    """

    chosen = _model_route(mode)
    if chosen is None:
        return None
    configuration, family, model_id, route = chosen
    from oak.adapters.models.providers import profile_for
    from oak.adapters.models.report_narrator import HostedReportNarrator

    profile = profile_for(family, local_endpoint=os.getenv("OAK_MODEL_ENDPOINT_LOCAL"))
    return HostedReportNarrator(
        profile,
        model_id,
        provider_route=route,
        credential_provider=lambda: configuration.credential_for(family),
        transport=_model_transport(profile),
    )


def research_source_mode() -> tuple[str, frozenset[str]]:
    """`(source_mode, hosts)` without building a transport: what a plan read shows."""

    if os.getenv("OAK_RESEARCH_FIXTURES", "").strip():
        return "fixture", frozenset()
    return "live", RESEARCH_HOSTS


_RESEARCH_CACHE: Any = None


def research_cache() -> Any:
    """The worker's in-memory research cache, created on first use (24 hours, by terms).

    Handed to the services as a factory: the reader it imports loads on the first
    consented live run, never when the API or the worker starts (ADR-0018).
    """

    global _RESEARCH_CACHE
    if _RESEARCH_CACHE is None:
        from oak.adapters.models.research_sources import ResearchCache

        _RESEARCH_CACHE = ResearchCache()
    return _RESEARCH_CACHE


def research_runner(*arguments: Any, **keywords: Any) -> Any:
    """The adapter's `run_research`, imported at the moment of use (never on the default path)."""

    from oak.adapters.models.research_sources import run_research

    return run_research(*arguments, **keywords)


def create_research_service(workspace: Path) -> ResearchService:
    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    catalogue_directory = canonical_catalogue_directory()
    return ResearchService(
        FileWorkspaceRepository(workspace, registry),
        registry,
        LocalCatalogue(catalogue_directory, registry),
        ResearchVocabularyLoader(catalogue_directory),
        source_factory=lambda occurred_at: create_research_source(occurred_at=occurred_at),
        source_mode=research_source_mode,
        runner=research_runner,
        cache=research_cache,
    )


def create_research_source(*, occurred_at: str) -> tuple[Any, str, frozenset[str]]:
    """`(fetch, source_mode, hosts)` for one research run (Sprint 14, ADR-0018).

    The fixture source is selected only by ``OAK_RESEARCH_FIXTURES`` (safety-relevant,
    ``RR-052``); otherwise the one transport, scoped to exactly the three research hosts.
    Both are imported lazily, so a deterministic generation never loads either.
    """

    directory = os.getenv("OAK_RESEARCH_FIXTURES", "").strip()
    if directory:
        from oak.adapters.models.research_fixture import FixtureResearchSource

        source = FixtureResearchSource(Path(directory), occurred_at=occurred_at)
        return source.fetch, "fixture", frozenset()
    from oak.adapters.models.research_sources import MAXIMUM_RESPONSE_BYTES
    from oak.adapters.models.transport import ModelTransport

    transport = ModelTransport(
        allowed_hosts=RESEARCH_HOSTS,
        deadline_seconds=INTERPRETATION_CEILING_SECONDS,
        maximum_response_bytes=MAXIMUM_RESPONSE_BYTES,
    )
    return transport.send, "live", RESEARCH_HOSTS


def create_report_renderer() -> ReportRendererPort:
    """The PDF renderer; imported here so a command that draws nothing never loads it."""

    from oak.adapters.report import PdfReportRenderer

    return PdfReportRenderer()


def create_report_service(workspace: Path) -> ReportService:
    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    return ReportService(
        FileWorkspaceRepository(workspace, registry),
        registry,
        create_report_renderer(),
        oak_version=__version__,
        narrator_factory=create_report_narrator,
        proposal_limits=model_proposal_limits(),
        model_requests_per_day=model_requests_per_case_per_day(),
    )


def _choose_route(listed: dict[str, Any] | None, policy: str) -> str | None:
    """The provider route for a listed model under the user's policy and its time budget.

    ``None`` means no route of this model can generate a proposal inside
    ``OAK_MODEL_TIMEOUT_SECONDS``, so the caller should try the next model rather than send
    a request that will expire.
    """

    from oak.adapters.models.providers import recommended_route

    return recommended_route(listed, policy, budget_seconds=model_timeout_seconds())


def canonical_catalogue_directory() -> Path:
    """Locate the bundled synthetic catalogue without requiring network access."""

    configured = os.getenv("OAK_CATALOGUE_DIRECTORY")
    candidates = [
        Path(configured) if configured else None,
        Path(__file__).resolve().parent / "community_catalogue",
        Path(__file__).resolve().parents[2] / "catalogue",
    ]
    for candidate in candidates:
        if candidate is not None and (candidate / "components").is_dir():
            return candidate
    raise RuntimeError("OAK Community catalogue is not installed")


def create_candidate_planning_service(workspace: Path) -> CandidatePlanningService:
    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    repository = FileWorkspaceRepository(workspace, registry)
    return CandidatePlanningService(
        repository,
        compiler_catalogue(registry),
        LocalTargetProfile(registry),
        registry,
        research_vocabulary=ResearchVocabularyLoader(canonical_catalogue_directory()),
    )


def canonical_policy_pack_directory() -> Path:
    """Locate the bundled deterministic fixture policy packs offline."""

    configured = os.getenv("OAK_POLICY_PACK_DIRECTORY")
    candidates = [
        Path(configured) if configured else None,
        Path(__file__).resolve().parent / "community_policy_packs",
        Path(__file__).resolve().parents[2] / "policy-packs",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_dir():
            return candidate
    raise RuntimeError("OAK Community policy packs are not installed")


def compiler_catalogue(registry: SchemaRegistry) -> ExtensionFedCatalogue:
    """The catalogue every compile reads: the curated documents in the wheel, plus the
    activated component-manifest and architecture-pattern extensions whose packs the
    operator's trust directory vouches for when they are read."""

    return ExtensionFedCatalogue(
        LocalCatalogue(canonical_catalogue_directory(), registry),
        LocalExtensionStore(default_extensions_directory(), registry),
        load_steward_anchors,
        registry,
    )


def default_extensions_directory() -> Path:
    configured = os.getenv("OAK_EXTENSIONS_DIRECTORY")
    if configured:
        return Path(configured).absolute()
    return Path.home() / ".oak" / "extensions"


def policy_engine_loaders() -> dict[str, "Callable[[], PolicyEnginePort]"]:
    """Registered policy engines; only the built-in engine is required."""

    def load_builtin() -> PolicyEnginePort:
        return BuiltinPolicyEngine()

    def load_opa() -> PolicyEnginePort:
        from oak.adapters.policies.opa import OpaPolicyEngine

        return OpaPolicyEngine()

    return {"builtin": load_builtin, "opa": load_opa}


def load_steward_anchors() -> dict[str, str]:
    """Pinned extension-steward public keys from the local trust directory."""

    identity_path = default_trust_directory() / "extension-steward.identity.json"
    try:
        document = json.loads(identity_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    key_id = document.get("key_id")
    public_key = document.get("public_key_base64")
    if isinstance(key_id, str) and isinstance(public_key, str):
        return {key_id: public_key}
    return {}


def create_extension_service() -> ExtensionService:
    registry = SchemaRegistry.from_directory(canonical_schema_directory())

    def bundled_pack_ids() -> frozenset[str]:
        store = LocalPolicyPackStore(
            (canonical_policy_pack_directory(),),
            registry,
            nested_directories=(default_extensions_directory() / "active",),
        )
        return frozenset(str(pack["id"]) for pack in store.list_packs())

    return ExtensionService(
        registry,
        LocalExtensionStore(default_extensions_directory(), registry),
        BuiltinPolicyEngine,
        load_steward_anchors,
        __version__,
        bundled_pack_ids,
    )


def load_steward_signer() -> LocalEd25519Signer:
    return LocalEd25519Signer.load(default_trust_directory(), "extension-steward")


def _policy_pack_store(registry: SchemaRegistry) -> LocalPolicyPackStore:
    return LocalPolicyPackStore(
        (canonical_policy_pack_directory(),),
        registry,
        # Read each activated extension's verified pack in place rather than a
        # materialized copy, so the pack that is evaluated is the pack that was
        # digest-checked and signature-verified at activation.
        nested_directories=(default_extensions_directory() / "active",),
    )


def create_policy_service(workspace: Path) -> PolicyService:
    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    repository = FileWorkspaceRepository(workspace, registry)
    return PolicyService(
        repository, registry, _policy_pack_store(registry), policy_engine_loaders()
    )


def list_policy_packs() -> tuple[dict[str, Any], ...]:
    """The available policy packs; reading them needs no workspace."""

    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    return pack_summaries(_policy_pack_store(registry))


def create_render_service(workspace: Path) -> DeploymentRenderService:
    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    repository = FileWorkspaceRepository(workspace, registry)
    return DeploymentRenderService(
        repository,
        {
            LOCAL_MANIFEST_RENDERER_ID: LocalManifestRenderer(),
            HELM_KUBERNETES_RENDERER_ID: HelmKubernetesRenderer(),
        },
    )


def default_trust_directory() -> Path:
    configured = os.getenv("OAK_TRUST_DIRECTORY")
    if configured:
        return Path(configured).absolute()
    return Path.home() / ".oak" / "trust"


def default_mailbox_directory() -> Path:
    configured = os.getenv("OAK_DISPATCH_MAILBOX")
    if configured:
        return Path(configured).absolute()
    return Path.home() / ".oak" / "mailbox"


def default_credentials_directory() -> Path:
    """Where provider keys and the per-process model token live (owner-only files)."""

    configured = os.getenv("OAK_CREDENTIALS_DIRECTORY")
    if configured:
        return Path(configured).absolute()
    return Path.home() / ".oak" / "credentials"


def default_models_directory() -> Path:
    """Where the non-secret model selection and discovery snapshot live."""

    configured = os.getenv("OAK_MODELS_DIRECTORY")
    if configured:
        return Path(configured).absolute()
    return Path.home() / ".oak" / "models"


def mint_model_token() -> str:
    """Write a fresh per-process capability token and return it."""

    return write_api_token(default_credentials_directory())


def read_model_token() -> str | None:
    """Read the current capability token; ``None`` when no server has minted one."""

    return read_api_token(default_credentials_directory())


def create_model_configuration_service() -> ModelConfigurationService:
    """The user's model selection and credential backends; nothing here touches a network."""

    credentials_directory = default_credentials_directory()
    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    file_store = FileCredentialStore(credentials_directory)
    return ModelConfigurationService(
        ModelConfigurationFileStore(default_models_directory(), registry),
        {
            "keychain": KeychainCredentialStore(),
            "file": file_store,
            "env": EnvironmentCredentialReference(),
        },
        clock=_utc_now,
        discoverer=model_discoverer,
        verifier=model_verifier,
        route_chooser=_choose_route,
        discovery_cache_seconds=model_discovery_cache_seconds(),
        verification_stale_seconds=model_verification_stale_seconds(),
        token_reader=read_model_token,
        credentials_location=str(credentials_directory),
        local_endpoint=os.getenv("OAK_MODEL_ENDPOINT_LOCAL"),
        under_compose=os.getenv("OAK_ARTIFACT_ROOT", "").startswith("/var/lib/oak/"),
    )


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def initialize_local_trust() -> tuple[dict[str, str], ...]:
    """Create missing local signing keys and return their public identities."""

    return tuple(
        identity.to_document() for identity in initialize_trust_directory(default_trust_directory())
    )


def show_local_trust() -> tuple[dict[str, str], ...]:
    """The local signing identities, read only; refuses when none exists yet."""

    return tuple(
        identity.to_document() for identity in read_trust_directory(default_trust_directory())
    )


def enroll_local_runner(document: object) -> dict[str, str]:
    """Pin a runner's public identity in the local trust directory."""

    return enroll_runner(default_trust_directory(), document)


def create_release_service(workspace: Path) -> ReleaseService:
    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    repository = FileWorkspaceRepository(workspace, registry)
    trust_directory = default_trust_directory()
    return ReleaseService(
        repository,
        registry,
        lambda role: LocalEd25519Signer.load(trust_directory, role),
        FilesystemMailbox(default_mailbox_directory()),
        runner_identities=lambda: load_runner_identities(trust_directory),
    )


def create_gitops_renderer(workspace: Path) -> GitOpsRenderer:
    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    return GitOpsRenderer(FileWorkspaceRepository(workspace, registry))


def create_persistent_control_plane() -> CommunityControlPlane:
    """Construct the PostgreSQL-backed local Community application facade."""

    database_url = os.getenv("OAK_DATABASE_URL")
    if not database_url:
        raise RuntimeError("OAK_DATABASE_URL is required for persistent API operations")
    artifact_root = Path(os.getenv("OAK_ARTIFACT_ROOT", ".oak/server-artifacts")).absolute()
    environment_id = os.getenv("OAK_ENVIRONMENT_ID", "local")
    engine = create_postgresql_engine(database_url)
    registry = SchemaRegistry.from_directory(canonical_schema_directory())

    def repository_factory(workspace_id: str, tenant_id: str) -> PostgreSQLWorkspaceRepository:
        return PostgreSQLWorkspaceRepository(
            engine,
            registry,
            artifact_root,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            environment_id=environment_id,
        )

    maximum_active = operations_per_tenant()
    model_requests_per_day = model_requests_per_case_per_day()

    def operation_service_factory(tenant_id: str) -> OperationService:
        return OperationService(
            PostgreSQLOperationStore(
                engine,
                tenant_id=tenant_id,
                environment_id=environment_id,
            ),
            environment_id=environment_id,
            maximum_active=maximum_active,
        )

    def outbox_store_factory(tenant_id: str) -> PostgreSQLOutboxStore:
        return PostgreSQLOutboxStore(
            engine,
            tenant_id=tenant_id,
            environment_id=environment_id,
        )

    def case_directory_factory(tenant_id: str) -> PostgreSQLCaseDirectory:
        return PostgreSQLCaseDirectory(
            engine,
            tenant_id=tenant_id,
            environment_id=environment_id,
        )

    return CommunityControlPlane(
        repository_factory,
        operation_service_factory,
        LocalBriefIntake(),
        DeterministicBriefInterpreter(),
        compiler_catalogue(registry),
        LocalTargetProfile(registry),
        registry,
        outbox_store_factory,
        case_directory_factory,
        model_interpreter_factory=create_model_interpreter,
        proposal_limits=model_proposal_limits(),
        report_renderer=create_report_renderer(),
        report_narrator_factory=create_report_narrator,
        oak_version=__version__,
        model_requests_per_day=model_requests_per_day,
        research_vocabulary=ResearchVocabularyLoader(canonical_catalogue_directory()),
        research_source_factory=lambda occurred_at: create_research_source(occurred_at=occurred_at),
        research_source_mode=research_source_mode,
        research_runner=research_runner,
        research_cache=research_cache,
    )


def create_persistent_worker(*, worker_id: str) -> CommunityWorker:
    """Construct the separately leased compiler/outbox worker for local Community mode."""

    database_url = os.getenv("OAK_DATABASE_URL")
    if not database_url:
        raise RuntimeError("OAK_DATABASE_URL is required for oak-worker")
    tenant_id = os.getenv("OAK_LOCAL_TENANT", "local")
    environment_id = os.getenv("OAK_ENVIRONMENT_ID", "local")
    engine = create_postgresql_engine(database_url)
    control_plane = create_persistent_control_plane()
    operation_store = PostgreSQLOperationStore(
        engine,
        tenant_id=tenant_id,
        environment_id=environment_id,
    )
    operation_worker = OperationWorker(
        operation_store,
        {
            "generate_candidates": control_plane.execute_operation,
            "evaluate_candidate": control_plane.execute_operation,
            "compile_bundle": control_plane.execute_operation,
            "research_catalogue": control_plane.execute_operation,
        },
    )
    return CommunityWorker(
        operation_worker,
        PostgreSQLOutboxStore(
            engine,
            tenant_id=tenant_id,
            environment_id=environment_id,
        ),
        worker_id=worker_id,
    )
