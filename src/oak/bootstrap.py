# SPDX-License-Identifier: Apache-2.0
"""Composition root shared by local interfaces."""

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from oak import __version__
from oak.adapters.catalogue import LocalCatalogue
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
from oak.adapters.signing import LocalEd25519Signer, initialize_trust_directory
from oak.adapters.targets import LocalTargetProfile
from oak.application import (
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
    SystemInformationService,
)
from oak.application.design_case import ModelInterpreterFactory
from oak.application.gitops import GitOpsRenderer
from oak.application.rendering import DeploymentRenderService
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry
from oak.domain import SystemInformation
from oak.domain.extension_sdk import (
    HELM_KUBERNETES_RENDERER_ID,
    LOCAL_MANIFEST_RENDERER_ID,
)
from oak.ports.interpreter import ModelInterpreterPort, ProposalLimits
from oak.ports.policy import PolicyEnginePort
from oak.ports.readiness import ReadinessProbe

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
    )


def model_timeout_seconds() -> float:
    """The total budget for one provider request, capped below the shipped proxy timeout."""

    raw = os.getenv("OAK_MODEL_TIMEOUT_SECONDS", "").strip()
    try:
        value = float(raw) if raw else 30.0
    except ValueError:
        value = 30.0
    return max(1.0, min(value, 55.0))


def model_discovery_cache_seconds() -> int:
    raw = os.getenv("OAK_MODEL_DISCOVERY_CACHE_SECONDS", "").strip()
    try:
        value = int(raw) if raw else 21_600
    except ValueError:
        value = 21_600
    return max(0, value)


# A provider's chat answer is bounded by the proposal limits; its *catalogue* is a different
# size of thing — the Hugging Face router alone lists well over a hundred models with per
# provider pricing — so discovery gets its own budget. Sharing the interpretation cap made
# every real discovery exceed it and silently fall back to the pinned chain.
MAXIMUM_CATALOGUE_BYTES = 4_194_304


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


def create_model_interpreter() -> ModelInterpreterPort | None:
    """The model adapter for the user's current selection, or ``None`` when none applies.

    ``None`` means "no model is configured": ``--interpreter model`` then refuses with
    ``OAK-MODEL-NOT-CONFIGURED`` and ``auto`` stays deterministic. Nothing is imported from
    the provider modules, and no socket is opened, until a selection actually exists.
    """

    configuration = create_model_configuration_service()
    selection = configuration.selection()
    if selection is None or selection.default_interpreter != "model":
        return None
    family = selection.family
    from oak.adapters.models.hosted_interpreter import HostedModelInterpreter, build_path_hints
    from oak.adapters.models.providers import profile_for, recommended_route

    profile = profile_for(family, local_endpoint=os.getenv("OAK_MODEL_ENDPOINT_LOCAL"))
    route = selection.provider_route
    if route is None and family == "huggingface":
        snapshot = configuration.discovery_snapshot(family) or {}
        listed = next(
            (
                model
                for model in snapshot.get("models", [])
                if model.get("id") == selection.model_id
            ),
            None,
        )
        route = recommended_route(listed, str(snapshot.get("provider_policy", "cheapest")))
    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    return HostedModelInterpreter(
        profile,
        selection.model_id,
        provider_route=route,
        credential_provider=lambda: configuration.credential_for(family),
        transport=_model_transport(profile),
        path_hints=build_path_hints(registry.schema("system-intent.schema.json")),
    )


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
        LocalCatalogue(canonical_catalogue_directory(), registry),
        LocalTargetProfile(registry),
        registry,
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


def create_policy_service(workspace: Path) -> PolicyService:
    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    repository = FileWorkspaceRepository(workspace, registry)
    return PolicyService(
        repository,
        registry,
        LocalPolicyPackStore(
            (canonical_policy_pack_directory(),),
            registry,
            # Read each activated extension's verified pack in place rather than a
            # materialized copy, so the pack that is evaluated is the pack that was
            # digest-checked and signature-verified at activation.
            nested_directories=(default_extensions_directory() / "active",),
        ),
        policy_engine_loaders(),
    )


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
        discovery_cache_seconds=model_discovery_cache_seconds(),
        token_reader=read_model_token,
        credentials_location=str(credentials_directory),
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


def create_release_service(workspace: Path) -> ReleaseService:
    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    repository = FileWorkspaceRepository(workspace, registry)
    trust_directory = default_trust_directory()
    return ReleaseService(
        repository,
        registry,
        lambda role: LocalEd25519Signer.load(trust_directory, role),
        FilesystemMailbox(default_mailbox_directory()),
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

    def operation_service_factory(tenant_id: str) -> OperationService:
        return OperationService(
            PostgreSQLOperationStore(
                engine,
                tenant_id=tenant_id,
                environment_id=environment_id,
            ),
            environment_id=environment_id,
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
        LocalCatalogue(canonical_catalogue_directory(), registry),
        LocalTargetProfile(registry),
        registry,
        outbox_store_factory,
        case_directory_factory,
        model_interpreter_factory=create_model_interpreter,
        proposal_limits=model_proposal_limits(),
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
