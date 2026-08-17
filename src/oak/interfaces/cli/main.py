# SPDX-License-Identifier: Apache-2.0
"""Local-first command-line entrypoint."""

import hashlib
import json
import os
import re
import stat
import unicodedata
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
import yaml

from oak.application import CommandContext, DesignCaseService
from oak.bootstrap import create_design_case_service, create_system_information_service
from oak.contracts import ContractValidationError, load_json_document, load_yaml_document
from oak.domain import OAKError


class OutputFormat(StrEnum):
    HUMAN = "human"
    JSON = "json"
    YAML = "yaml"


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


def _workspace_service() -> DesignCaseService:
    root_path = FileWorkspaceRoot.discover(Path.cwd())
    return create_design_case_service(root_path)


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


def _emit(document: dict[str, Any], output: OutputFormat, *, human: str) -> None:
    if output is OutputFormat.HUMAN:
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
