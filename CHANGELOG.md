# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Groq as an M2 backend**, selectable with `--provider groq`. Groq's free
  tier allows 30 requests/minute, 1,000 requests/day and 200k tokens/day, which
  is twenty times the request allowance of OpenRouter's free tier. The default
  model is `openai/gpt-oss-120b`, Groq's recommended replacement for the Llama
  models it retired from the free tier in August 2026. `--model` accepts any id
  the chosen provider serves.
- `--provider` and `--model` on `apksmith understand run`; the mock-friendly
  `LlmClient(provider=...)` routes endpoints, env vars and defaults per backend.
- The `--dry-run` output now names the provider and model it would have used.

### Changed

- `LlmClient` docs and error messages are provider-aware. A missing key names
  the right environment variable and the right signup URL instead of always
  saying `OPENROUTER_API_KEY`.
- The disk cache key now includes the provider and model, so switching backends
  cannot replay another provider's cached answer for an identical prompt.

### Fixed

- **`understand` deleted the system temp directory.** Cleanup called
  `shutil.rmtree(tmp_dir.parent)`, and because `mkdtemp()` returns
  `<tempdir>/apksmith-m2-XXXX`, `.parent` is the user's Temp folder. Every
  temporary file on the machine was removed after a run. It now removes only
  its own directory. `tests/test_temp_cleanup.py` greps the package for
  `rmtree(... .parent)` so the pattern cannot return.
- **`role_census()` reported `{'other': N}` for every app.** It was called
  before `rank()` populated `ClassSummary.role`, so the diagnostic always
  claimed the classifier had matched nothing. It now ranks first, and the
  pipeline orders the calls correctly.
- `_cache_put` used `contextlib.suppress` without importing `contextlib`. No
  test wrote to the cache, so the resulting `NameError` would only have
  appeared on the first live API call.

## [0.2.0] - 2026-10-18

M2 through M5. The project now runs from an APK to a runnable project.

### Added

- **`understand/` (M2)** — LLM understanding layer. Filters decompiled Java to
  compact class summaries (97% reduction measured), ranks classes by role,
  interleaves chunks so every batch has both screens and data classes, then
  describes and merges in two passes. Disk-cached by content hash.
- **`resolve_app_prefixes`** — works out which source subtree is the app's own.
  Handles the manifest package not being a source prefix, and library
  components injected into the manifest.
- **`generate/` (M3)** — BehaviourSpec to a runnable Flutter project. Pure
  code, no model: scaffolding, routing, theme, data classes and an API client
  are generated deterministically. Screen logic is left as `TODO` rather than
  invented. Every file carries a provenance header.
- **`mcp_server.py` (M4)** — seven MCP tools so an agent can drive the pipeline:
  `apk_identity`, `apk_analyse`, `apk_decompile`, `apk_extract`,
  `apk_understand`, `apk_generate`, `apk_coverage`.
- **`evaluate.py` (M5)** — scores specs against hand-written references with
  precision, recall, F1 and purpose token overlap. Reports state plainly that
  they measure agreement, not truth.
- **End-to-end pipeline tests** with a stub model, proving M2 needs no API key.
- **CI** across Linux, Windows and macOS on Python 3.11-3.13, plus an
  integration job that runs the real APK through the pipeline and asserts the
  report is sane.
- `scripts/fetch_samples.{sh,ps1}`, `CONTRIBUTING.md`, `LICENSE`,
  `docs/ARCHITECTURE.md`, `evaluation/example_spec.json`.

### Fixed

- `select()` raised `KeyError` on any app missing one of the six roles, which
  is most apps.
- Extracted class names were capturing the whole declaration line.
- Risk score pinned every app at 100. Replaced with a saturating curve.
- Launcher activities were flagged as medium risk, though they are required
  to be exported.
- All-zero sentinel strings were reported as hardcoded encryption keys.
- `singular("expenses")` returned `"expens"`, producing identifiers that read
  as typos.

### Known issues

- M2 has never been run against a live model. Prompt and parse paths are
  covered by tests; real-model behaviour is unverified.
- No cross-reference analysis, so findings stay at "a string exists".
- The evaluation suite covers two apps. Treat its numbers as a regression
  signal, not a benchmark.

## [0.1.0] - 2026-10-18

> Internal milestone, not a released tag. M1 through M5 were developed in a
> single pass and first published as `v0.2.0`. This section is kept as a record
> of what each stage contributed.

M1. Static analysis and reporting.

### Added

- **Static analysis** — permissions with a hand-curated risk table and a
  declared-versus-actually-used distinction, network endpoint extraction,
  third-party SDK fingerprinting, component and exported-surface analysis,
  WebView bridge detection, cryptographic primitive detection, native library
  inventory, and obfuscation metrics.
- **Reporting** to terminal, Markdown and JSON.
- **CLI** — `apksmith scan`.
- 20 tests, including an integration test against F-Droid that asserts a
  legitimate app does not trip the false-positive filter.
- `understand`-stage groundwork: `ingest/jadx.py` for optional decompilation.

### Notes

- Built with `androguard` 4.1.4, whose `get_all_dex()` returns raw DEX bytes
  from a generator rather than parsed objects. Handled explicitly.
- androguard is extremely chatty at DEBUG. Silenced by default, re-enabled with
  `APKSMITH_DEBUG=1`.

[Unreleased]: https://github.com/YOUR-USERNAME/apksmith/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/YOUR-USERNAME/apksmith/releases/tag/v0.2.0