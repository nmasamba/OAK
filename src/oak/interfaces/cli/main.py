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
from typing import Annotated, Any, NoReturn

import typer
import yaml

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
) -> None:
    """OAK Community command group."""


@app.command("init")
def init_workspace(
    directory: Annotated[Path, typer.Argument(help="Directory to initialize.")] = Path("."),
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.HUMAN,
) -> None:
    """Initialize an atomic local OAK workspace."""

    try:
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
        current = _workspace_service().current().case
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
        current = _workspace_service().current().case
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
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Stable retry key; derived by default."),
    ] = None,
) -> None:
    """Create the selected candidate's deterministic assurance plan."""

    try:
        if output is None:
            raise OAKError("OAK-ASSURE-OUTPUT", "--output is required")
        current = _workspace_service().current().case
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
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Stable retry key; derived by default."),
    ] = None,
) -> None:
    """Compile canonical review files and a non-executing typed runner plan."""

    try:
        if target is None or output is None:
            raise OAKError("OAK-PLAN-INPUT", "--target and --output are required")
        current = _workspace_service().current().case
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

    from oak.interfaces.api.server import run_server

    try:
        run_server(host=host, port=port, allow_non_loopback=allow_non_loopback)
    except ValueError as error:
        typer.echo(f"OAK-SAFE-BIND: {error}", err=True)
        raise typer.Exit(code=2) from error


@app.command()
def keys(
    action: Annotated[str, typer.Argument(help="init or show.")],
    output: Annotated[
        OutputFormat, typer.Option("--output", help="Output format.")
    ] = OutputFormat.HUMAN,
) -> None:
    """Create or inspect the local development signing identities."""

    try:
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
        if output is None:
            raise OAKError("OAK-GITOPS-OUTPUT", "--output is required")
        from oak.bootstrap import create_gitops_renderer

        renderer = create_gitops_renderer(FileWorkspaceRoot.discover(Path.cwd()))
        written = renderer.render(output.absolute())
        typer.echo(f"Wrote {len(written)} file(s) to {output}")
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
    absolute = path.absolute()
    if absolute.is_symlink() or not absolute.is_file():
        raise OAKError("OAK-CONFIRM-UNSAFE-PATH", "answers must be a regular non-symlink file")
    if absolute.suffix.lower() not in {".yaml", ".yml", ".json"}:
        raise OAKError("OAK-CONFIRM-TYPE", "answers must be YAML or JSON")
    content = _read_bounded_answers(absolute)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise OAKError("OAK-CONFIRM-ENCODING", "answers must be valid UTF-8") from error
    if any(
        unicodedata.category(character) in {"Cc", "Cf"} and character not in {"\n", "\r", "\t"}
        for character in text
    ):
        raise OAKError("OAK-CONFIRM-CONTROL", "answers contain disallowed control characters")
    try:
        if absolute.suffix.lower() == ".json":
            return load_json_document(text)
        tokens = tuple(yaml.scan(text))
        if any(
            isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)) for token in tokens
        ):
            raise OAKError("OAK-CONFIRM-ALIAS", "answer aliases and anchors are not accepted")
        return load_yaml_document(text)
    except (ValueError, yaml.YAMLError, ContractValidationError) as error:
        raise OAKError("OAK-CONFIRM-MALFORMED", "answers are malformed") from error


def _read_bounded_answers(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise OAKError("OAK-CONFIRM-UNSAFE-PATH", "answers could not be opened safely") from error
    with os.fdopen(descriptor, "rb") as stream:
        details = os.fstat(stream.fileno())
        if not stat.S_ISREG(details.st_mode):
            raise OAKError("OAK-CONFIRM-UNSAFE-PATH", "answers must be a regular file")
        if details.st_size < 1 or details.st_size > 65_536:
            raise OAKError("OAK-CONFIRM-SIZE", "answers must contain 1 to 65536 bytes")
        content = stream.read(65_537)
    if not content or len(content) > 65_536:
        raise OAKError("OAK-CONFIRM-SIZE", "answers must contain 1 to 65536 bytes")
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
