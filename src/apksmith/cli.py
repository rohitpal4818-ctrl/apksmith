"""
APKSmith command-line interface.

    apksmith scan app.apk                  human-readable terminal summary
    apksmith scan app.apk --json out.json  full machine-readable report
    apksmith scan app.apk --markdown r.md  report for a README or PR
    apksmith scan app.apk --top 30         show more findings
    apksmith coverage                      what this tool does not do

We use Typer because it generates a good `--help` for free, which matters
when someone other than the author has to run the tool.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from . import __version__
from .app import analyse, coverage_notes
from .commands import evaluate as evaluate_cmd
from .commands import generate as generate_cmd
from .commands import understand as understand_cmd
from .errors import ApkSmithError
from .fileio import write_text
from .logging_setup import configure_logging
from .report import to_json, to_markdown, to_terminal

cli = typer.Typer(
    name="apksmith",
    help="Static analysis and behaviour extraction from Android APKs.",
    add_completion=False,
    no_args_is_help=True,
)
cli.add_typer(understand_cmd.app, name="understand", help="M2: infer what an app does")
cli.add_typer(generate_cmd.app, name="generate", help="M3: spec -> project")
cli.add_typer(evaluate_cmd.app, name="evaluate", help="M5: score against references")


def _run(path: Path, verbose: bool) -> object:
    """Shared entry for scan. Keeps the command bodies thin."""
    configure_logging(verbose=verbose)
    if verbose:
        typer.echo(f"apksmith {__version__}")
        typer.echo(f"analysing {path}")
    return analyse(path, progress=verbose)


@cli.command()
def scan(
    apk: Path = typer.Argument(..., exists=True, help="Path to the .apk file"),
    json_out: Path = typer.Option(None, "--json", help="Write the full report as JSON"),
    md_out: Path = typer.Option(None, "--markdown", help="Write the report as Markdown"),
    top: int = typer.Option(
        12, "--top", help="How many findings to show in the terminal"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show pipeline progress"),
) -> None:
    """Analyse an APK and print a report."""
    try:
        report = _run(apk, verbose)
    except ApkSmithError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo(to_terminal(report, top_n=top))

    if json_out:
        write_text(json_out, to_json(report))
        typer.secho(f"\nwrote JSON     -> {json_out}", fg=typer.colors.GREEN)

    if md_out:
        write_text(md_out, to_markdown(report))
        typer.secho(f"wrote Markdown -> {md_out}", fg=typer.colors.GREEN)

    # Non-zero exit when something notable was found makes the tool usable in
    # CI, which is where a security tool actually earns its keep.
    if report.risk_score >= 80:
        raise typer.Exit(code=2)


@cli.command()
def coverage() -> None:
    """Print what this tool does not do."""
    typer.echo("APKSmith coverage limits\n")
    for note in coverage_notes():
        typer.echo(f"  - {note}")
    typer.echo("")


@cli.command()
def version() -> None:
    """Print the version."""
    typer.echo(__version__)


@cli.command()
def mcp() -> None:
    """Run the MCP server over stdio, so an agent can drive the pipeline.

    Needs the optional SDK (``pip install -e ".\\[mcp]"``). Speaks stdio, so it
    is meant to be launched by an MCP client rather than typed into a terminal.
    """
    from .mcp_server import main as run_mcp_server

    run_mcp_server()


def main() -> None:
    """Console-script entry point."""
    try:
        cli()
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
