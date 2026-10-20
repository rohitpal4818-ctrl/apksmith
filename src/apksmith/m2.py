"""
M2: the understanding stage.

Turns decompiled sources plus the M1 report into a behaviour specification.

    apksmith understand app.apk                    full run
    apksmith understand app.apk --dry-run          build prompts, call nothing
    apksmith understand app.apk --max-classes 40   smaller class budget
"""

from __future__ import annotations

import os
from pathlib import Path

import typer

from .errors import ApkSmithError
from .ingest import jadx
from .logging_setup import configure_logging
from .models import RiskReport
from .understand.extract import extract_tree
from .understand.llm import DEFAULT_MODEL, LlmClient, known_providers
from .understand.pipeline import understand
from .understand.prompt import SYSTEM, extraction_prompt
from .understand.rank import role_census, select

cli = typer.Typer(
    name="understand",
    help="M2: decompiled source + static report -> behaviour specification.",
    no_args_is_help=True,
)


@cli.command()
def run(
    apk: Path = typer.Argument(..., exists=True, help="Path to the .apk"),
    report_json: Path | None = typer.Option(
        None, "--report", help="Reuse a saved M1 JSON report instead of re-running M1"
    ),
    out: Path = typer.Option(
        Path("reports/understanding.md"), "--out", help="Markdown output"
    ),
    json_out: Path | None = typer.Option(
        None, "--json", help="Also write the spec as JSON"
    ),
    decompiled: Path | None = typer.Option(
        None, "--decompiled", help="Reuse an existing jadx output directory"
    ),
    keep_decompiled: bool = typer.Option(
        False, "--keep-decompiled", help="Keep the jadx output instead of deleting it"
    ),
    max_classes: int = typer.Option(60, "--max-classes", help="Class budget"),
    per_chunk: int = typer.Option(12, "--per-chunk", help="Classes per model call"),
    per_role_cap: int = typer.Option(20, "--per-role-cap", help="Max classes per role"),
    provider: str = typer.Option(
        "openrouter",
        "--provider",
        help=f"LLM provider: {', '.join(known_providers())}",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help="Model id. Defaults to the provider's recommended model.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Build and show the prompts without calling the model"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Understand what an APK does, and write a behaviour spec."""
    configure_logging(verbose=verbose)

    # Validate the provider before doing any work. The dict lookups below would
    # otherwise raise a bare KeyError, and only after jadx had spent a minute
    # decompiling -- a wasted minute and an unhelpful traceback.
    if provider not in known_providers():
        raise typer.BadParameter(
            f"unknown provider {provider!r}; choose from {', '.join(known_providers())}",
            param_hint="--provider",
        )

    # Claiming to "use existing sources" for a path that is not there just
    # moves the failure a few steps later, where it reads as a parser bug.
    # Checked here, before M1, so a typo costs nothing.
    if decompiled is not None and not decompiled.is_dir():
        typer.secho(
            f"--decompiled points at {decompiled}, which is not a directory.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    from .app import analyse

    # ---- M1: static report ------------------------------------------------ #
    if report_json and report_json.is_file():
        typer.echo(f"reusing M1 report {report_json}")
        import json as _json

        raw = _json.loads(report_json.read_text(encoding="utf-8"))
        report = RiskReport.model_validate(raw)
    else:
        typer.echo("running M1 static analysis ...")
        report = analyse(apk, progress=verbose)

    # ---- decompile -------------------------------------------------------- #
    tmp_dir: Path | None = None
    if decompiled:
        typer.echo(f"using existing decompiled sources at {decompiled}")
        source_root = decompiled
    else:
        if not jadx.is_available():
            typer.secho(
                "jadx not found. Install it from https://github.com/skylot/jadx/releases "
                "and put jadx on PATH, or pass --decompiled.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)
        import tempfile

        tmp_dir = Path(tempfile.mkdtemp(prefix="apksmith-m2-"))
        source_root = tmp_dir / "jadx"
        typer.echo("decompiling with jadx (this takes a while) ...")
        try:
            jadx.decompile(apk, out_dir=source_root)
        except ApkSmithError as exc:
            typer.secho(f"jadx failed: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        typer.echo(f"decompiled to {source_root}")

    try:
        from .understand.pipeline import resolve_app_prefixes

        prefixes = resolve_app_prefixes(report, source_root)
        if prefixes:
            typer.echo(f"app's own source prefix: {prefixes[0]}")

        if dry_run:
            summaries = extract_tree(source_root, package_prefixes=prefixes)
            selected = select(
                summaries, max_classes=max_classes, per_role_cap=per_role_cap
            )
            typer.echo(f"\nprovider           : {provider}")
            typer.echo(f"model              : {model or DEFAULT_MODEL[provider]}")
            typer.echo(f"classes in package : {len(summaries):,}")
            typer.echo(f"roles              : {role_census(summaries)}")
            typer.echo(f"selected           : {len(selected)}")
            typer.echo(
                f"prompt size        : "
                f"{sum(len(s.to_prompt_block()) for s in selected):,} chars"
            )
            typer.echo("\n--- SYSTEM PROMPT ---")
            typer.echo(SYSTEM)
            typer.echo("\n--- FIRST USER MESSAGE ---")
            typer.echo(extraction_prompt(selected[:per_chunk], report, 1, 1)[:3000])
            return

        # ---- M2 ------------------------------------------------------------ #
        env_name = {
            "openrouter": "OPENROUTER_API_KEY",
            "groq": "GROQ_API_KEY",
        }[provider]
        client = LlmClient(
            api_key=os.environ.get(env_name),
            provider=provider,
            model=model,
        )
        if not client.api_key:
            key_url = {
                "openrouter": "https://openrouter.ai/keys",
                "groq": "https://console.groq.com/keys",
            }[provider]
            typer.secho(
                f"No {env_name} set. Get a free key at {key_url}, then:\n"
                f"  $env:{env_name} = '...'\n"
                "Or run with --dry-run to see the prompts without spending requests.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)

        result = understand(
            report,
            source_root,
            client,
            package_prefixes=prefixes,
            max_classes=max_classes,
            per_chunk=per_chunk,
            per_role_cap=per_role_cap,
            verbose=verbose,
        )

        _write(out, result.spec.to_markdown())
        typer.secho(f"wrote behaviour spec -> {out}", fg=typer.colors.GREEN)
        if json_out:
            _write(json_out, result.spec.model_dump_json(indent=2))
            typer.secho(f"wrote spec JSON      -> {json_out}", fg=typer.colors.GREEN)

        typer.echo("\nrun stats")
        typer.echo(f"  app classes considered : {result.classes_considered:,}")
        typer.echo(f"  classes sent to model  : {result.classes_sent}")
        typer.echo(f"  chunks / parts         : {result.parts}")
        for key, value in result.stats.as_dict().items():
            typer.echo(f"  {key:<26}: {value}")
        if result.cache_dir:
            typer.echo(f"  cache                  : {result.cache_dir}")

    finally:
        if tmp_dir and not keep_decompiled:
            import shutil

            # Remove OUR directory only. `tmp_dir.parent` is the system temp
            # directory -- `mkdtemp(prefix=...)` returns
            # <tempdir>/apksmith-m2-XXXX, so walking up one level and calling
            # rmtree on it would delete every temp file on the user's machine.
            # This ran on a real APK before it was caught.
            shutil.rmtree(tmp_dir, ignore_errors=True)
            typer.echo(f"cleaned up {tmp_dir}")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
