# SPDX-License-Identifier: Apache-2.0
"""Local-first command-line entrypoint."""

from typing import Annotated

import typer

from oak.bootstrap import create_system_information_service

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


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
