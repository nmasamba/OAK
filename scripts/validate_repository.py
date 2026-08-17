# SPDX-License-Identifier: Apache-2.0
"""Validate schemas/examples and repository-generated invariants."""

import json
import subprocess
from pathlib import Path
from typing import Any

from oak.contracts import CanonicalDocument, SchemaRegistry, load_yaml_document

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_BY_SCHEMA = {
    "architecture-candidate.schema.json": "example-architecture-candidate.yaml",
    "architecture-decision.schema.json": "example-architecture-decision.yaml",
    "architecture-pattern.schema.json": "example-architecture-pattern.yaml",
    "assurance-plan.schema.json": "example-assurance-plan.yaml",
    "audit-event.schema.json": "example-audit-event.yaml",
    "change-proposal.schema.json": "example-change-proposal.yaml",
    "component-manifest.schema.json": "example-component.yaml",
    "catalogue-snapshot.schema.json": "example-catalogue-snapshot.yaml",
    "confirmation-answers.schema.json": "briefs/public-manual-qa-answers.yaml",
    "decision-cost-model.schema.json": "example-decision-cost-model.yaml",
    "deployment-bundle.schema.json": "example-deployment-bundle.yaml",
    "design-case.schema.json": "example-design-case.yaml",
    "evaluation-contract.schema.json": "example-evaluation-contract.yaml",
    "evaluation-result.schema.json": "example-evaluation-result.yaml",
    "interpretation-proposal.schema.json": "example-interpretation-proposal.yaml",
    "obligation-control-mapping.schema.json": "example-obligation-control-mapping.yaml",
    "regulatory-nexus.schema.json": "example-regulatory-nexus.yaml",
    "regulatory-profile.schema.json": "example-eu-regulatory-profile.yaml",
    "runner-plan.schema.json": "example-runner-plan.yaml",
    "review-artifact.schema.json": "example-review-artifact.yaml",
    "source-record.schema.json": "example-source-record.yaml",
    "system-intent.schema.json": "example-intent.yaml",
    "target-profile.schema.json": "targets/local-fixture.yaml",
    "workspace-manifest.schema.json": "example-workspace-manifest.yaml",
}


def _load_yaml(path: Path) -> dict[str, Any]:
    return load_yaml_document(path.read_text(encoding="utf-8"))


def validate_contracts() -> None:
    registry = SchemaRegistry.from_directory(ROOT / "schemas")
    expected = set(registry.names) - {"common.schema.json"}
    if set(EXAMPLE_BY_SCHEMA) != expected:
        missing = sorted(expected - set(EXAMPLE_BY_SCHEMA))
        extra = sorted(set(EXAMPLE_BY_SCHEMA) - expected)
        raise ValueError(f"schema/example map drift: missing={missing}, extra={extra}")
    for schema_name, example_name in sorted(EXAMPLE_BY_SCHEMA.items()):
        source = _load_yaml(ROOT / "examples" / example_name)
        runtime = CanonicalDocument.model_validate(source)
        round_tripped = json.loads(runtime.model_dump_json())
        if round_tripped != source:
            raise ValueError(f"runtime semantic drift for {example_name}")
        registry.validate(schema_name, round_tripped)


def main() -> int:
    validate_contracts()
    subprocess.run(
        ["python", "scripts/generate_openapi.py", "--check"],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(["python", "tools/check_repository.py"], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
