"""``apksmith evaluate``: the M5 stage, scoring specs against references.

    apksmith evaluate run evaluation/suite.json --out reports/evaluation.md

The references are hand-written from public documentation, never produced by a
model. That is the whole point: comparing a model's output with another model's
output measures nothing. The numbers here are agreement with a human reading,
which is why the report says so in its first paragraph.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from ..evaluate import load_suite
from ..fileio import write_text

app = typer.Typer(
    name="evaluate",
    help="M5: score specs against hand-written references.",
    no_args_is_help=True,
)


@app.command("run")
def evaluate_run(
    suite: Path = typer.Argument(..., exists=True, help="Reference suite JSON"),
    out: Path = typer.Option(
        Path("reports/evaluation.md"), "--out", help="Markdown report"
    ),
) -> None:
    """Score generated specs against hand-written references."""
    try:
        report = load_suite(suite)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        typer.secho(f"could not load suite: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    write_text(out, report.to_markdown())

    typer.secho(f"evaluated {len(report.cases)} case(s) -> {out}", fg=typer.colors.GREEN)
    typer.echo(f"  mean F1 across cases: {report.mean_f1:.3f}")
    for name, value in report.per_metric().items():
        typer.echo(f"  {name:<26} {value:.3f}")
    typer.secho(
        "\nthese measure agreement with an independent human description, not "
        "truth. treat them as a regression signal.",
        fg=typer.colors.CYAN,
    )
