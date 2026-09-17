# SPDX-License-Identifier: Apache-2.0
"""Deterministic brief interpretation, findings, and question ranking.

The interpreter has two inputs: the brief, which it maps without guessing, and an
optional interpretation proposal from a configured model. The proposal is untrusted
data. It is merged claim by claim under fixed rules (admissible path, bounded value,
explicit brief values win, schema re-validated after every claim), every value it
contributes carries ``model_proposed`` provenance, and every section it touches gains a
confirmation question. With no proposal the output is byte-identical to the interpreter
that shipped before the model path existed; a golden test pins that.
"""

import copy
import math
from dataclasses import dataclass
from typing import Any

from oak.contracts import (
    ContractValidationError,
    SchemaRegistry,
    intent_section,
    is_admissible_intent_path,
)
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
PRODUCTION_DATA_PATH = "/spec/data/extensions/oak.community~1production_data_permitted"
PRODUCTION_DATA_EXTENSION = "oak.community/production_data_permitted"
MODEL_PROPOSED = "model_proposed"
MODEL_QUESTION_PREFIX = "question.model."
PROPOSAL_REJECTED_CODE = "OAK-INT-PROPOSAL-REJECTED"
PROPOSAL_UNANSWERED_CODE = "OAK-INT-PROPOSAL-UNANSWERED"
# Value bounds for one proposed claim. The proposal schema bounds the document; these
# bound what may enter the canonical intent, independently of what the schema allows.
MAXIMUM_CLAIM_STRING = 4000
MAXIMUM_CLAIM_ITEMS = 64
MAXIMUM_CLAIM_ITEM_STRING = 400
MAXIMUM_CLAIM_KEY = 200
MAXIMUM_CLAIM_RATIONALE = 400
# Paths whose absence the deterministic interpreter already turns into a question. A
# proposal that lists one of them as unanswered opens that question; any other path is
# recorded as a finding and nothing else.
KNOWN_QUESTION_PATHS = {
    PRODUCTION_DATA_PATH: "question.production-use",
    "/spec/hardware": "question.model-hardware",
    "/spec/stakeholders/accountable_owner": "question.accountable-owner",
    "/spec/data/classifications/0": "question.data-classification",
    "/spec/decision/autonomy": "question.action-autonomy",
    "/spec/data/volume": "question.data-volume",
}


@dataclass(frozen=True, slots=True)
class SectionConfirmation:
    materiality: str
    blocking_stage: str
    blocking_gate: str
    question: str
    reason: str


# One confirmation question per spec section a proposal may touch. The invariant the
# service relies on: an intent with at least one ``model_proposed`` record always has at
# least one open question, whatever confidence the model reported.
SECTION_CONFIRMATION_TABLE: dict[str, SectionConfirmation] = {
    "purpose": SectionConfirmation(
        "high",
        "assess",
        "gate_1",
        "Confirm the purpose, outcomes and baseline a model proposed from the brief.",
        "The purpose frames every later constraint and candidate.",
    ),
    "stakeholders": SectionConfirmation(
        "critical",
        "assess",
        "gate_1",
        "Confirm the stakeholders and accountable owner a model proposed.",
        "Consequential decisions require named, confirmed stakeholders and an owner.",
    ),
    "decision": SectionConfirmation(
        "high",
        "assess",
        "gate_1",
        "Confirm the decision scope, autonomy and reversibility a model proposed.",
        "Autonomy and reversibility change oversight, testing and approval requirements.",
    ),
    "domain": SectionConfirmation(
        "medium",
        "assess",
        "gate_1",
        "Confirm the domain setting, sectors and languages a model proposed.",
        "Domain facts change the regulatory nexus, accessibility and eligible components.",
    ),
    "regulatory_nexus": SectionConfirmation(
        "critical",
        "assess",
        "gate_1",
        "Confirm the regulatory nexus a model proposed.",
        "The regulatory nexus determines mandatory obligations and gate blockers.",
    ),
    "risk_utility": SectionConfirmation(
        "high",
        "assess",
        "gate_1",
        "Confirm the risk tier and material unknowns a model proposed.",
        "The risk tier sets the assurance depth every later stage must meet.",
    ),
    "data": SectionConfirmation(
        "critical",
        "assess",
        "gate_1",
        "Confirm the data sources, classifications and handling a model proposed.",
        "The data boundary changes eligible components, controls and deployment eligibility.",
    ),
    "quality_contract": SectionConfirmation(
        "high",
        "solve",
        "gate_2",
        "Confirm the quality metrics and thresholds a model proposed.",
        "Quality thresholds decide which candidates pass evaluation.",
    ),
    "operational_contract": SectionConfirmation(
        "high",
        "solve",
        "gate_2",
        "Confirm the load, latency and availability targets a model proposed.",
        "Operational targets size capacity and rule candidates in or out.",
    ),
    "hardware": SectionConfirmation(
        "critical",
        "solve",
        "gate_2",
        "Confirm the target hardware and capacity a model proposed.",
        "Measured capacity and model compatibility determine feasibility.",
    ),
    "deployment_environment": SectionConfirmation(
        "critical",
        "solve",
        "gate_2",
        "Confirm the deployment modes, targets and network constraints a model proposed.",
        "Deployment mode and network constraints change eligible components and the target.",
    ),
    "security_tenancy": SectionConfirmation(
        "critical",
        "assess",
        "gate_1",
        "Confirm the identity, tenancy, trust-boundary and egress facts a model proposed.",
        "Security and tenancy facts change mandatory controls and the threat model.",
    ),
    "openness_sovereignty": SectionConfirmation(
        "high",
        "solve",
        "gate_2",
        "Confirm the software and model openness constraints a model proposed.",
        "Openness constraints decide licence eligibility for every catalogue component.",
    ),
    "economics": SectionConfirmation(
        "medium",
        "solve",
        "gate_2",
        "Confirm the budgets and cost constraints a model proposed.",
        "Budgets bound the candidate objective ranges and the Pareto frontier.",
    ),
    "organization": SectionConfirmation(
        "medium",
        "assess",
        "gate_1",
        "Confirm the team, skills and ownership facts a model proposed.",
        "Ownership and skills change operability and support assumptions.",
    ),
    "lifecycle": SectionConfirmation(
        "medium",
        "solve",
        "gate_2",
        "Confirm the lifetime, upgrade, retention and decommission policies a model proposed.",
        "Lifecycle policies change portability, archival and deletion obligations.",
    ),
}


_ABSENT = object()


@dataclass(frozen=True, slots=True)
class InterpretationResult:
    intent_document: dict[str, Any]
    assumptions: tuple[dict[str, Any], ...]
    questions: tuple[ClarificationQuestion, ...]
    findings: tuple[Finding, ...]


class DeterministicBriefInterpreter:
    """Map supported brief fields without guessing unstated values."""

    def interpret(
        self,
        brief: IngestedBrief,
        *,
        created_at: str,
        proposal: dict[str, Any] | None = None,
        registry: SchemaRegistry | None = None,
    ) -> InterpretationResult:
        """Interpret ``brief``; merge an already validated ``proposal`` when one is given.

        ``proposal`` must have passed ``validate_interpretation_proposal``. ``registry`` is
        required with a proposal: every applied claim is re-validated against the intent
        schema before the next one is considered.
        """

        if proposal is not None and registry is None:
            raise TypeError("a schema registry is required to merge an interpretation proposal")
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
            if proposal is not None and registry is not None:
                self._merge_proposal(
                    proposal, spec, provenance, questions, findings, registry, created_at
                )
            self._add_missing_questions(questions, findings, provenance)
        else:
            self._map_structured(brief.structured, spec, provenance, questions, findings)
            if proposal is not None and registry is not None:
                self._merge_proposal(
                    proposal, spec, provenance, questions, findings, registry, created_at
                )

        self._add_inferred_fields(spec, provenance)
        self._analyze(spec, provenance, questions, findings)
        # Every ranked question is persisted; interfaces present five per round.
        ranked = tuple(
            sorted(
                questions.values(),
                key=lambda question: (
                    MATERIALITY_ORDER[question.materiality],
                    question.rank_hint,
                    question.id,
                ),
            )
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
                question = self._missing_question("question.data-volume", "/spec/data/volume")
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
        if (
            isinstance(actions, list)
            and "task_types" not in spec["decision"]
            and not self._model_proposed(provenance, "/spec/decision/actions")
        ):
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
        provenance: dict[str, dict[str, Any]],
        questions: dict[str, ClarificationQuestion],
        findings: list[Finding],
    ) -> None:
        required = (
            ("question.data-classification", "/spec/data/classifications/0"),
            ("question.action-autonomy", "/spec/decision/autonomy"),
            ("question.production-use", PRODUCTION_DATA_PATH),
        )
        for question_id, path in required:
            # A model-proposed value is not missing; its section question covers it.
            if question_id not in questions and not self._model_proposed(provenance, path):
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
        questions: dict[str, ClarificationQuestion],
        findings: list[Finding],
        provenance: dict[str, dict[str, Any]],
    ) -> None:
        for question_id, path in (
            ("question.production-use", PRODUCTION_DATA_PATH),
            ("question.model-hardware", "/spec/hardware"),
            ("question.accountable-owner", "/spec/stakeholders/accountable_owner"),
            ("question.data-classification", "/spec/data/classifications/0"),
            ("question.action-autonomy", "/spec/decision/autonomy"),
        ):
            if DeterministicBriefInterpreter._model_proposed(provenance, path):
                continue
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
            "question.data-volume": (
                "What document volume and update cadence must the design support?",
                "Volume and freshness materially affect storage, indexing, and operating cost.",
                "high",
                "solve",
                "gate_2",
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
        evidence_refs: tuple[str, ...] = (),
    ) -> None:
        provenance[path] = {
            "source": source,
            "confidence": confidence,
            "rationale": rationale,
            "evidence_refs": list(evidence_refs),
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
        statements = {
            "inferred_from_brief": "A deterministic mapping supplied this provisional field.",
            "domain_default": "A deterministic mapping supplied this provisional field.",
            MODEL_PROPOSED: "A configured model proposed this value; confirm or correct it.",
        }
        assumptions: list[dict[str, Any]] = []
        for path, record in sorted(provenance.items()):
            statement = statements.get(str(record["source"]))
            if statement is None:
                continue
            identifier = path.removeprefix("/spec/").replace("/", ".").replace("~1", "-")
            assumptions.append(
                {
                    "id": f"assumption.{identifier}",
                    "path": path,
                    "statement": statement,
                    "source": record["source"],
                    "confidence": record["confidence"],
                    "materiality": record["materiality"],
                    "status": "proposed",
                }
            )
        return tuple(assumptions)

    # ----- optional proposal merge -------------------------------------------------

    def _merge_proposal(
        self,
        proposal: dict[str, Any],
        spec: dict[str, dict[str, Any]],
        provenance: dict[str, dict[str, Any]],
        questions: dict[str, ClarificationQuestion],
        findings: list[Finding],
        registry: SchemaRegistry,
        created_at: str,
    ) -> None:
        proposal_id = str(proposal["id"])
        touched: dict[str, float] = {}
        for claim in sorted(proposal["proposed_claims"], key=lambda item: str(item["path"])):
            path = str(claim["path"])
            value = copy.deepcopy(claim["value"])
            reason = self._claim_rejection(path, value, provenance)
            if reason is None:
                previous = self._apply_claim(spec, path, value)
                if not self._spec_is_valid(spec, registry, created_at):
                    self._restore_claim(spec, path, previous)
                    reason = "the proposed value does not satisfy the intent schema"
            if reason is not None:
                findings.append(
                    Finding(
                        code=PROPOSAL_REJECTED_CODE,
                        kind="rejected",
                        path=path,
                        message=reason,
                        materiality="low",
                        blocking_stage="interpret",
                    )
                )
                continue
            section = intent_section(path) or ""
            entry = SECTION_CONFIRMATION_TABLE[section]
            confidence = claim["confidence"]
            self._value_provenance(
                provenance,
                path,
                value,
                source=MODEL_PROPOSED,
                confidence=confidence,
                rationale=str(claim["rationale"])[:MAXIMUM_CLAIM_RATIONALE],
                materiality=entry.materiality,
                confirmation_required=True,
                evidence_refs=(proposal_id,),
            )
            touched[section] = min(touched.get(section, 1.0), float(confidence))
        for section in sorted(touched):
            question_id = f"{MODEL_QUESTION_PREFIX}{section}"
            if question_id in questions:
                continue
            entry = SECTION_CONFIRMATION_TABLE[section]
            questions[question_id] = ClarificationQuestion(
                id=question_id,
                path=f"/spec/{section}",
                question=entry.question,
                reason=entry.reason,
                materiality=entry.materiality,
                blocking_stage=entry.blocking_stage,
                blocking_gate=entry.blocking_gate,
                rank_hint=round(touched[section] * 10),
            )
        for unanswered in sorted({str(item) for item in proposal["unanswered_paths"]}):
            known_id = KNOWN_QUESTION_PATHS.get(unanswered)
            if known_id is None:
                findings.append(
                    Finding(
                        code=PROPOSAL_UNANSWERED_CODE,
                        kind="unknown",
                        path=unanswered,
                        message="The model reported that the brief does not answer this path.",
                        materiality="low",
                        blocking_stage="clarify",
                    )
                )
                continue
            if known_id in questions or self._model_proposed(provenance, unanswered):
                continue
            questions[known_id] = self._missing_question(known_id, unanswered)

    @staticmethod
    def _claim_rejection(
        path: str, value: Any, provenance: dict[str, dict[str, Any]]
    ) -> str | None:
        if not is_admissible_intent_path(path):
            return "the proposed path is not an admissible intent path"
        if DeterministicBriefInterpreter._occupied(provenance, path):
            return "the brief states this value; the proposal was not applied"
        if path == PRODUCTION_DATA_PATH and not isinstance(value, bool):
            # The one admissible extension slot is an open schema; its meaning is not.
            return "the production-data declaration must be a boolean"
        return DeterministicBriefInterpreter._bounds_reason(value)

    @staticmethod
    def _occupied(provenance: dict[str, dict[str, Any]], path: str) -> bool:
        prefix = f"{path}/"
        return any(record == path or record.startswith(prefix) for record in provenance)

    @staticmethod
    def _model_proposed(provenance: dict[str, dict[str, Any]], path: str) -> bool:
        prefix = f"{path}/"
        return any(
            (record_path == path or record_path.startswith(prefix))
            and record["source"] == MODEL_PROPOSED
            for record_path, record in provenance.items()
        )

    @staticmethod
    def _scalar_reason(value: Any, *, maximum_string: int) -> str | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return None if math.isfinite(value) else "the proposed number is not finite"
        if isinstance(value, str):
            if len(value) > maximum_string:
                return f"the proposed text exceeds {maximum_string} characters"
            return None
        return "the proposed value nests containers"

    @staticmethod
    def _bounds_reason(value: Any) -> str | None:
        if isinstance(value, list):
            if len(value) > MAXIMUM_CLAIM_ITEMS:
                return f"the proposed list exceeds {MAXIMUM_CLAIM_ITEMS} items"
            for item in value:
                reason = DeterministicBriefInterpreter._scalar_reason(
                    item, maximum_string=MAXIMUM_CLAIM_ITEM_STRING
                )
                if reason is not None:
                    return reason
            return None
        if isinstance(value, dict):
            if len(value) > MAXIMUM_CLAIM_ITEMS:
                return f"the proposed object exceeds {MAXIMUM_CLAIM_ITEMS} keys"
            for key, item in value.items():
                if not isinstance(key, str) or not key or len(key) > MAXIMUM_CLAIM_KEY:
                    return "the proposed object has an unusable key"
                reason = DeterministicBriefInterpreter._scalar_reason(
                    item, maximum_string=MAXIMUM_CLAIM_ITEM_STRING
                )
                if reason is not None:
                    return reason
            return None
        return DeterministicBriefInterpreter._scalar_reason(
            value, maximum_string=MAXIMUM_CLAIM_STRING
        )

    @staticmethod
    def _claim_slot(spec: dict[str, dict[str, Any]], path: str) -> tuple[dict[str, Any], str]:
        section = intent_section(path) or ""
        if path == PRODUCTION_DATA_PATH:
            return spec[section].setdefault("extensions", {}), PRODUCTION_DATA_EXTENSION
        return spec[section], path.rsplit("/", 1)[1]

    @classmethod
    def _apply_claim(cls, spec: dict[str, dict[str, Any]], path: str, value: Any) -> Any:
        container, key = cls._claim_slot(spec, path)
        previous = container.get(key, _ABSENT)
        container[key] = value
        return previous

    @classmethod
    def _restore_claim(cls, spec: dict[str, dict[str, Any]], path: str, previous: Any) -> None:
        container, key = cls._claim_slot(spec, path)
        if previous is _ABSENT:
            container.pop(key, None)
        else:
            container[key] = previous
        if path == PRODUCTION_DATA_PATH and not container:
            spec["data"].pop("extensions", None)

    @staticmethod
    def _spec_is_valid(
        spec: dict[str, dict[str, Any]], registry: SchemaRegistry, created_at: str
    ) -> bool:
        probe: dict[str, Any] = {
            "schema_version": "0.3.0",
            "id": "intent.proposal-probe",
            "version": "0.1.0",
            "status": "draft",
            "created_at": created_at,
            "supersedes": None,
            "spec": spec,
            "provenance": {},
            "evidence": [],
            "unresolved": [],
            "extensions": {},
        }
        try:
            registry.validate("system-intent.schema.json", probe)
        except (ContractValidationError, ValueError):
            return False
        return True

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
