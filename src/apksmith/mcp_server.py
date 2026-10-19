"""
M4: the MCP server.

Exposes the whole pipeline as Model Context Protocol tools, so an AI agent can
drive APKSmith without knowing anything about its internals. This is what
turns the pipeline from a command-line tool into something an agent can
reason over.

Why MCP specifically: an agent that has to shell out and parse terminal output
is brittle. MCP gives it typed tools with structured results, and it is the
protocol the ecosystem is standardising on.

The tools are intentionally coarse-grained. An agent is far more reliable
asking "what does this APK do?" than orchestrating forty fine-grained
inspection calls.

Registering with an MCP client:

    claude mcp add apksmith -- python /path/to/apksmith/mcp_server.py
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .errors import ApkSmithError
from .models import RiskReport

try:
    from mcp.server.fastmcp import FastMCP
    HAVE_MCP = True
except ImportError:  # pragma: no cover
    FastMCP = None  # type: ignore[assignment]
    HAVE_MCP = False


SERVER_NAME = "apksmith"
SERVER_INSTRUCTIONS = """\
APKSmith analyses Android APKs. Use it to find out what an app does, then to
generate a reconstruction scaffold.

Typical sequence:

1. `apk_identity`   -- cheap. Get the package, main activity, SDK range.
2. `apk_analyse`    -- static report: permissions, endpoints, components, SDKs.
3. `apk_decompile`  -- decompile to Java. Takes a minute or two.
4. `apk_extract`    -- turn decompiled source into ranked class summaries.
5. `apk_understand` -- needs an OpenRouter key. Produces a behaviour spec.
6. `apk_generate`   -- spec -> runnable Flutter project.

Steps 1, 2, 3, 4 and 6 work with no API key. Only `apk_understand` needs one,
and only it calls a model.

Be honest about limits when reporting: string-pool matching is not dataflow
analysis, and generated projects are scaffolds with the logic left as TODO.
"""


def _require_mcp() -> None:
    if not HAVE_MCP:
        raise ApkSmithError(
            "The MCP SDK is not installed. Install it with:\n"
            "    pip install mcp\n"
            "or install the dev extras: pip install -e \".[dev,mcp]\""
        )


# --------------------------------------------------------------------------- #
# Shared state between calls
# --------------------------------------------------------------------------- #
class Workspace:
    """Holds decompiled output between tool calls.

    Decompiling takes minutes, so an agent should not have to do it twice. We
    key sessions on the APK's SHA-256 and clean up on exit.
    """

    def __init__(self) -> None:
        self._dirs: dict[str, Path] = {}
        self._root = Path(tempfile.mkdtemp(prefix="apksmith-mcp-"))

    def source_dir(self, digest: str) -> Path | None:
        return self._dirs.get(digest)

    def allocate(self, digest: str) -> Path:
        """Reserve and return an output directory for this session.

        Decompiled output runs to tens of thousands of files, so it has to go
        somewhere temporary rather than into the caller's working directory.
        Exposed publicly so the tools never reach into ``_root``.
        """
        return self._root / digest

    def remember(self, digest: str, path: Path) -> None:
        self._dirs[digest] = path

    def cleanup(self) -> None:
        shutil.rmtree(self._root, ignore_errors=True)


#: Workspaces built during this process, so main() can clean them up.
_LIVE_WORKSPACES: list[Workspace] = []


def _apk_digest(path: str | Path) -> str:
    from .ingest.apkfile import sha256_of

    return sha256_of(Path(path))[:16]


def _dump(payload: Any) -> str:
    """Serialise a Pydantic model or dict for an MCP text result."""
    if hasattr(payload, "model_dump_json"):
        return payload.model_dump_json(indent=2)
    return json.dumps(payload, indent=2, default=str)


def build_server():
    """Construct the FastMCP server with all tools registered."""
    _require_mcp()

    mcp = FastMCP(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    workspace = Workspace()
    # Held so main() can clean up the temp tree on exit.
    _LIVE_WORKSPACES.append(workspace)

    # -- 1. identity ---------------------------------------------------- #
    @mcp.tool()
    def apk_identity(apk_path: str) -> str:
        """Cheap first look at an APK: package, version, SDK range, entry point.

        Use this before anything else. It parses only the manifest, so it is
        fast and never fails on a packed app.
        """
        from .app import analyse

        report = analyse(apk_path)
        i = report.identity
        return _dump(
            {
                "package": i.package,
                "app_name": i.app_name,
                "version": i.version_name,
                "version_code": i.version_code,
                "min_sdk": i.min_sdk,
                "target_sdk": i.target_sdk,
                "main_activity": i.main_activity,
                "sha256": report.apk_sha256[:16],
                "size_bytes": report.apk_size_bytes,
            }
        )

    # -- 2. static analysis --------------------------------------------- #
    @mcp.tool()
    def apk_analyse(apk_path: str, risk_only: bool = False) -> str:
        """Full static analysis. Returns permissions, endpoints, components,
        WebView bridges, crypto use, SDK fingerprints and a risk score.

        Set risk_only for a summary without the full component and endpoint
        lists.
        """
        from .app import analyse
        from .report import to_json, to_markdown, to_terminal

        report = analyse(apk_path)
        if risk_only:
            return to_terminal(report, top_n=8)
        return to_markdown(report)

    # -- 3. decompile --------------------------------------------------- #
    @mcp.tool()
    def apk_decompile(apk_path: str) -> str:
        """Decompile an APK to readable Java using jadx.

        Takes one to several minutes for a large app. The result is cached for
        this session, so calling it twice is cheap.

        Returns the session id and how many classes were produced.
        """
        from .ingest import jadx

        if not jadx.is_available():
            return json.dumps(
                {
                    "error": "jadx not found",
                    "detail": (
                        "Install jadx from https://github.com/skylot/jadx/releases "
                        "and put it on PATH. Steps 1, 2 and 6 work without it."
                    ),
                }
            )

        digest = _apk_digest(apk_path)
        cached = workspace.source_dir(digest)
        if cached is not None:
            return json.dumps(
                {"session_id": digest, "cached": True, "path": str(cached)}
            )

        out = workspace.allocate(digest)
        jadx.decompile(apk_path, out_dir=out)
        workspace.remember(digest, out)

        java_files = sum(1 for _ in (out / "sources").rglob("*.java"))
        return json.dumps(
            {
                "session_id": digest,
                "cached": False,
                "path": str(out),
                "java_files": java_files,
            }
        )

    # -- 4. extract ----------------------------------------------------- #
    @mcp.tool()
    def apk_extract(apk_path: str, max_classes: int = 30) -> str:
        """Turn decompiled source into ranked class summaries.

        Returns the classes that best describe the app: screens first, then
        data and models. This is the input the model actually reads, so the
        output is a much smaller, much more useful view than the raw source.
        """
        from .app import analyse
        from .understand.extract import extract_tree
        from .understand.pipeline import resolve_app_prefixes
        from .understand.rank import role_census, select

        digest = _apk_digest(apk_path)
        source = workspace.source_dir(digest)
        if source is None:
            return json.dumps(
                {"error": "not decompiled", "hint": "call apk_decompile first"}
            )

        report = analyse(apk_path)
        prefixes = resolve_app_prefixes(report, source)
        summaries = extract_tree(source, package_prefixes=prefixes)
        selected = select(summaries, max_classes=max_classes, per_role_cap=10)

        return _dump(
            {
                "package": report.identity.package,
                "source_prefix": prefixes,
                "classes_in_app": len(summaries),
                "roles": role_census(summaries),
                "selected": [
                    {
                        "class": s.fqcn,
                        "role": s.role,
                        "score": round(s.score, 2),
                        "methods": s.methods[:8],
                        "strings": s.strings[:6],
                    }
                    for s in selected
                ],
            }
        )

    # -- 5. understand -------------------------------------------------- #
    @mcp.tool()
    def apk_understand(
        apk_path: str,
        max_classes: int = 60,
        per_chunk: int = 12,
    ) -> str:
        """Produce a behaviour specification. Requires OPENROUTER_API_KEY.

        This is the only tool that calls a model. It chunks the app's own code,
        describes each chunk, then merges the results. Consumes free-tier rate
        limit, and responses are cached on disk so repeats are free.
        """
        from .app import analyse
        from .understand.llm import DEFAULT_MODEL, LlmClient
        from .understand.pipeline import resolve_app_prefixes, understand

        if not os.environ.get("OPENROUTER_API_KEY"):
            return json.dumps(
                {
                    "error": "no API key",
                    "hint": (
                        "Set OPENROUTER_API_KEY. Get a free key at "
                        "https://openrouter.ai/keys (no card required)."
                    ),
                }
            )

        digest = _apk_digest(apk_path)
        source = workspace.source_dir(digest)
        if source is None:
            return json.dumps(
                {"error": "not decompiled", "hint": "call apk_decompile first"}
            )

        report = analyse(apk_path)
        client = LlmClient(model=DEFAULT_MODEL)

        try:
            result = understand(
                report,
                source,
                client,
                package_prefixes=resolve_app_prefixes(report, source),
                max_classes=max_classes,
                per_chunk=per_chunk,
                verbose=False,
            )
        except ApkSmithError as exc:
            return json.dumps({"error": type(exc).__name__, "detail": str(exc)})

        return result.spec.to_markdown()

    # -- 6. generate ---------------------------------------------------- #
    @mcp.tool()
    def apk_generate(
        spec_json: str,
        output_dir: str,
        overwrite: bool = False,
    ) -> str:
        """Generate a runnable Flutter project from a behaviour specification.

        Takes the JSON produced by apk_understand. Does not need an API key:
        the scaffolding is generated by code and is correct by construction,
        with screen logic left as explicit TODO markers.

        Returns the files written, plus open questions the specification could
        not answer.
        """
        from .generate import build_flutter_project
        from .understand.spec import BehaviourSpec

        try:
            spec = BehaviourSpec.model_validate(json.loads(spec_json))
        except (json.JSONDecodeError, ValueError) as exc:
            return json.dumps({"error": "bad spec", "detail": str(exc)})

        try:
            result = build_flutter_project(spec)
        except ValueError as exc:
            return json.dumps({"error": "cannot generate", "detail": str(exc)})

        written = result.write(Path(output_dir), overwrite=overwrite)

        return _dump(
            {
                "output_dir": str(Path(output_dir)),
                "files_written": len(written),
                "summary": result.summary(),
                "files": [
                    {"path": gf.path, "origin": gf.origin} for gf in result.files
                ],
                "open_questions": result.open_questions,
                "warnings": result.warnings,
                "note": (
                    "This is a reconstruction scaffold, not a working app. "
                    "Screen behaviour, state and business rules are TODO."
                ),
            }
        )

    # -- 7. coverage ---------------------------------------------------- #
    @mcp.tool()
    def apk_coverage() -> str:
        """What APKSmith cannot do. Call this before promising a user accuracy."""
        from .app import coverage_notes

        return _dump({"limits": coverage_notes()})

    return mcp


def main() -> None:  # pragma: no cover - entry point
    """Run the MCP server over stdio."""
    try:
        server = build_server()
    except ApkSmithError as exc:
        raise SystemExit(str(exc))
    try:
        server.run()
    finally:
        # Decompiled output can run to hundreds of megabytes. Without this the
        # temp tree survives an abnormal exit and quietly fills the disk.
        for workspace in _LIVE_WORKSPACES:
            workspace.cleanup()
        _LIVE_WORKSPACES.clear()


if __name__ == "__main__":  # pragma: no cover
    main()
