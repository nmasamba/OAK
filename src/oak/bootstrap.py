# SPDX-License-Identifier: Apache-2.0
"""Composition root shared by local interfaces."""

import os
from collections.abc import Callable
from pathlib import Path

from oak import __version__
from oak.adapters.catalogue import LocalCatalogue
from oak.adapters.dispatch import FilesystemMailbox
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
    OperationService,
    OperationWorker,
    PolicyService,
    ReleaseService,
    SystemInformationService,
)
from oak.application.gitops import GitOpsRenderer
from oak.compiler import DeterministicBriefInterpreter
from oak.contracts import SchemaRegistry
from oak.domain import SystemInformation
from oak.ports.policy import PolicyEnginePort

SUPPORTED_SCHEMA_VERSIONS = ("0.3.0", "0.4.0")


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
    probes = (
        (PostgreSQLReadinessProbe(create_postgresql_engine(database_url)),) if database_url else ()
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


def create_design_case_service(workspace: Path) -> DesignCaseService:
    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    repository = FileWorkspaceRepository(workspace, registry)
    return DesignCaseService(
        repository,
        LocalBriefIntake(),
        DeterministicBriefInterpreter(),
        registry,
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


def create_policy_service(workspace: Path) -> PolicyService:
    registry = SchemaRegistry.from_directory(canonical_schema_directory())
    repository = FileWorkspaceRepository(workspace, registry)
    pack_directories = (
        canonical_policy_pack_directory(),
        default_extensions_directory() / "active-packs",
    )
    return PolicyService(
        repository,
        registry,
        LocalPolicyPackStore(pack_directories, registry),
        policy_engine_loaders(),
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
