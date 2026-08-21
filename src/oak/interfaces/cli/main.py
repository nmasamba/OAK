# SPDX-License-Identifier: Apache-2.0
"""Local-first command-line entrypoint."""

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import unicodedata
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, NoReturn

import typer
import yaml

if TYPE_CHECKING:
    from oak.interfaces.cli.remote import RemoteClient

from oak.application import (
    CandidatePlanningService,
    CommandContext,
    DesignCaseService,
    ReleaseService,
)
from oak.bootstrap import (
    create_candidate_planning_service,
    create_design_case_service,
    create_system_information_service,
)
from oak.contracts import ContractValidationError, load_json_document, load_yaml_document
from oak.domain import OAKError


class OutputFormat(StrEnum):
    HUMAN = "human"
    JSON = "json"
    YAML = "yaml"
    TABLE = "table"


app = typer.Typer(
    name="oak",
    help="Design, evaluate, and plan AI systems with OAK Community.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        information = create_system_information_service().get_information()
        typer.echo(information.version)
        raise typer.Exit()


_REMOTE_SERVER: str | None = None


@app.callback()
def root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the OAK Community version and exit.",
        ),
    ] = False,
    server: Annotated[
        str | None,
        typer.Option(
            "--server",
            envvar="OAK_SERVER",
            help="Remote control-plane URL; run this command over REST instead of the "
            "local workspace.",
        ),
    ] = None,
) -> None:
    """OAK Community command group."""

    global _REMOTE_SERVER
    _REMOTE_SERVER = server


def _remote() -> "RemoteClient | None":
    if _REMOTE_SERVER is None:
        return None
    from oak.interfaces.cli.remote import RemoteClient

    return RemoteClient(_REMOTE_SERVER, actor=os.getenv("OAK_ACTOR"))


def _require_local(command: str) -> None:
    if _REMOTE_SERVER is not None:
        raise OAKError(
            "OAK-REMOTE-UNSUPPORTED",
            f"{command} is local-only and is not available in remote mode",
        )


def _remote_case_id(design_case: str | None) -> str:
    if design_case is None:
        raise OAKError(
            "OAK-REMOTE-CASE-REQUIRED",
            "remote mode requires an explicit design-case identifier",
        )
    return design_case


@app.command("init")
def init_workspace(
    directory: Annotated[Path, typer.Argument(help="Directory to initialize.")] = Path("."),
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.HUMAN,
) -> None:
    """Initialize an atomic local OAK workspace."""

    try:
        if _REMOTE_SERVER is not None:
            raise OAKError(
                "OAK-REMOTE-UNSUPPORTED",
                "init is local-only; a remote case is created by oak design",
            )
        root_path = directory.absolute()
        workspace_id = _workspace_id(root_path)
        create_design_case_service(root_path).initialize(
            workspace_id=workspace_id,
            tenant_id="local",
            created_at=_now(),
        )
        _emit(
            {
                "workspace_id": workspace_id,
                "directory": str(root_path),
                "status": "initialized",
            },
            output,
            human=f"Initialized {workspace_id} in {root_path}",
        )
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command()
def design(
    brief: Annotated[Path, typer.Argument(help="YAML, JSON, Markdown, or text brief.")],
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.HUMAN,
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Stable retry key; derived from input by default."),
    ] = None,
) -> None:
    """Ingest and deterministically interpret a local brief."""

    try:
        remote = _remote()
        if remote is not None:
            _remote_design(remote, brief, idempotency_key, output)
            return
        service = _workspace_service()
        result = service.design(
            brief,
            _context(idempotency_key=idempotency_key, expected_version=None),
        )
        if result.intent is None:
            raise OAKError("OAK-INTENT-NOT-FOUND", "interpreted design has no intent artifact")
        _emit(
            result.intent,
            output,
            human=(
                f"Design case {result.case['id']}@{result.case['version']} is "
                f"{result.case['status']} with {len(result.case['unresolved_questions'])} questions"
                + (" (idempotent retry)" if result.duplicate else "")
            ),
        )
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


def _remote_design(
    remote: "RemoteClient",
    brief: Path,
    idempotency_key: str | None,
    output: OutputFormat,
) -> None:
    from oak.interfaces.cli import remote as remote_mode

    content = _read_bounded_file(brief, prefix="OAK-INTAKE", maximum_bytes=262_144)
    identity = idempotency_key or remote_mode.content_identity(content)
    created = remote.create_design_case(
        original_name=brief.name,
        content=content.decode("utf-8"),
        idempotency_key=remote_mode.derived_key("create", identity),
    )
    interpreted = remote.interpret(
        str(created["case"]["id"]),
        expected_version=str(created["case"]["version"]),
        idempotency_key=idempotency_key or remote_mode.derived_key("interpret", identity),
    )
    case = interpreted["case"]
    intent = interpreted.get("intent")
    if not isinstance(intent, dict):
        raise OAKError("OAK-INTENT-NOT-FOUND", "interpreted design has no intent artifact")
    _emit(
        intent,
        output,
        human=(
            f"Design case {case['id']}@{case['version']} is "
            f"{case['status']} with {len(case['unresolved_questions'])} questions"
            + (" (idempotent retry)" if interpreted.get("duplicate") else "")
        ),
    )


@app.command()
def questions(
    design_case: Annotated[
        str | None, typer.Argument(help="Optional design-case identifier.")
    ] = None,
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.HUMAN,
) -> None:
    """List the current deterministic clarification questions."""

    try:
        remote = _remote()
        if remote is not None:
            case = remote.get_case(_remote_case_id(design_case))["case"]
            document = {
                "case_id": str(case["id"]),
                "case_version": str(case["version"]),
                "status": str(case["status"]),
                "questions": list(case["unresolved_questions"]),
            }
            human = "\n".join(
                f"{question['id']}: {question['question']} [{question['status']}]"
                for question in document["questions"]
            )
            _emit(document, output, human=human or "No open questions")
            return
        result = _workspace_service().questions()
        if design_case is not None and design_case != result.case_id:
            raise OAKError("OAK-CASE-NOT-FOUND", "requested design case is not current")
        document = result.to_document()
        human = "\n".join(
            f"{question['id']}: {question['question']} [{question['status']}]"
            for question in result.questions
        )
        _emit(document, output, human=human or "No open questions")
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command()
def confirm(
    design_case: Annotated[
        str | None, typer.Argument(help="Optional design-case identifier.")
    ] = None,
    answers: Annotated[
        Path | None, typer.Option("--answers", help="Bounded YAML or JSON answers.")
    ] = None,
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.HUMAN,
    idempotency_key: Annotated[
        str | None,
        typer.Option(
            "--idempotency-key", help="Stable retry key; derived from answers by default."
        ),
    ] = None,
) -> None:
    """Create immutable confirmation successors for current claims."""

    try:
        if answers is None:
            raise OAKError("OAK-CONFIRM-ANSWERS", "--answers is required")
        remote = _remote()
        if remote is not None:
            from oak.interfaces.cli import remote as remote_mode

            case_id = _remote_case_id(design_case)
            answers_document = _load_answers(answers)
            result_document = remote.confirm(
                case_id,
                answers_document,
                expected_version=remote.current_case_version(case_id),
                idempotency_key=idempotency_key
                or remote_mode.derived_key(
                    "confirm", remote_mode.document_identity(answers_document)
                ),
            )
            remote_case = result_document["case"]
            _emit(
                {
                    "case": remote_case,
                    "intent": result_document.get("intent"),
                    "duplicate": result_document.get("duplicate", False),
                },
                output,
                human=(
                    f"Recorded {remote_case['id']}@{remote_case['version']} as "
                    f"{remote_case['status']}"
                    + (" (idempotent retry)" if result_document.get("duplicate") else "")
                ),
            )
            return
        service = _workspace_service()
        current = service.current().case
        if design_case is not None and design_case != current["id"]:
            raise OAKError("OAK-CASE-NOT-FOUND", "requested design case is not current")
        result = service.confirm(
            _load_answers(answers),
            _context(
                idempotency_key=idempotency_key,
                expected_version=str(current["version"]),
            ),
        )
        document = {
            "case": result.case,
            "intent": result.intent,
            "duplicate": result.duplicate,
        }
        _emit(
            document,
            output,
            human=(
                f"Recorded {result.case['id']}@{result.case['version']} as "
                f"{result.case['status']}" + (" (idempotent retry)" if result.duplicate else "")
            ),
        )
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command()
def candidates(
    design_case: Annotated[
        str | None, typer.Argument(help="Optional design-case identifier.")
    ] = None,
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.TABLE,
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Stable retry key; derived by default."),
    ] = None,
) -> None:
    """Generate and compare deterministic architecture candidates."""

    try:
        remote = _remote()
        if remote is not None:
            from oak.interfaces.cli import remote as remote_mode

            case_id = _remote_case_id(design_case)
            version = remote.current_case_version(case_id)
            submission = remote.generate_candidates(
                case_id,
                expected_version=version,
                idempotency_key=idempotency_key
                or remote_mode.derived_key("candidates", f"{case_id}@{version}"),
            )
            operation = remote.wait_for_operation(str(submission["operation_id"]))
            document = operation["result"]
            if not isinstance(document, dict) or "candidates" not in document:
                raise OAKError("OAK-REMOTE-PROTOCOL", "remote operation result is invalid")
            _emit(
                document,
                output,
                human=_candidate_table(tuple(document["candidates"])),
            )
            return
        current = _workspace_service().current().case
        if design_case is not None and design_case != current["id"]:
            raise OAKError("OAK-CASE-NOT-FOUND", "requested design case is not current")
        result = _planning_service().candidates(
            _context(
                idempotency_key=idempotency_key,
                expected_version=str(current["version"]),
            )
        )
        document = result.to_document()
        table = _candidate_table(result.candidates)
        _emit(document, output, human=table)
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command()
def evaluate(
    candidate_id: Annotated[str, typer.Argument(help="Candidate identifier.")],
    design_case: Annotated[
        str | None,
        typer.Option("--case", help="Design-case identifier; required in remote mode."),
    ] = None,
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.HUMAN,
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Stable retry key; derived by default."),
    ] = None,
) -> None:
    """Run the deterministic reference evaluation contract."""

    try:
        remote = _remote()
        if remote is not None:
            from oak.interfaces.cli import remote as remote_mode

            case_id = _remote_case_id(design_case)
            version = remote.current_case_version(case_id)
            submission = remote.evaluate_candidate(
                candidate_id,
                case_id=case_id,
                expected_version=version,
                idempotency_key=idempotency_key
                or remote_mode.derived_key("evaluate", f"{case_id}@{version}:{candidate_id}"),
            )
            operation = remote.wait_for_operation(str(submission["operation_id"]))
            document = operation["result"]
            if not isinstance(document, dict) or "evaluation" not in document:
                raise OAKError("OAK-REMOTE-PROTOCOL", "remote operation result is invalid")
            _emit(
                document,
                output,
                human=(
                    f"Evaluation {document['evaluation']['id']} is "
                    f"{document['evaluation']['status']}"
                    + (" (idempotent retry)" if document.get("duplicate") else "")
                ),
            )
            return
        current = _workspace_service().current().case
        if design_case is not None and design_case != current["id"]:
            raise OAKError("OAK-CASE-NOT-FOUND", "requested design case is not current")
        result = _planning_service().evaluate(
            candidate_id,
            _context(
                idempotency_key=idempotency_key,
                expected_version=str(current["version"]),
            ),
        )
        _emit(
            result.to_document(),
            output,
            human=(
                f"Evaluation {result.evaluation['id']} is {result.evaluation['status']}"
                + (" (idempotent retry)" if result.duplicate else "")
            ),
        )
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command()
def select(
    candidate_id: Annotated[str, typer.Argument(help="Candidate identifier.")],
    rationale_file: Annotated[
        Path | None, typer.Option("--rationale-file", help="Bounded UTF-8 rationale file.")
    ] = None,
    design_case: Annotated[
        str | None,
        typer.Option("--case", help="Design-case identifier; required in remote mode."),
    ] = None,
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.HUMAN,
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Stable retry key; derived by default."),
    ] = None,
) -> None:
    """Record an immutable owner-bound candidate decision."""

    try:
        if rationale_file is None:
            raise OAKError("OAK-SELECT-RATIONALE", "--rationale-file is required")
        remote = _remote()
        if remote is not None:
            from oak.interfaces.cli import remote as remote_mode

            case_id = _remote_case_id(design_case)
            rationale = _load_bounded_text(rationale_file, code="OAK-SELECT-RATIONALE")
            version = remote.current_case_version(case_id)
            document = remote.select_candidate(
                case_id,
                candidate_id=candidate_id,
                rationale=rationale,
                expected_version=version,
                idempotency_key=idempotency_key
                or remote_mode.derived_key("select", f"{case_id}@{version}:{candidate_id}"),
            )
            _emit(
                document,
                output,
                human=(
                    f"Selected {candidate_id} in {document['decision']['id']}"
                    + (" (idempotent retry)" if document.get("duplicate") else "")
                ),
            )
            return
        current = _workspace_service().current().case
        if design_case is not None and design_case != current["id"]:
            raise OAKError("OAK-CASE-NOT-FOUND", "requested design case is not current")
        result = _planning_service().select(
            candidate_id,
            _load_bounded_text(rationale_file, code="OAK-SELECT-RATIONALE"),
            _context(
                idempotency_key=idempotency_key,
                expected_version=str(current["version"]),
            ),
        )
        _emit(
            result.to_document(),
            output,
            human=(
                f"Selected {candidate_id} in {result.decision['id']}"
                + (" (idempotent retry)" if result.duplicate else "")
            ),
        )
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command()
def assure(
    candidate_id: Annotated[str, typer.Argument(help="Selected candidate identifier.")],
    output: Annotated[
        Path | None, typer.Option("--output", help="New assurance output directory.")
    ] = None,
    design_case: Annotated[
        str | None,
        typer.Option("--case", help="Design-case identifier; required in remote mode."),
    ] = None,
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Stable retry key; derived by default."),
    ] = None,
) -> None:
    """Create the selected candidate's deterministic assurance plan."""

    try:
        if output is None:
            raise OAKError("OAK-ASSURE-OUTPUT", "--output is required")
        remote = _remote()
        if remote is not None:
            from oak.interfaces.cli import remote as remote_mode

            case_id = _remote_case_id(design_case)
            version = remote.current_case_version(case_id)
            document = remote.create_assurance_plan(
                case_id,
                candidate_id=candidate_id,
                expected_version=version,
                idempotency_key=idempotency_key
                or remote_mode.derived_key("assure", f"{case_id}@{version}:{candidate_id}"),
            )
            assurance_plan = document["assurance_plan"]
            remote_mode.verify_document_digest(
                assurance_plan,
                document["case"].get("assurance_plan_ref"),
                name="assurance-plan.json",
            )
            _write_output_directory(output, {"assurance-plan.json": assurance_plan})
            typer.echo(
                f"Wrote {assurance_plan['id']} to {output}"
                + (" (idempotent retry)" if document.get("duplicate") else "")
            )
            return
        current = _workspace_service().current().case
        if design_case is not None and design_case != current["id"]:
            raise OAKError("OAK-CASE-NOT-FOUND", "requested design case is not current")
        result = _planning_service().assure(
            candidate_id,
            _context(
                idempotency_key=idempotency_key,
                expected_version=str(current["version"]),
            ),
        )
        _write_output_directory(
            output,
            {"assurance-plan.json": result.assurance_plan},
        )
        typer.echo(
            f"Wrote {result.assurance_plan['id']} to {output}"
            + (" (idempotent retry)" if result.duplicate else "")
        )
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command()
def plan(
    candidate_id: Annotated[str, typer.Argument(help="Selected candidate identifier.")],
    target: Annotated[
        Path | None, typer.Option("--target", help="Bounded non-production target profile.")
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", help="New compiled review directory.")
    ] = None,
    design_case: Annotated[
        str | None,
        typer.Option("--case", help="Design-case identifier; required in remote mode."),
    ] = None,
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Stable retry key; derived by default."),
    ] = None,
) -> None:
    """Compile canonical review files and a non-executing typed runner plan."""

    try:
        if target is None or output is None:
            raise OAKError("OAK-PLAN-INPUT", "--target and --output are required")
        remote = _remote()
        if remote is not None:
            _remote_plan(remote, candidate_id, target, output, design_case, idempotency_key)
            return
        current = _workspace_service().current().case
        if design_case is not None and design_case != current["id"]:
            raise OAKError("OAK-CASE-NOT-FOUND", "requested design case is not current")
        result = _planning_service().plan(
            candidate_id,
            target,
            _context(
                idempotency_key=idempotency_key,
                expected_version=str(current["version"]),
            ),
        )
        _write_output_directory(
            output,
            {
                "architecture-decision.json": result.decision,
                "assurance-plan.json": result.assurance_plan,
                "semantic-manifest.json": result.semantic_manifest,
                "deployment-bundle.json": result.deployment_bundle,
                "runner-plan.json": result.runner_plan,
            },
        )
        typer.echo(
            f"Compiled {result.deployment_bundle['id']} to {output}; no target action was invoked"
            + (" (idempotent retry)" if result.duplicate else "")
        )
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


def _remote_plan(
    remote: "RemoteClient",
    candidate_id: str,
    target: Path,
    output: Path,
    design_case: str | None,
    idempotency_key: str | None,
) -> None:
    from oak.interfaces.cli import remote as remote_mode

    case_id = _remote_case_id(design_case)
    target_document = _load_bounded_mapping(target, prefix="OAK-PLAN-TARGET")
    version = remote.current_case_version(case_id)
    submission = remote.compile_bundle(
        case_id,
        candidate_id=candidate_id,
        target=target_document,
        expected_version=version,
        idempotency_key=idempotency_key
        or remote_mode.derived_key("plan", f"{case_id}@{version}:{candidate_id}"),
    )
    operation = remote.wait_for_operation(str(submission["operation_id"]))
    document = operation["result"]
    if not isinstance(document, dict) or "deployment_bundle" not in document:
        raise OAKError("OAK-REMOTE-PROTOCOL", "remote operation result is invalid")
    case = document["case"]
    extensions = case.get("extensions", {})
    references = {
        "architecture-decision.json": extensions.get("oak.community/selection_decision_ref"),
        "assurance-plan.json": case.get("assurance_plan_ref"),
        "semantic-manifest.json": extensions.get("oak.community/semantic_manifest_ref"),
        "deployment-bundle.json": case.get("deployment_bundle_ref"),
        "runner-plan.json": case.get("runner_plan_ref"),
    }
    files = {
        "architecture-decision.json": document["decision"],
        "assurance-plan.json": document["assurance_plan"],
        "semantic-manifest.json": document["semantic_manifest"],
        "deployment-bundle.json": document["deployment_bundle"],
        "runner-plan.json": document["runner_plan"],
    }
    for name, file_document in files.items():
        remote_mode.verify_document_digest(file_document, references[name], name=name)
    _write_output_directory(output, files)
    typer.echo(
        f"Compiled {document['deployment_bundle']['id']} to {output}; "
        "no target action was invoked"
        + (" (idempotent retry)" if document.get("duplicate") else "")
    )


@app.command("export")
def export_workspace(
    design_case: Annotated[
        str | None, typer.Argument(help="Optional design-case identifier.")
    ] = None,
    output: Annotated[Path | None, typer.Option("--output", help="New export directory.")] = None,
) -> None:
    """Export a digest-verified portable workspace."""

    try:
        if output is None:
            raise OAKError("OAK-EXPORT-OUTPUT", "--output is required")
        remote = _remote()
        if remote is not None:
            from oak.interfaces.cli import remote as remote_mode

            case_id = _remote_case_id(design_case)
            export_document = remote.export_case(case_id)
            remote_mode.write_export_directory(output, export_document)
            reference = export_document["manifest"]["current_case_ref"]
            typer.echo(f"Exported {reference['id']}@{reference['version']} to {output}")
            return
        service = _workspace_service()
        current = service.current().case
        if design_case is not None and design_case != current["id"]:
            raise OAKError("OAK-CASE-NOT-FOUND", "requested design case is not current")
        service.export_to(output)
        typer.echo(f"Exported {current['id']}@{current['version']} to {output}")
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command("import")
def import_workspace(
    source: Annotated[Path, typer.Argument(help="Export directory to import.")],
    directory: Annotated[Path, typer.Option("--directory", help="New workspace directory.")] = Path(
        "."
    ),
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.HUMAN,
) -> None:
    """Import a validated export into a new local workspace."""

    try:
        remote = _remote()
        if remote is not None:
            from oak.interfaces.cli import remote as remote_mode

            export_document = remote_mode.read_export_directory(source)
            result_document = remote.import_case(
                export_document,
                idempotency_key=remote_mode.derived_key(
                    "import", remote_mode.document_identity(export_document)
                ),
            )
            case = result_document["case"]
            _emit(
                {"case": case, "intent": result_document.get("intent")},
                output,
                human=f"Imported {case['id']}@{case['version']}",
            )
            return
        root_path = directory.absolute()
        service = create_design_case_service(root_path)
        service.import_from(source.absolute())
        current = service.current()
        _emit(
            {"case": current.case, "intent": current.intent},
            output,
            human=(f"Imported {current.case['id']}@{current.case['version']} into {root_path}"),
        )
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Address to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535, help="Port to bind.")] = 8080,
    allow_non_loopback: Annotated[
        bool,
        typer.Option(
            "--allow-non-loopback",
            help="Acknowledge that the development API has no authentication.",
        ),
    ] = False,
) -> None:
    """Serve the read-only local API harness."""

    if _REMOTE_SERVER is not None:
        _abort(OAKError("OAK-REMOTE-UNSUPPORTED", "serve is local-only"))

    from oak.interfaces.api.server import run_server

    try:
        run_server(host=host, port=port, allow_non_loopback=allow_non_loopback)
    except ValueError as error:
        typer.echo(f"OAK-SAFE-BIND: {error}", err=True)
        raise typer.Exit(code=2) from error


mcp_app = typer.Typer(
    name="mcp",
    help="Bounded typed Model Context Protocol interface.",
    no_args_is_help=True,
)
app.add_typer(mcp_app, name="mcp")


@mcp_app.command("serve")
def mcp_serve() -> None:
    """Serve the bounded design/read MCP tool set on stdio."""

    if _REMOTE_SERVER is not None:
        _abort(OAKError("OAK-REMOTE-UNSUPPORTED", "mcp serve is local-only"))

    from oak.interfaces.mcp.server import main as run_mcp_server

    run_mcp_server()


@app.command()
def keys(
    action: Annotated[str, typer.Argument(help="init or show.")],
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.HUMAN,
) -> None:
    """Create or inspect the local development signing identities."""

    try:
        _require_local("keys")
        from oak.bootstrap import initialize_local_trust

        if action not in {"init", "show"}:
            raise OAKError("OAK-KEYS-ACTION", "keys action must be init or show")
        identities = initialize_local_trust()
        _emit(
            {"identities": list(identities)},
            output,
            human="\n".join(
                f"{identity['role']}: {identity['key_id']} ({identity['trust_level']})"
                for identity in identities
            ),
        )
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command()
def sign(
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.HUMAN,
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Stable retry key; derived by default."),
    ] = None,
) -> None:
    """Sign the compiled draft runner plan into an immutable envelope binding."""

    try:
        _require_local("sign")
        current = _workspace_service().current().case
        result = _release_service().sign_plan(
            _context(
                idempotency_key=idempotency_key,
                expected_version=str(current["version"]),
            )
        )
        _emit(
            {"case": result.case, "plan_signature": result.document},
            output,
            human=(
                f"Signed plan for {result.case['id']}@{result.case['version']}"
                + (" (idempotent retry)" if result.duplicate else "")
            ),
        )
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command()
def approve(
    action: Annotated[str, typer.Argument(help="dry_run, apply, rollback, or destroy.")],
    expires_at: Annotated[
        str | None, typer.Option("--expires-at", help="RFC 3339 expiry; default 24 hours.")
    ] = None,
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.HUMAN,
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Stable retry key; derived by default."),
    ] = None,
) -> None:
    """Record a digest, target, action, and expiry bound signed approval."""

    try:
        _require_local("approve")
        current = _workspace_service().current().case
        result = _release_service().approve(
            action,
            _context(
                idempotency_key=idempotency_key,
                expected_version=str(current["version"]),
            ),
            expires_at=expires_at,
        )
        _emit(
            {"case": result.case, "approval": result.document},
            output,
            human=(
                f"Recorded {action} approval for {result.case['id']}"
                + (" (idempotent retry)" if result.duplicate else "")
            ),
        )
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command("revoke-approval")
def revoke_approval(
    action: Annotated[str, typer.Argument(help="dry_run, apply, rollback, or destroy.")],
    reason: Annotated[str, typer.Option("--reason", help="Recorded revocation reason.")],
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.HUMAN,
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Stable retry key; derived by default."),
    ] = None,
) -> None:
    """Revoke a recorded approval and publish the revocation to the mailbox."""

    try:
        _require_local("revoke-approval")
        current = _workspace_service().current().case
        result = _release_service().revoke_approval(
            action,
            reason,
            _context(
                idempotency_key=idempotency_key,
                expected_version=str(current["version"]),
            ),
        )
        _emit(
            {"case": result.case, "approval": result.document},
            output,
            human=f"Revoked the {action} approval"
            + (" (idempotent retry)" if result.duplicate else ""),
        )
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command()
def dispatch(
    kinds: Annotated[list[str], typer.Argument(help="Operation kinds to dispatch, in plan order.")],
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.HUMAN,
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Stable retry key; derived by default."),
    ] = None,
) -> None:
    """Issue the signed lease envelope for an outbound-only runner."""

    try:
        _require_local("dispatch")
        current = _workspace_service().current().case
        result = _release_service().dispatch(
            tuple(kinds),
            _context(
                idempotency_key=idempotency_key,
                expected_version=str(current["version"]),
            ),
        )
        _emit(
            {"case": result.case, "envelope": result.document},
            output,
            human=(
                f"Dispatched {', '.join(kinds)} as {result.document.get('id', 'duplicate')}"
                + (" (idempotent retry)" if result.duplicate else "")
            ),
        )
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command()
def ingest(
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.HUMAN,
) -> None:
    """Ingest signed runner messages; delivery never implies success."""

    try:
        _require_local("ingest")
        result = _release_service().ingest_runner_messages(
            _context(idempotency_key="ingest-runner-messages", expected_version=None)
        )
        _emit(
            {
                "case": result.case,
                "accepted": list(result.accepted),
                "rejected": list(result.rejected),
            },
            output,
            human=(f"Ingested {len(result.accepted)} message(s); rejected {len(result.rejected)}"),
        )
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command()
def gitops(
    output: Annotated[
        Path | None, typer.Option("--output", help="New GitOps output directory.")
    ] = None,
) -> None:
    """Render deterministic branch-ready files and a patch description."""

    try:
        _require_local("gitops")
        if output is None:
            raise OAKError("OAK-GITOPS-OUTPUT", "--output is required")
        from oak.bootstrap import create_gitops_renderer

        renderer = create_gitops_renderer(FileWorkspaceRoot.discover(Path.cwd()))
        written = renderer.render(output.absolute())
        typer.echo(f"Wrote {len(written)} file(s) to {output}")
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command()
def policy(
    action: Annotated[str, typer.Argument(help="evaluate or packs.")],
    pack: Annotated[
        str | None, typer.Option("--pack", help="Policy pack identifier to evaluate.")
    ] = None,
    engine: Annotated[
        str,
        typer.Option("--engine", help="Policy engine: builtin (default) or opa."),
    ] = "builtin",
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.HUMAN,
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Stable retry key; derived by default."),
    ] = None,
) -> None:
    """Evaluate a governed policy pack into a canonical decision, or list packs."""

    try:
        _require_local("policy")
        from oak.bootstrap import create_policy_service

        service = create_policy_service(FileWorkspaceRoot.discover(Path.cwd()))
        if action == "packs":
            packs = service.list_packs()
            _emit(
                {"packs": list(packs)},
                output,
                human="\n".join(
                    f"{item['id']}@{item['version']} {item['status']}"
                    f" effective {item['effective_from']}"
                    for item in packs
                )
                or "No policy packs are available.",
            )
            return
        if action != "evaluate":
            raise OAKError("OAK-POLICY-ACTION", "policy action must be evaluate or packs")
        if not pack:
            raise OAKError("OAK-POLICY-PACK-REQUIRED", "--pack is required to evaluate")
        current = _workspace_service().current().case
        result = service.evaluate(
            pack,
            _context(
                idempotency_key=idempotency_key,
                expected_version=str(current["version"]),
            ),
            engine=engine,
        )
        _emit(
            {"case": result.case, "decision": result.decision},
            output,
            human=(
                f"Policy {pack} on {result.case['id']}@{result.case['version']}: "
                f"{result.decision['outcome']}"
                + (" (idempotent retry)" if result.duplicate else "")
            ),
        )
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command()
def render(
    adapter: Annotated[
        str,
        typer.Option("--adapter", help="Registered deployment renderer identifier."),
    ],
    output: Annotated[
        Path | None, typer.Option("--output", help="New render output directory.")
    ] = None,
) -> None:
    """Render the compiled bundle through a deployment renderer; executes nothing."""

    try:
        _require_local("render")
        if output is None:
            raise OAKError("OAK-RENDER-OUTPUT", "--output is required")
        from oak.bootstrap import create_render_service

        service = create_render_service(FileWorkspaceRoot.discover(Path.cwd()))
        written = service.render(adapter, output.absolute())
        typer.echo(
            f"Rendered {len(written)} file(s) to {output} with {adapter}; "
            "no target action was invoked"
        )
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


@app.command()
def extensions(
    action: Annotated[
        str,
        typer.Argument(help="install, verify, activate, deactivate, list, sign, or capabilities."),
    ],
    target: Annotated[
        str | None,
        typer.Argument(help="Extension id, or a source directory for install/sign."),
    ] = None,
    version: Annotated[
        str | None, typer.Option("--version", help="Installed extension version.")
    ] = None,
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.HUMAN,
) -> None:
    """Manage governed extensions: quarantined on install, active only after verification."""

    try:
        _require_local("extensions")
        from oak.bootstrap import create_extension_service, load_steward_signer

        service = create_extension_service()
        if action == "list":
            entries = service.list_extensions()
            _emit(
                {"extensions": list(entries)},
                output,
                human="\n".join(
                    f"{item['id']}@{item['version']} [{item['state']}] {item['extension_class']}"
                    for item in entries
                )
                or "No extensions are installed.",
            )
            return
        if action == "capabilities":
            document = service.capabilities()
            _emit(
                document,
                output,
                human=json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True),
            )
            return
        if target is None:
            raise OAKError("OAK-EXTENSION-TARGET", f"{action} requires a target argument")
        if action == "install":
            entry = service.install(Path(target))
            _emit(
                {"id": entry.extension_id, "version": entry.version, "state": entry.state},
                output,
                human=(
                    f"Installed {entry.extension_id}@{entry.version} into quarantine; "
                    "verify and activate it explicitly."
                ),
            )
            return
        if action == "sign":
            manifest = service.sign_source(Path(target), load_steward_signer())
            _emit(
                {"manifest": manifest},
                output,
                human=(
                    f"Signed {manifest['id']}@{manifest['version']} with the extension-steward key."
                ),
            )
            return
        if action == "verify":
            report = service.verify(target, version, occurred_at=_now())
            _emit(
                report.to_document(),
                output,
                human="\n".join(
                    f"{check['id']}: {check['result']} — {check['detail']}"
                    for check in report.checks
                )
                + ("\nPASSED" if report.passed else "\nFAILED (stays quarantined)"),
            )
            if not report.passed:
                # Exit non-zero so a script or CI job cannot read a failed
                # supply-chain verification as success.
                raise OAKError(
                    "OAK-EXTENSION-QUARANTINED",
                    "extension failed verification and stays quarantined",
                )
            return
        if action == "activate":
            activation = service.activate(
                target,
                version,
                actor=os.getenv("OAK_ACTOR", "local-user"),
                occurred_at=_now(),
            )
            _emit(
                {"activation": activation},
                output,
                human=(
                    f"Activated {activation['extension_id']}@"
                    f"{activation['extension_version']} after full verification."
                ),
            )
            return
        if action == "deactivate":
            entry = service.deactivate(target, version)
            _emit(
                {"id": entry.extension_id, "version": entry.version, "state": entry.state},
                output,
                human=f"Deactivated {entry.extension_id}@{entry.version}; it is quarantined.",
            )
            return
        raise OAKError("OAK-EXTENSION-ACTION", "extensions action is not recognized")
    except (OAKError, ContractValidationError, OSError, RuntimeError, ValueError) as error:
        _abort(error)


def _release_service() -> ReleaseService:
    from oak.bootstrap import create_release_service

    return create_release_service(FileWorkspaceRoot.discover(Path.cwd()))


def _workspace_service() -> DesignCaseService:
    root_path = FileWorkspaceRoot.discover(Path.cwd())
    return create_design_case_service(root_path)


def _planning_service() -> CandidatePlanningService:
    root_path = FileWorkspaceRoot.discover(Path.cwd())
    return create_candidate_planning_service(root_path)


class FileWorkspaceRoot:
    """Keep filesystem discovery out of application services."""

    @staticmethod
    def discover(start: Path) -> Path:
        candidate = start.resolve()
        for directory in (candidate, *candidate.parents):
            if (directory / ".oak" / "manifest.json").is_file():
                return directory
        raise OAKError("OAK-WORKSPACE-NOT-FOUND", "no OAK workspace found")


def _context(*, idempotency_key: str | None, expected_version: str | None) -> CommandContext:
    return CommandContext(
        actor=os.getenv("OAK_ACTOR", "local-user"),
        tenant_id="local",
        idempotency_key=idempotency_key or "",
        expected_version=expected_version,
        correlation_id="",
        interface_origin="cli",
        occurred_at=_now(),
    )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _workspace_id(directory: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", directory.name.casefold()).strip("-") or "local"
    digest = hashlib.sha256(str(directory).encode("utf-8")).hexdigest()[:12]
    return f"workspace.{slug}-{digest}"


def _load_answers(path: Path) -> dict[str, Any]:
    return _load_bounded_mapping(path, prefix="OAK-CONFIRM")


def _load_bounded_mapping(path: Path, *, prefix: str) -> dict[str, Any]:
    absolute = path.absolute()
    if absolute.is_symlink() or not absolute.is_file():
        raise OAKError(f"{prefix}-UNSAFE-PATH", "input must be a regular non-symlink file")
    if absolute.suffix.lower() not in {".yaml", ".yml", ".json"}:
        raise OAKError(f"{prefix}-TYPE", "input must be YAML or JSON")
    content = _read_bounded_file(absolute, prefix=prefix, maximum_bytes=65_536)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise OAKError(f"{prefix}-ENCODING", "input must be valid UTF-8") from error
    if any(
        unicodedata.category(character) in {"Cc", "Cf"} and character not in {"\n", "\r", "\t"}
        for character in text
    ):
        raise OAKError(f"{prefix}-CONTROL", "input contains disallowed control characters")
    try:
        if absolute.suffix.lower() == ".json":
            return load_json_document(text)
        tokens = tuple(yaml.scan(text))
        if any(
            isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)) for token in tokens
        ):
            raise OAKError(f"{prefix}-ALIAS", "aliases and anchors are not accepted")
        return load_yaml_document(text)
    except (ValueError, yaml.YAMLError, ContractValidationError) as error:
        raise OAKError(f"{prefix}-MALFORMED", "input is malformed") from error


def _read_bounded_file(path: Path, *, prefix: str, maximum_bytes: int) -> bytes:
    absolute = path.absolute()
    if absolute.is_symlink() or not absolute.is_file():
        raise OAKError(f"{prefix}-UNSAFE-PATH", "input must be a regular non-symlink file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(absolute, flags)
    except OSError as error:
        raise OAKError(f"{prefix}-UNSAFE-PATH", "input could not be opened safely") from error
    with os.fdopen(descriptor, "rb") as stream:
        details = os.fstat(stream.fileno())
        if not stat.S_ISREG(details.st_mode):
            raise OAKError(f"{prefix}-UNSAFE-PATH", "input must be a regular file")
        if details.st_size < 1 or details.st_size > maximum_bytes:
            raise OAKError(f"{prefix}-SIZE", f"input must contain 1 to {maximum_bytes} bytes")
        content = stream.read(maximum_bytes + 1)
    if not content or len(content) > maximum_bytes:
        raise OAKError(f"{prefix}-SIZE", f"input must contain 1 to {maximum_bytes} bytes")
    return content


def _load_bounded_text(path: Path, *, code: str) -> str:
    absolute = path.absolute()
    if absolute.is_symlink() or not absolute.is_file():
        raise OAKError(code, "input must be a regular non-symlink file")
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(absolute, flags)
        with os.fdopen(descriptor, "rb") as stream:
            details = os.fstat(stream.fileno())
            if not stat.S_ISREG(details.st_mode):
                raise ValueError("input is not a regular file")
            content = stream.read(65_537)
        if not content or len(content) > 65_536:
            raise ValueError("input size is outside the accepted range")
        text = content.decode("utf-8")
    except (OSError, UnicodeError, ValueError) as error:
        raise OAKError(code, "input must be bounded UTF-8 text") from error
    if any(
        unicodedata.category(character) in {"Cc", "Cf"} and character not in {"\n", "\r", "\t"}
        for character in text
    ):
        raise OAKError(code, "input contains disallowed control characters")
    return text


def _write_output_directory(destination: Path, documents: dict[str, dict[str, Any]]) -> None:
    absolute = destination.absolute()
    if absolute.exists() or absolute.is_symlink():
        raise OAKError("OAK-OUTPUT-EXISTS", "output directory already exists")
    parent = absolute.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{absolute.name}.tmp-", dir=parent))
    try:
        for name, document in sorted(documents.items()):
            path = temporary / name
            path.write_text(
                json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n",
                encoding="utf-8",
            )
            path.chmod(0o600)
        os.replace(temporary, absolute)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _candidate_table(candidates_value: tuple[dict[str, Any], ...]) -> str:
    header = "ID            VARIANT                    STATUS      FRONTIER  REJECTIONS"
    rows = [header]
    for candidate in candidates_value:
        variant = str(candidate["extensions"]["oak.community/pattern_variant"])
        rows.append(
            f"{candidate['id']:<13} {variant:<26} {candidate['status']:<11} "
            f"{str(candidate['pareto']['frontier_member']).lower():<9} "
            f"{len(candidate['rejection_reasons'])}"
        )
    return "\n".join(rows)


def _emit(document: dict[str, Any], output: OutputFormat, *, human: str) -> None:
    if output in {OutputFormat.HUMAN, OutputFormat.TABLE}:
        typer.echo(human)
    elif output is OutputFormat.JSON:
        typer.echo(json.dumps(document, ensure_ascii=False, sort_keys=True))
    else:
        typer.echo(yaml.safe_dump(document, allow_unicode=True, sort_keys=False).rstrip())


def _abort(error: Exception) -> NoReturn:
    if isinstance(error, OAKError):
        code = error.code
        message = error.message
        exit_code = 4 if code in {"OAK-EXPECTED-VERSION", "OAK-IDEMPOTENCY-CONFLICT"} else 2
    elif isinstance(error, ContractValidationError):
        code = "OAK-CONTRACT-INVALID"
        message = "input failed canonical contract validation"
        exit_code = 2
    else:
        code = "OAK-INPUT-INVALID"
        message = "input could not be processed safely"
        exit_code = 2
    typer.echo(f"{code}: {message}", err=True)
    raise typer.Exit(code=exit_code)


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
