# SPDX-License-Identifier: Apache-2.0
"""Deterministic brief interpretation, findings, and question ranking."""

from dataclasses import dataclass
from typing import Any

from oak.contracts import SchemaRegistry
from oak.domain import OAKError, canonical_json_bytes
from oak.domain.intake import ClarificationQuestion, Finding, IngestedBrief

SPEC_SECTIONS = (
    "purpose",
    "stakeholders",
    "decision",
    "domain",
    "regulatory_nexus",
    "risk_utility",
    "data",
    "quality_contract",
    "operational_contract",
    "hardware",
    "deployment_environment",
    "security_tenancy",
    "openness_sovereignty",
    "economics",
    "organization",
    "lifecycle",
)
MATERIALITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass(frozen=True, slots=True)
class InterpretationResult:
    intent_document: dict[str, Any]
    assumptions: tuple[dict[str, Any], ...]
    questions: tuple[ClarificationQuestion, ...]
    findings: tuple[Finding, ...]


class DeterministicBriefInterpreter:
    """Map supported brief fields without guessing unstated values."""

    def interpret(self, brief: IngestedBrief, *, created_at: str) -> InterpretationResult:
        spec: dict[str, dict[str, Any]] = {section: {} for section in SPEC_SECTIONS}
        provenance: dict[str, dict[str, Any]] = {}
        questions: dict[str, ClarificationQuestion] = {}
        findings: list[Finding] = []

        if brief.structured is None:
            problem = brief.content.decode("utf-8").strip()[:4000]
            if not problem:
                raise OAKError("OAK-INTAKE-EMPTY", "text brief has no usable content")
            spec["purpose"]["problem"] = problem
            self._provenance(
                provenance,
                "/spec/purpose/problem",
                source="explicit",
                confidence=1.0,
                rationale="Copied from the bounded text brief.",
                materiality="high",
                confirmation_required=True,
            )
            self._add_missing_questions(questions, findings)
        else:
            self._map_structured(brief.structured, spec, provenance, questions, findings)

        self._add_inferred_fields(spec, provenance)
        self._analyze(spec, questions, findings)
        ranked = tuple(
            sorted(
                questions.values(),
                key=lambda question: (MATERIALITY_ORDER[question.materiality], question.id),
            )[:5]
        )
        assumptions = self._assumptions(provenance)
        intent_id = self._derived_id("intent", brief.id)
        intent_document: dict[str, Any] = {
            "schema_version": "0.3.0",
            "id": intent_id,
            "version": "0.1.0",
            "status": "draft",
            "created_at": created_at,
            "supersedes": None,
            "spec": spec,
            "provenance": provenance,
            "evidence": [],
            "unresolved": [question.intent_document() for question in ranked],
            "extensions": {
                "oak.community/findings": [self._finding_document(finding) for finding in findings]
            },
        }
        self._verify_provenance(intent_document)
        return InterpretationResult(
            intent_document=intent_document,
            assumptions=assumptions,
            questions=ranked,
            findings=tuple(findings),
        )

    def _map_structured(
        self,
        document: dict[str, Any],
        spec: dict[str, dict[str, Any]],
        provenance: dict[str, dict[str, Any]],
        questions: dict[str, ClarificationQuestion],
        findings: list[Finding],
    ) -> None:
        purpose = self._object(document, "purpose")
        stakeholders = self._object(document, "stakeholders")
        decision = self._object(document, "decision")
        data = self._object(document, "data")
        quality = self._object(document, "quality")
        deployment = self._object(document, "deployment")
        hardware = self._object(document, "hardware")
        openness = self._object(document, "openness")

        self._copy_fields(
            purpose,
            spec["purpose"],
            provenance,
            section="purpose",
            fields=("problem", "desired_outcomes", "baseline"),
            materiality="high",
        )
        self._copy_fields(
            stakeholders,
            spec["stakeholders"],
            provenance,
            section="stakeholders",
            fields=("end_users", "operators", "affected_non_users"),
            materiality="high",
        )
        self._copy_fields(
            decision,
            spec["decision"],
            provenance,
            section="decision",
            fields=("actions", "autonomy", "reversibility"),
            materiality="high",
        )
        self._copy_fields(
            data,
            spec["data"],
            provenance,
            section="data",
            fields=("sources", "classifications"),
            materiality="high",
        )
        self._copy_fields(
            hardware,
            spec["hardware"],
            provenance,
            section="hardware",
            fields=("cpu_architectures", "ram_gib", "storage_gib"),
            materiality="critical",
        )

        priorities = quality.get("priorities")
        if priorities is not None:
            spec["quality_contract"]["task_metrics"] = priorities
            self._value_provenance(
                provenance,
                "/spec/quality_contract/task_metrics",
                priorities,
                source="explicit",
                confidence=1.0,
                rationale="Copied from brief quality priorities.",
                materiality="high",
            )
        modes = deployment.get("modes")
        if modes is not None:
            spec["deployment_environment"]["modes"] = modes
            self._value_provenance(
                provenance,
                "/spec/deployment_environment/modes",
                modes,
                source="explicit",
                confidence=1.0,
                rationale="Copied from brief deployment modes.",
                materiality="critical",
            )
        network = deployment.get("network")
        if network is not None:
            network_constraints = [network]
            spec["deployment_environment"]["network_constraints"] = network_constraints
            self._value_provenance(
                provenance,
                "/spec/deployment_environment/network_constraints",
                network_constraints,
                source="explicit",
                confidence=1.0,
                rationale="Copied from the brief network constraint.",
                materiality="critical",
            )
        software = openness.get("software")
        if software is not None:
            values = [software]
            spec["openness_sovereignty"]["allowed_software_classes"] = values
            self._value_provenance(
                provenance,
                "/spec/openness_sovereignty/allowed_software_classes",
                values,
                source="explicit",
                confidence=1.0,
                rationale="Copied from the brief software openness constraint.",
                materiality="high",
            )
        models = openness.get("models")
        if models is not None:
            values = [models]
            spec["openness_sovereignty"]["allowed_model_classes"] = values
            self._value_provenance(
                provenance,
                "/spec/openness_sovereignty/allowed_model_classes",
                values,
                source="explicit",
                confidence=1.0,
                rationale="Copied from the brief model openness constraint.",
                materiality="high",
            )

        production_permitted = data.get("production_data_permitted")
        if production_permitted is not None:
            extension_key = "oak.community/production_data_permitted"
            spec["data"].setdefault("extensions", {})[extension_key] = production_permitted
            path = "/spec/data/extensions/oak.community~1production_data_permitted"
            self._value_provenance(
                provenance,
                path,
                production_permitted,
                source="explicit",
                confidence=1.0,
                rationale="Copied from the brief production-data declaration.",
                materiality="critical",
                confirmation_required=True,
            )
            questions["question.production-use"] = ClarificationQuestion(
                id="question.production-use",
                path=path,
                question="Confirm whether production data is permitted for this design case.",
                reason="This changes the data boundary, controls, and deployment eligibility.",
                materiality="critical",
                blocking_stage="assess",
                blocking_gate="gate_1",
            )

        classifications = data.get("classifications")
        if isinstance(classifications, list) and classifications:
            questions["question.data-classification"] = ClarificationQuestion(
                id="question.data-classification",
                path="/spec/data/classifications/0",
                question="Confirm the highest data classification used by this design.",
                reason=(
                    "Data classification changes eligible components, handling, "
                    "and deployment controls."
                ),
                materiality="high",
                blocking_stage="assess",
                blocking_gate="gate_1",
            )
            self._set_confirmation_required(provenance, "/spec/data/classifications/0")
        autonomy = decision.get("autonomy")
        if isinstance(autonomy, str):
            questions["question.action-autonomy"] = ClarificationQuestion(
                id="question.action-autonomy",
                path="/spec/decision/autonomy",
                question="Confirm the maximum action autonomy permitted for this system.",
                reason="Autonomy changes human oversight, testing, and approval requirements.",
                materiality="high",
                blocking_stage="assess",
                blocking_gate="gate_1",
            )
            self._set_confirmation_required(provenance, "/spec/decision/autonomy")

        unknowns = document.get("unknowns", [])
        if not isinstance(unknowns, list) or any(not isinstance(item, str) for item in unknowns):
            raise OAKError("OAK-INTERPRET-BRIEF-TYPE", "brief unknowns must be a string array")
        for unknown in unknowns:
            folded = unknown.casefold()
            if "document" in folded or "update cadence" in folded:
                question = ClarificationQuestion(
                    id="question.data-volume",
                    path="/spec/data/volume",
                    question="What document volume and update cadence must the design support?",
                    reason=(
                        "Volume and freshness materially affect storage, indexing, "
                        "and operating cost."
                    ),
                    materiality="high",
                    blocking_stage="solve",
                    blocking_gate="gate_2",
                )
            else:
                question = ClarificationQuestion(
                    id="question.model-hardware",
                    path="/spec/hardware",
                    question="Which approved model licence and measured target hardware apply?",
                    reason=(
                        "Model eligibility and measured capacity can make generated-answer "
                        "variants infeasible."
                    ),
                    materiality="critical",
                    blocking_stage="solve",
                    blocking_gate="gate_2",
                )
            questions[question.id] = question
            findings.append(
                Finding(
                    code="OAK-INT-UNKNOWN-DECLARED",
                    kind="unknown",
                    path=question.path,
                    message="The brief explicitly declares a material unknown.",
                    materiality=question.materiality,
                    blocking_stage=question.blocking_stage,
                )
            )

    def _add_inferred_fields(
        self, spec: dict[str, dict[str, Any]], provenance: dict[str, dict[str, Any]]
    ) -> None:
        actions = spec["decision"].get("actions", [])
        if isinstance(actions, list):
            combined = " ".join(str(action).casefold() for action in actions)
            task_types: list[str] = []
            if "passage" in combined or "cite" in combined or "search" in combined:
                task_types.append("retrieval")
            if "draft" in combined or "answer" in combined:
                task_types.append("generation")
            if task_types:
                spec["decision"]["task_types"] = task_types
                self._value_provenance(
                    provenance,
                    "/spec/decision/task_types",
                    task_types,
                    source="inferred_from_brief",
                    confidence=0.8,
                    rationale="Mapped action words to the canonical task taxonomy.",
                    materiality="medium",
                    confirmation_required=True,
                )
        if "setting" not in spec["domain"]:
            spec["domain"]["setting"] = "Non-production local design review"
            self._provenance(
                provenance,
                "/spec/domain/setting",
                source="domain_default",
                confidence=0.7,
                rationale="Sprint 1 operates only as a local non-production design workflow.",
                materiality="medium",
                confirmation_required=True,
            )

    def _analyze(
        self,
        spec: dict[str, dict[str, Any]],
        questions: dict[str, ClarificationQuestion],
        findings: list[Finding],
    ) -> None:
        required = (
            ("question.data-classification", "/spec/data/classifications/0"),
            ("question.action-autonomy", "/spec/decision/autonomy"),
            (
                "question.production-use",
                "/spec/data/extensions/oak.community~1production_data_permitted",
            ),
        )
        for question_id, path in required:
            if question_id not in questions:
                question = self._missing_question(question_id, path)
                questions[question.id] = question
                findings.append(
                    Finding(
                        code="OAK-INT-MISSING-CRITICAL",
                        kind="missing",
                        path=path,
                        message="A consequential intent value is missing.",
                        materiality=question.materiality,
                        blocking_stage=question.blocking_stage,
                    )
                )

        sources = spec["data"].get("sources", [])
        production_permitted = (
            spec["data"].get("extensions", {}).get("oak.community/production_data_permitted")
            if isinstance(spec["data"].get("extensions", {}), dict)
            else None
        )
        if (
            production_permitted is False
            and isinstance(sources, list)
            and any("production" in str(source).casefold() for source in sources)
        ):
            findings.append(
                Finding(
                    code="OAK-INT-CONTRADICTION-PRODUCTION-DATA",
                    kind="contradiction",
                    path="/spec/data",
                    message=(
                        "Production sources conflict with the declared production-data boundary."
                    ),
                    materiality="critical",
                    blocking_stage="assess",
                )
            )

        for field in ("ram_gib", "storage_gib"):
            value = spec["hardware"].get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value <= 0:
                findings.append(
                    Finding(
                        code="OAK-INT-INFEASIBLE-CAPACITY",
                        kind="infeasible",
                        path=f"/spec/hardware/{field}",
                        message="Declared capacity must be greater than zero.",
                        materiality="critical",
                        blocking_stage="solve",
                    )
                )

    @staticmethod
    def _add_missing_questions(
        questions: dict[str, ClarificationQuestion], findings: list[Finding]
    ) -> None:
        for question_id, path in (
            (
                "question.production-use",
                "/spec/data/extensions/oak.community~1production_data_permitted",
            ),
            ("question.model-hardware", "/spec/hardware"),
            ("question.accountable-owner", "/spec/stakeholders/accountable_owner"),
            ("question.data-classification", "/spec/data/classifications/0"),
            ("question.action-autonomy", "/spec/decision/autonomy"),
        ):
            question = DeterministicBriefInterpreter._missing_question(question_id, path)
            questions[question.id] = question
            findings.append(
                Finding(
                    code="OAK-INT-MISSING-CRITICAL",
                    kind="missing",
                    path=path,
                    message="A consequential intent value is missing.",
                    materiality=question.materiality,
                    blocking_stage=question.blocking_stage,
                )
            )

    @staticmethod
    def _missing_question(question_id: str, path: str) -> ClarificationQuestion:
        definitions = {
            "question.production-use": (
                "Is production data permitted for this design case?",
                "The data boundary changes controls and deployment eligibility.",
                "critical",
                "assess",
                "gate_1",
            ),
            "question.model-hardware": (
                "Which measured hardware and model constraints apply?",
                "Capacity and model compatibility determine feasibility.",
                "critical",
                "solve",
                "gate_2",
            ),
            "question.accountable-owner": (
                "Who is the accountable owner for the intended outcome?",
                "Consequential decisions require a named accountable owner.",
                "critical",
                "assess",
                "gate_1",
            ),
            "question.data-classification": (
                "What is the highest data classification used by this design?",
                "Data classification changes handling and deployment controls.",
                "high",
                "assess",
                "gate_1",
            ),
            "question.action-autonomy": (
                "What is the maximum action autonomy permitted for this system?",
                "Autonomy changes oversight and approval requirements.",
                "high",
                "assess",
                "gate_1",
            ),
        }
        question, reason, materiality, stage, gate = definitions[question_id]
        return ClarificationQuestion(
            id=question_id,
            path=path,
            question=question,
            reason=reason,
            materiality=materiality,
            blocking_stage=stage,
            blocking_gate=gate,
        )

    @staticmethod
    def _copy_fields(
        source: dict[str, Any],
        destination: dict[str, Any],
        provenance: dict[str, dict[str, Any]],
        *,
        section: str,
        fields: tuple[str, ...],
        materiality: str,
    ) -> None:
        for field in fields:
            if field not in source:
                continue
            value = source[field]
            destination[field] = value
            DeterministicBriefInterpreter._value_provenance(
                provenance,
                f"/spec/{section}/{field}",
                value,
                source="explicit",
                confidence=1.0,
                rationale=f"Copied from brief field {section}.{field}.",
                materiality=materiality,
            )

    @staticmethod
    def _object(document: dict[str, Any], key: str) -> dict[str, Any]:
        value = document.get(key, {})
        if not isinstance(value, dict):
            raise OAKError("OAK-INTERPRET-BRIEF-TYPE", f"brief field {key} must be an object")
        return value

    @staticmethod
    def _value_provenance(
        provenance: dict[str, dict[str, Any]],
        base_path: str,
        value: Any,
        **record: Any,
    ) -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                DeterministicBriefInterpreter._value_provenance(
                    provenance, f"{base_path}/{index}", item, **record
                )
            return
        if isinstance(value, dict):
            for key, item in value.items():
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                DeterministicBriefInterpreter._value_provenance(
                    provenance, f"{base_path}/{escaped}", item, **record
                )
            return
        DeterministicBriefInterpreter._provenance(provenance, base_path, **record)

    @staticmethod
    def _provenance(
        provenance: dict[str, dict[str, Any]],
        path: str,
        *,
        source: str,
        confidence: float,
        rationale: str,
        materiality: str,
        confirmation_required: bool = False,
    ) -> None:
        provenance[path] = {
            "source": source,
            "confidence": confidence,
            "rationale": rationale,
            "evidence_refs": [],
            "materiality": materiality,
            "confirmation_required": confirmation_required,
            "confirmed_by": None,
            "confirmed_at": None,
        }

    @staticmethod
    def _set_confirmation_required(provenance: dict[str, dict[str, Any]], path: str) -> None:
        record = provenance.get(path)
        if record is not None:
            record["confirmation_required"] = True

    @staticmethod
    def _assumptions(
        provenance: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Any], ...]:
        assumptions: list[dict[str, Any]] = []
        for path, record in sorted(provenance.items()):
            if record["source"] not in {"inferred_from_brief", "domain_default"}:
                continue
            identifier = path.removeprefix("/spec/").replace("/", ".").replace("~1", "-")
            assumptions.append(
                {
                    "id": f"assumption.{identifier}",
                    "path": path,
                    "statement": "A deterministic mapping supplied this provisional field.",
                    "source": record["source"],
                    "confidence": record["confidence"],
                    "materiality": record["materiality"],
                    "status": "proposed",
                }
            )
        return tuple(assumptions)

    @staticmethod
    def _verify_provenance(intent: dict[str, Any]) -> None:
        populated = set(DeterministicBriefInterpreter._scalar_paths(intent["spec"], "/spec"))
        recorded = set(intent["provenance"])
        if populated != recorded:
            raise OAKError(
                "OAK-INTENT-PROVENANCE",
                "every populated scalar intent value must have exactly one provenance record",
            )

    @staticmethod
    def _scalar_paths(value: Any, path: str) -> list[str]:
        if isinstance(value, dict):
            paths: list[str] = []
            for key, child in value.items():
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                paths.extend(
                    DeterministicBriefInterpreter._scalar_paths(child, f"{path}/{escaped}")
                )
            return paths
        if isinstance(value, list):
            paths = []
            for index, child in enumerate(value):
                paths.extend(DeterministicBriefInterpreter._scalar_paths(child, f"{path}/{index}"))
            return paths
        return [path]

    @staticmethod
    def _derived_id(prefix: str, brief_id: str) -> str:
        suffix = brief_id.removeprefix("brief.")
        return f"{prefix}.{suffix}"

    @staticmethod
    def _finding_document(finding: Finding) -> dict[str, str]:
        return {
            "code": finding.code,
            "kind": finding.kind,
            "path": finding.path,
            "message": finding.message,
            "materiality": finding.materiality,
            "blocking_stage": finding.blocking_stage,
        }


def validate_interpretation_proposal(
    proposal: dict[str, Any], registry: SchemaRegistry, maximum_output_bytes: int
) -> dict[str, Any]:
    try:
        encoded = canonical_json_bytes(proposal)
    except (TypeError, ValueError) as error:
        raise OAKError(
            "OAK-INTERPRETER-MALFORMED", "optional proposal is not canonical JSON data"
        ) from error
    if len(encoded) > maximum_output_bytes:
        raise OAKError("OAK-INTERPRETER-OUTPUT-LIMIT", "proposal output exceeds its limit")
    try:
        registry.validate("interpretation-proposal.schema.json", proposal)
    except ValueError as error:
        raise OAKError(
            "OAK-INTERPRETER-MALFORMED", "optional proposal failed validation"
        ) from error
    claim_paths = [str(claim["path"]) for claim in proposal["proposed_claims"]]
    if len(claim_paths) != len(set(claim_paths)):
        raise OAKError("OAK-INTERPRETER-MALFORMED", "optional proposal repeats a claim path")
    return proposal


def verify_intent_provenance(intent: dict[str, Any]) -> None:
    """Apply the canonical scalar-provenance invariant to an intent document."""

    DeterministicBriefInterpreter._verify_provenance(intent)
