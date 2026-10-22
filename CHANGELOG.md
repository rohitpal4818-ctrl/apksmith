# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Direct tests for the file writer.** `tests/test_fileio.py` covers the one
  function every artefact goes through: CRLF input, non-ASCII text, parent
  directory creation, and the returned path. The generate tests only proved
  that the templates happen to contain no CRLF; these prove the writer does
  not introduce any.
- **Jules setup.** `AGENTS.md` states the rules an automated agent must not
  break: no invented behaviour, no secrets, no network in tests, no writing
  files outside `fileio`, and what to do when the test count moves. An issue
  template carries the `jules` label so a task can be assigned from GitHub, and
  `docs/JULES.md` covers the one-time browser setup, what to hand Jules, and how
  to review the pull request it returns.
- **An obfuscated-tree test for M2.** A tree whose every identifier is one
  letter, run through extract, rank, select and the pipeline. It pins the limit
  rather than pretending there is none: role classification has nothing to
  match, so every class lands in `other`, but string literals survive and a
  spec is still produced. No shipped obfuscated APK has been tested yet, and
  the roadmap says so.

### Fixed

- **`write_text` only half-kept its promise.** The `newline="\n"` argument
  stops the platform from translating newlines, but it passes an existing
  `\r\n` straight through, so content assembled from a Windows-authored file
  reached disk with CRLF while the docstring promised LF. The writer now
  normalises `\r\n` and lone `\r` to `\n` first, and `tests/test_fileio.py`
  fails if that step is removed.
- **The extraction ratio was understated.** `extract.py` claimed roughly 85%
  on the strength of a one-off measurement. Re-measured on F-Droid 2.0.1 with
  jadx 1.5.6: 990 files totalling 10.9 MB become 705 KB of summaries, so the
  real reduction is **93.6%**. The README and ARCHITECTURE now quote the
  reproducible number and say how to reproduce it.

### Security

- **A guard against committing a live key.** `tests/test_no_secrets.py` scans
  every tracked text file for the shape of a real key from the providers this
  project can use, and a planted key fails the suite naming the file.
  `.env` and `.env.*` are now ignored, so a key kept for local runs cannot be
  added by accident; `.env.example` stays trackable. No real key has ever been
  committed — all 18 commits were scanned, and only placeholders such as
  `sk-or-v1-...` appear in the documentation and tests.

## [0.3.0] - 2026-10-20

### Added

- **Groq as an M2 backend**, selectable with `--provider groq`. Groq's free
  tier is larger than OpenRouter's on requests, though the published limits
  change per model and are not repeated here. The default model is
  `openai/gpt-oss-120b`, Groq's recommended replacement for the Llama models it
  retired from the free tier in August 2026. `--model` accepts any id the
  chosen provider serves. The routing is tested against a stub; no request has
  been sent to Groq yet.
- `--provider` and `--model` on `apksmith understand run`; the mock-friendly
  `LlmClient(provider=...)` routes endpoints, env vars and defaults per backend.
- The `--dry-run` output now names the provider and model it would have used.
- **`scripts/check_docs.py`**, run in CI, which re-derives the checkable claims
  in the README (test count, MCP tool list, sample metrics, evaluation suite
  size) and fails when the prose disagrees with the artifacts. It also bans a
  list of phrases that used to be true.
- **`reports/README.md`** recording how each committed sample was produced,
  including what it does not prove.
- **`apksmith mcp`**, so the MCP server is reachable like every other stage
  instead of only through `python -m apksmith.mcp_server`.
- **An `mcp` extra** (`pip install -e ".[mcp]"`). `_require_mcp` had been
  telling users to install `.[dev,mcp]` while no such extra existed.
- **`docs/USAGE.md`**, a task-oriented guide: install, one section per command,
  a table mapping each error message to its cause, and the honest limits.

### Changed

- **Provider details live in one table.** The provider -> environment variable
  and provider -> signup URL mappings were written out three times. They are
  now `KEY_ENV` / `KEY_URL` in `understand/llm.py`, with `key_env_var()` and
  `key_url()` as the accessors, and a test asserting every provider in
  `ENDPOINTS` has an entry in both.
- **CLI modules are named for what they do.** `m2.py` and `m3_m5.py` became
  `commands/understand.py`, `commands/generate.py` and
  `commands/evaluate.py`. A file called `m3_m5.py` describes a schedule, not a
  responsibility, and it held two unrelated command groups.
- **All file output goes through `fileio.write_text`**, replacing four copies
  of the same mkdir/encoding/newline logic.
- **Every public class and method has a docstring.** `evaluate.save_suite` was
  deleted instead: nothing called it, and it wrote Markdown despite its name.
- **`docs/README.md`** indexes the documentation, and **`docs/TESTING.md`**
  explains what each test file pins and what the suite deliberately does not
  cover. The README's tree now maps the whole repository rather than `src/`.
- `LlmClient` docs and error messages are provider-aware. A missing key names
  the right environment variable and the right signup URL instead of always
  saying `OPENROUTER_API_KEY`.
- The disk cache key now includes the provider and model, so switching backends
  cannot replay another provider's cached answer for an identical prompt.

### Fixed

- **The version was stated twice, and the two disagreed.** `pyproject.toml`
  said 0.1.0 while `apksmith.__version__` said 0.2.0, so `apksmith version`
  printed 0.2.0 and the packaging metadata carried 0.1.0 -- the number that
  would have reached an index was the wrong one. `pyproject.toml` now declares
  `dynamic = ["version"]` and reads `apksmith.__version__`, and a test fails if
  a literal version comes back.
- **The MCP server could not start on a current install.** `pip install mcp`
  now resolves to 2.x, which renamed `FastMCP` to `MCPServer`, so
  `apksmith mcp` failed with "The MCP SDK is not installed" -- on a machine
  where it was installed. The `[mcp]` extra is now pinned below 2.0, and the
  error distinguishes "missing" from "wrong version" instead of telling the
  user to install it again.
- **`apk_understand` sent the model table where the API expects a model name.**
  The MCP tool called `LlmClient(model=DEFAULT_MODEL)`, so the request body
  carried a dict in the `model` field and would have failed after the app had
  already been decompiled. It also hard-coded `OPENROUTER_API_KEY`, so a Groq
  user could not use the tool at all. It now takes a `provider` argument and
  lets the client resolve both the model and the key.
- **`generate` marked every nested file as skipped.** The "was this written"
  check compared a generated relative path (`lib/screens/home.dart`) against a
  set of basenames (`home.dart`), so the match never succeeded below the top
  level. It now compares resolved paths.
- **`own_classes` was counted from the manifest package**, which is the one
  thing `docs/ARCHITECTURE.md` warns not to do. F-Droid declares
  `org.fdroid.fdroid` but ships under `org.fdroid`, so the report claimed 161
  own classes instead of 3,881 and a third-party ratio of 99.3% instead of
  84.2%. `resolve_own_class_prefix` now mirrors `resolve_app_prefixes` at the
  DEX level and anchors on the launcher activity. `reports/sample-f-droid.*`
  was regenerated; the risk score is unchanged at 78.
- **Documented figures that could not be reproduced.** The README claimed "~1%
  of an APK is the app's own code" (it is ~16% of classes), quoted `990 of
  11,949` decompiled files alongside it, said text was reduced by 97% while
  `extract.py` measures 85%, said "54 classes instead of 845" where the real
  pair is 161 and 3,881, and described a two-app evaluation suite as three
  apps. All now use figures that can be re-derived from the committed APK.
- **M2 was described as never having been run live** in the README, the
  architecture doc and the changelog, after the F-Droid run had already been
  committed. Status text now matches reality, and the Groq backend is labelled
  as untested because it is.
- Generated reports and Flutter files inherited the platform's line ending, so
  a Windows run produced different bytes from a Linux run despite generation
  being described as deterministic. Every writer now passes `newline="\n"`.
- `understand` deleted the system temp directory. Cleanup called
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
  compact class summaries (roughly 85% byte reduction measured), ranks classes
  by role, interleaves chunks so every batch has both screens and data classes,
  then describes and merges in two passes. Disk-cached by content hash.
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

- M2 has been run live once, on F-Droid, an unobfuscated app. Behaviour on
  obfuscated code is unmeasured.
- The Groq backend is wired and tested against a stub, but no request has been
  sent to Groq.
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

[Unreleased]: https://github.com/rohitpal4818-ctrl/apksmith/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/rohitpal4818-ctrl/apksmith/releases/tag/v0.3.0
[0.2.0]: https://github.com/rohitpal4818-ctrl/apksmith/releases/tag/v0.2.0