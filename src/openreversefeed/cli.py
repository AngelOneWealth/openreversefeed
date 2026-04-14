"""orf — command-line interface for openreversefeed."""
from __future__ import annotations

import typer

from openreversefeed import __version__

app = typer.Typer(
    name="orf",
    help="openreversefeed — India MF registrar feed processor.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"openreversefeed {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """orf — openreversefeed CLI."""


@app.command()
def migrate() -> None:
    """Run alembic migrations to head. Full implementation in chunk 7."""
    typer.echo("migrate: not yet implemented")
    raise typer.Exit(code=1)


@app.command()
def process(file: str) -> None:
    """Process a single feed file. Full implementation in chunk 7."""
    typer.echo(f"process {file}: not yet implemented")
    raise typer.Exit(code=1)
