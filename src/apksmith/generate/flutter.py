"""
The Flutter project builder: BehaviourSpec -> a complete, runnable project.

Pure code. No model is consulted here, which is deliberate: the output must be
correct and compilable even when no API key exists. A model-assisted layer can
fill in screen bodies afterwards, but it is optional and additive.

The builder is also where the honesty requirements are enforced. Every file
carries a provenance header, the README has an explicit "what is real" table,
and anything analysis could not determine is surfaced as an open question
rather than quietly omitted.
"""

from __future__ import annotations

from ..understand.spec import BehaviourSpec
from . import templates
from .naming import GeneratedFile, GenerationResult, dart_string, pascal, singular, snake


def _bullet_list(items: list[str], indent: str = "") -> str:
    """Render a doc-comment bullet list, newline-terminated.

    The trailing newline matters: the template places `///` immediately after
    the placeholder, so without it the last bullet runs into the next comment.
    """
    if not items:
        return f"{indent}/// (none observed)\n"
    return "".join(f"{indent}/// - {i}\n" for i in items)


class _NameRegistry:
    """Hands out file stems that are unique.

    Three separate collisions are possible from model-supplied labels, and
    each one silently produced two files at the same path -- the second
    overwriting the first, so a screen vanished from the generated project
    with no error at all:

    1. the same name twice (``App List`` from two different partials)
    2. names that collide once normalised (``App List`` and ``app_list``)
    3. a name that shadows a file the generator emits itself (``Home``, which
       would overwrite the entry screen)
    """

    def __init__(self, reserved: set[str] | None = None) -> None:
        self._used: set[str] = set(reserved or set())

    def unique(self, base: str) -> str:
        """Return ``base``, or ``base_2``, ``base_3``... if it is already taken.

        Also records the result, so a later caller asking for the same name gets
        the next suffix rather than the same one.
        """
        candidate = base
        suffix = 2
        while candidate in self._used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        self._used.add(candidate)
        return candidate


#: Stems the generator emits itself, which a screen or model must not shadow.
_BUILTIN_STEMS = {"home", "unknown_route"}


def build_flutter_project(spec: BehaviourSpec) -> GenerationResult:
    """Generate a Flutter project from a behaviour specification."""
    if not spec.screens and not spec.features:
        raise ValueError(
            "The specification contains no screens or features. There is "
            "nothing to generate a project from. Re-run the understanding "
            "stage, or check the model's output."
        )

    result = GenerationResult()
    stems = _NameRegistry(reserved=_BUILTIN_STEMS)
    app_class = f"{pascal(spec.app_name or spec.package or 'app')}App"
    project_name = snake(spec.app_name or spec.package or "reconstructed_app").replace(
        ".", "_"
    )
    title = spec.app_name or pascal(spec.package or "Reconstructed App")
    description = _one_line(spec.purpose) or "Reconstructed from static analysis"

    def add(path: str, content: str, origin: str = "scaffold", note: str = "") -> None:
        result.files.append(
            GeneratedFile(path=path, content=content, origin=origin, note=note)
        )

    # ---- project scaffolding --------------------------------------------- #
    add(
        "pubspec.yaml",
        templates.render(
            templates.PUBSPEC, project_name=project_name, description=description
        ),
    )
    add(".gitignore", templates.render(templates.GITIGNORE))
    add("analysis_options.yaml", templates.render(templates.ANALYSIS_OPTIONS))
    add("lib/main.dart", templates.render(templates.MAIN_DART, app_class=app_class))
    add(
        "lib/app.dart",
        templates.render(
            templates.APP_DART, app_class=app_class, title=dart_string(title)
        ),
    )
    add("lib/theme.dart", templates.render(templates.THEME_DART))
    add(
        "lib/screens/unknown_route_screen.dart",
        templates.render(templates.UNKNOWN_ROUTE_DART),
    )
    add(
        "test/widget_test.dart",
        templates.render(templates.TEST_DART, project_name=project_name),
    )

    # ---- screens ---------------------------------------------------------- #
    screen_routes: list[tuple[str, str]] = []
    for screen in spec.screens:
        stem = stems.unique(snake(screen.name))
        class_name = f"{pascal(stem)}Screen"
        route = f"/{stem}"
        screen_routes.append((route, class_name))
        add(
            f"lib/screens/{stem}_screen.dart",
            _screen_dart(screen, class_name, project_name, stem),
            origin="stub",
            note="screen shell from observed behaviour; logic is TODO",
        )

    # ---- router ----------------------------------------------------------- #
    # Emitted after the screens so every route resolves to a real class.
    add("lib/router.dart", _routes_dart(screen_routes, app_class))

    # ---- home screen ------------------------------------------------------ #
    add(
        "lib/screens/home_screen.dart",
        _home_dart(title, screen_routes, app_class, spec.purpose),
    )

    # ---- data models ------------------------------------------------------ #
    model_stems = _NameRegistry()
    for data in spec.data_stored:
        # `expenses` -> class `Expense`, file `expense.dart`. Applying the
        # singulariser before pascal() is what keeps all three in agreement.
        stem = model_stems.unique(snake(singular(data.name)))
        class_name = pascal(stem)
        add(
            # Name the file after the class, not the raw label, so
            # `expenses` produces `expense.dart` holding `class Expense`.
            f"lib/models/{stem}.dart",
            _model_dart(data.name, data.description, data.kind, class_name, spec.package),
            origin="stub",
            note="data class from observed storage; fields unknown",
        )

    # ---- api client ------------------------------------------------------- #
    if spec.network_calls:
        add(
            "lib/data/api_client.dart",
            _api_client_dart(spec),
            origin="scaffold",
            note="endpoints recovered from the DEX string pool; unverified",
        )

    # ---- docs ------------------------------------------------------------- #
    add("README.md", _readme(spec, title))
    add("docs/SPEC.md", _spec_doc(spec))

    # ---- open questions --------------------------------------------------- #
    result.open_questions = _open_questions(spec)
    result.warnings = _warnings(spec)
    return result


# --------------------------------------------------------------------------- #
# Individual file builders
# --------------------------------------------------------------------------- #
def _routes_dart(screen_routes: list[tuple[str, str]], app_class: str) -> str:
    """Route table built from the already-unique stems.

    Takes the stems rather than re-deriving them from the screen names, so the
    route name, the file name and the class name cannot drift apart.
    """
    consts = ["  static const home = '/';"]
    entries = ["    AppRoutes.home: (_) => const HomeScreen(),"]

    for route, class_name in screen_routes:
        stem = route.strip("/")
        consts.append(f"  static const {stem} = '{route}';")
        entries.append(f"    AppRoutes.{stem}: (_) => const {class_name}(),")

    return templates.render(
        templates.ROUTES_DART,
        route_constants="\n".join(consts) + "\n",
        route_entries="\n".join(entries) + "\n",
    )


def _home_dart(
    title: str,
    screen_routes: list[tuple[str, str]],
    app_class: str,
    purpose: str,
) -> str:
    if screen_routes:
        tiles = []
        for route, _class_name in screen_routes:
            label = route.strip("/").replace("_", " ").capitalize()
            tiles.append(
                "        ListTile(\n"
                f"          title: Text('{label}'),\n"
                f"          trailing: const Icon(Icons.chevron_right),\n"
                f"          onTap: () => Navigator.pushNamed(context, '{route}'),\n"
                "        ),"
            )
        tile_source = "\n".join(tiles) + "\n"
    else:
        tile_source = "        const Center(child: Text('No screens identified.')),\n"

    return templates.render(
        templates.HOME_DART,
        title=dart_string(title),
        purpose=dart_string(_one_line(purpose) or "Behaviour not determined."),
        home_route_tiles=tile_source,
    )


def _screen_dart(screen, class_name: str, project_name: str, stem: str) -> str:
    shows = _bullet_list(screen.shows)
    actions = _bullet_list(screen.actions)
    evidence = ", ".join(screen.evidence) or "not recorded"

    blocks = []
    for show in screen.shows[:8]:
        blocks.append(
            "        Card(\n"
            "          child: ListTile(\n"
            f"            title: Text({dart_string(show)}),\n"
            "            trailing: const Icon(Icons.chevron_right),\n"
            "          ),\n"
            "        ),"
        )
    observed_blocks = "\n".join(blocks) + "\n" if blocks else ""

    items = []
    for show in screen.shows[:10]:
        items.append(f"        Text('• {show}'),")
    observed_items = (
        "\n".join(items) + "\n" if items else "        const SizedBox.shrink(),\n"
    )

    stub_detail = (
        f"Static analysis observed {len(screen.shows)} element(s) and "
        f"{len(screen.actions)} action(s) here, but cannot recover how they "
        f"behave. Confidence for this screen: {screen.confidence}."
    )

    return templates.render(
        templates.SCREEN_DART,
        package="",
        screen_name=dart_string(screen.name),
        class_name=class_name,
        purpose=dart_string(screen.purpose or "Purpose not determined."),
        evidence=evidence,
        shows="\n".join(shows),
        actions="\n".join(actions),
        observed_blocks=observed_blocks,
        observed_list_items=observed_items,
        stub_detail=dart_string(stub_detail),
    )


def _model_dart(
    name: str, description: str, kind: str, class_name: str, package: str
) -> str:
    # The real field list is unknowable from static analysis, so the class
    # carries one clearly-marked placeholder rather than inventing plausible
    # field names a developer might mistake for recovered facts.
    return templates.render(
        templates.MODEL_DART,
        package=package,
        model_name=name,
        description=description or "Observed to be stored by the original app.",
        kind=kind,
        class_name=class_name,
        fields="    required this.payload,\n",
        field_declarations=(
            "  /// Placeholder. The original class's fields could not be\n"
            "  /// recovered from decompiled bytecode.\n"
            "  final String payload;\n"
        ),
        from_json="      payload: json['payload']?.toString() ?? '',\n",
        to_json="        'payload': payload,\n",
        # Dart string interpolation is ${name}; Python f-string needs the
        # doubled brace to emit a literal one.
        debug_fields="${payload}",
    )


def _api_client_dart(spec: BehaviourSpec) -> str:
    consts: list[str] = []
    seen: set[str] = set()
    for call in spec.network_calls:
        endpoint = call.endpoint or call.purpose or ""
        if not endpoint or endpoint in seen:
            continue
        seen.add(endpoint)
        name = snake(endpoint)[:40] or "endpoint"
        consts.append(f"  static const {name} = {dart_string(endpoint)};")

    if not consts:
        consts.append("  // No endpoints were identified.")

    return templates.render(
        templates.API_CLIENT_DART,
        package=spec.package,
        endpoint_constants="\n".join(consts),
    )


def _readme(spec: BehaviourSpec, title: str) -> str:
    screens = "| Screen | Purpose | Confidence | Evidence |\n| --- | --- | --- | --- |\n"
    for s in spec.screens:
        screens += (
            f"| {s.name} | {s.purpose or '-'} | {s.confidence} | "
            f"{', '.join(s.evidence[:3]) or '-'} |\n"
        )
    if not spec.screens:
        screens += "| _none identified_ | | | |\n"

    features = (
        "\n".join(
            f"- **{f.name}**"
            + ("" if f.implemented else " _(appears stubbed)_")
            + (f" — {f.description}" if f.description else "")
            for f in spec.features
        )
        or "_none identified_"
    )

    data = (
        "\n".join(
            f"- **{d.name}** ({d.kind})"
            + (f" — {d.description}" if d.description else "")
            for d in spec.data_stored
        )
        or "_none identified_"
    )

    network = "| Purpose | Endpoint | Method | Evidence |\n| --- | --- | --- | --- |\n"
    for n in spec.network_calls:
        network += (
            f"| {n.purpose or '-'} | `{n.endpoint or '-'}` | {n.method or '-'} | "
            f"{', '.join(n.evidence[:2]) or '-'} |\n"
        )
    if not spec.network_calls:
        network += "| _none identified_ | | | |\n"

    permissions = "\n".join(
        f"- `{p}` — {why}" for p, why in spec.permissions_justified.items()
    )
    if not permissions:
        risky = "\n".join(f"- `{p}`" for p in spec.permissions_justified)
        permissions = risky or "_none justified_"

    return templates.render(
        templates.README,
        app_name=title,
        purpose=spec.purpose or "_Purpose could not be determined._",
        target_users=f"**For.** {spec.target_users}" if spec.target_users else "",
        screen_table=screens,
        feature_list=features,
        data_list=data,
        network_table=network,
        permission_table=permissions,
    )


def _spec_doc(spec: BehaviourSpec) -> str:
    lines = [
        "# Behaviour specification",
        "",
        "Machine-generated from static analysis. This is the input that "
        "produced the code in `lib/`.",
        "",
        "## Purpose",
        "",
        spec.purpose or "_Not determined._",
        "",
        "## Screens",
        "",
    ]
    for s in spec.screens:
        lines.append(f"### {s.name}  `confidence: {s.confidence}`")
        lines.append("")
        lines.append(s.purpose or "_Purpose not determined._")
        lines.append("")
        if s.shows:
            lines.append("Shows:")
            lines.extend(f"- {x}" for x in s.shows)
            lines.append("")
        if s.actions:
            lines.append("Actions:")
            lines.extend(f"- {x}" for x in s.actions)
            lines.append("")
        if s.evidence:
            lines.append(f"Evidence: {', '.join(s.evidence)}")
            lines.append("")

    lines += ["## Features", ""]
    lines.extend(
        f"- **{f.name}**"
        + ("" if f.implemented else " (appears stubbed)")
        + (f" — {f.description}" if f.description else "")
        for f in spec.features
    ) or ["_none_"]

    lines += ["", "## Caveats carried from analysis", ""]
    lines.extend(f"- {c}" for c in spec.caveats) or ["_none_"]

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Honesty helpers
# --------------------------------------------------------------------------- #
def _one_line(text: str, limit: int = 110) -> str:
    if not text:
        return ""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _open_questions(spec: BehaviourSpec) -> list[str]:
    """What a developer must supply, because analysis could not."""
    questions: list[str] = []

    if not spec.purpose:
        questions.append(
            "What does this app actually do? The purpose could not be "
            "determined from static analysis."
        )
    low = [s.name for s in spec.screens if s.confidence == "low"]
    if low:
        questions.append("Verify these low-confidence screens by hand: " + ", ".join(low))
    stubbed = [f.name for f in spec.features if not f.implemented]
    if stubbed:
        questions.append(
            "These features appear stubbed or dead in the original: " + ", ".join(stubbed)
        )
    if not spec.network_calls:
        questions.append(
            "No network endpoints were identified. If the original talks to a "
            "server, the endpoints are encrypted, obfuscated, or loaded at "
            "runtime and static analysis cannot see them."
        )
    for dep in spec.platform_dependencies:
        questions.append(f"Handle the platform dependency: {dep}")
    return questions


def _warnings(spec: BehaviourSpec) -> list[str]:
    warnings: list[str] = []
    total = len(spec.screens) + len(spec.features)
    if total < 3:
        warnings.append(
            f"Only {total} screens/features were identified. The original app "
            "may be larger than the reconstruction, or the analysis may have "
            "been too shallow."
        )
    if all(s.confidence == "low" for s in spec.screens) and spec.screens:
        warnings.append(
            "Every screen was inferred at low confidence. Treat this output "
            "as a starting point, not a specification."
        )
    return warnings
