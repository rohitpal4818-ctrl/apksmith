"""``apksmith generate``: the M3 stage, behaviour spec to Flutter project.

    apksmith generate run reports/understanding.json --out build/recon

No model is consulted. The scaffolding, routing, theme, data classes and API
client are produced by code, so the command works with no API key and the
output is deterministic. Screen behaviour is left as ``TODO`` because inventing
it would be worse than leaving a marker.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from ..generate import build_flutter_project
from ..understand.spec import BehaviourSpec

app = typer.Typer(
    name="generate", help="M3: behaviour spec -> runnable project.", no_args_is_help=True
)


@app.command("run")
def generate_run(
    spec: Path = typer.Argument(..., exists=True, help="Behaviour spec JSON from M2"),
    out: Path = typer.Option(
        Path("build/reconstruction"), "--out", help="Output directory"
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace existing files"),
) -> None:
    """Generate a Flutter project from a behaviour specification."""
    try:
        parsed = BehaviourSpec.model_validate(
            json.loads(spec.read_text(encoding="utf-8"))
        )
    except (json.JSONDecodeError, ValueError) as exc:
        typer.secho(f"could not read spec: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    try:
        result = build_flutter_project(parsed)
    except ValueError as exc:
        typer.secho(f"cannot generate: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    written = result.write(out, overwrite=overwrite)

    typer.secho(f"generated {len(written)} files -> {out}", fg=typer.colors.GREEN)
    typer.echo(f"  {result.summary()}")

    # `written` holds only the files actually created; the rest were skipped
    # because they already existed. Compare full paths, not basenames, or
    # every file under lib/screens/ would look skipped.
    written_paths = {p.resolve() for p in written}
    for generated_file in result.files:
        marker = "*" if (out / generated_file.path).resolve() in written_paths else " "
        typer.echo(f"  {marker} [{generated_file.origin:8}] {generated_file.path}")

    if result.warnings:
        typer.secho("\nwarnings", fg=typer.colors.YELLOW)
        for warning in result.warnings:
            typer.echo(f"  - {warning}")

    if result.open_questions:
        typer.secho(
            "\nopen questions (analysis could not answer these)", fg=typer.colors.YELLOW
        )
        for question in result.open_questions:
            typer.echo(f"  - {question}")

    typer.secho(
        "\nthis is a scaffold. Screen behaviour, state and business rules are "
        "TODO. run `flutter pub get` inside the output to verify it compiles.",
        fg=typer.colors.CYAN,
    )
