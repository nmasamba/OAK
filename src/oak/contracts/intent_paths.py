# SPDX-License-Identifier: Apache-2.0
"""The intent paths a model proposal may populate.

A proposal is untrusted data. The merge in ``oak.compiler.interpretation`` applies a
claim only when its path is one of these, so a model can never write outside the typed
``SystemIntentSpec`` sections, never address an array element (arrays are replaced whole),
and never reach an ``extensions`` slot other than the one production-data declaration the
deterministic interpreter itself records. The tuple is checked in rather than derived at
import time so that a schema edit cannot widen the model's reach silently: a contract
test derives the same set from ``system-intent.schema.json`` and fails when they drift.
"""

ADMISSIBLE_INTENT_PATHS: tuple[str, ...] = (
    "/spec/data/classifications",
    "/spec/data/deletion_requirement",
    "/spec/data/extensions/oak.community~1production_data_permitted",
    "/spec/data/lineage_requirement",
    "/spec/data/permitted_uses",
    "/spec/data/residency",
    "/spec/data/retention",
    "/spec/data/sources",
    "/spec/data/velocity",
    "/spec/data/volume",
    "/spec/decision/actions",
    "/spec/decision/autonomy",
    "/spec/decision/irreversible_actions",
    "/spec/decision/reversibility",
    "/spec/decision/task_types",
    "/spec/deployment_environment/modes",
    "/spec/deployment_environment/network_constraints",
    "/spec/deployment_environment/targets",
    "/spec/domain/accessibility_requirements",
    "/spec/domain/countries",
    "/spec/domain/cultural_considerations",
    "/spec/domain/languages",
    "/spec/domain/sectors",
    "/spec/domain/setting",
    "/spec/economics/build_budget",
    "/spec/economics/cost_per_success",
    "/spec/economics/energy_constraints",
    "/spec/economics/operating_budget",
    "/spec/economics/procurement_constraints",
    "/spec/economics/staffing",
    "/spec/hardware/accelerators",
    "/spec/hardware/cpu_architectures",
    "/spec/hardware/drivers",
    "/spec/hardware/expansion_path",
    "/spec/hardware/network",
    "/spec/hardware/power_watts",
    "/spec/hardware/ram_gib",
    "/spec/hardware/storage_gib",
    "/spec/hardware/topology",
    "/spec/hardware/vram_gib",
    "/spec/lifecycle/adaptation_policy",
    "/spec/lifecycle/archival_policy",
    "/spec/lifecycle/compatibility_policy",
    "/spec/lifecycle/decommission_policy",
    "/spec/lifecycle/deletion_policy",
    "/spec/lifecycle/expected_lifetime_months",
    "/spec/lifecycle/upgrade_policy",
    "/spec/openness_sovereignty/allowed_model_classes",
    "/spec/openness_sovereignty/allowed_software_classes",
    "/spec/openness_sovereignty/data_locality",
    "/spec/openness_sovereignty/model_locality",
    "/spec/openness_sovereignty/portability_requirement",
    "/spec/openness_sovereignty/proprietary_exception_process",
    "/spec/operational_contract/availability_percent",
    "/spec/operational_contract/concurrency",
    "/spec/operational_contract/expected_users",
    "/spec/operational_contract/freshness_seconds",
    "/spec/operational_contract/latency_p95_ms",
    "/spec/operational_contract/modes",
    "/spec/operational_contract/rpo_seconds",
    "/spec/operational_contract/rto_seconds",
    "/spec/operational_contract/throughput_per_second",
    "/spec/organization/change_process",
    "/spec/organization/owners",
    "/spec/organization/release_cadence",
    "/spec/organization/skills",
    "/spec/organization/support_hours",
    "/spec/organization/team_size",
    "/spec/organization/vendor_tolerance",
    "/spec/purpose/ai_needed_hypothesis",
    "/spec/purpose/baseline",
    "/spec/purpose/desired_outcomes",
    "/spec/purpose/exclusions",
    "/spec/purpose/problem",
    "/spec/quality_contract/evaluation_contract_ref",
    "/spec/quality_contract/subgroup_metrics",
    "/spec/quality_contract/task_metrics",
    "/spec/quality_contract/thresholds",
    "/spec/quality_contract/unacceptable_behaviors",
    "/spec/regulatory_nexus/activity_date",
    "/spec/regulatory_nexus/eu_nexus",
    "/spec/regulatory_nexus/nexus_ref",
    "/spec/regulatory_nexus/operator_roles",
    "/spec/risk_utility/decision_cost_model_ref",
    "/spec/risk_utility/high_materiality_unknowns",
    "/spec/risk_utility/risk_tier",
    "/spec/security_tenancy/audit_requirement",
    "/spec/security_tenancy/egress_policy",
    "/spec/security_tenancy/encryption",
    "/spec/security_tenancy/identity_provider",
    "/spec/security_tenancy/key_owner",
    "/spec/security_tenancy/privileged_actions",
    "/spec/security_tenancy/tenant_model",
    "/spec/security_tenancy/threat_actors",
    "/spec/security_tenancy/trust_boundaries",
    "/spec/stakeholders/accountable_owner",
    "/spec/stakeholders/affected_non_users",
    "/spec/stakeholders/domain_experts",
    "/spec/stakeholders/end_users",
    "/spec/stakeholders/operators",
    "/spec/stakeholders/reviewers",
)

ADMISSIBLE_INTENT_PATH_SET = frozenset(ADMISSIBLE_INTENT_PATHS)


def is_admissible_intent_path(path: str) -> bool:
    return path in ADMISSIBLE_INTENT_PATH_SET


def intent_section(path: str) -> str | None:
    """The ``spec`` section a JSON pointer addresses, or ``None`` outside ``/spec/``."""

    parts = path.split("/")
    if len(parts) < 3 or parts[0] != "" or parts[1] != "spec" or not parts[2]:
        return None
    return parts[2]
