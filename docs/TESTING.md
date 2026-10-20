# Testing

```bash
pytest                                    # everything that needs no key
pytest tests/test_apksmith.py             # one file
pytest -k "prefix"                        # one idea
pytest --cov=apksmith --cov-report=term   # with coverage
```

No API key and no network are required. Tests that need the sample APK skip
cleanly when `samples/F-Droid.apk` is absent, which is why a fresh clone can run
the suite before downloading anything.

```bash
bash scripts/fetch_samples.sh      # or: .\scripts\fetch_samples.ps1
pytest
```

## The layers

The suite is organised by how much of the system each test commits to. Knowing
which layer a change belongs in is most of the work.

**Unit tests** assert one function's contract, with no filesystem and no
process. Risk-score arithmetic, identifier derivation, `parse_json_loose`,
prefix resolution from a list of class names.

**Pipeline tests** drive a stage end to end against real inputs from the
repository: an APK, a spec, a reference suite. They assert properties rather
than exact strings, because exact output changes every time a template is
improved and would make the suite a transcription exercise.

**End-to-end tests** run M2 with a **stub model client**. The stub returns
deliberately awkward JSON — fenced, trailing commas, prose wrapper — so the
parse path is exercised without a request. This is what lets the project claim
that M2 is tested without an API key.

**Integration tests** run the whole thing on a real APK and are excluded from
the default run only in the sense that they skip without the sample. CI
downloads it and runs them for real.

**Guards** are tests that exist because something went wrong once and should
never go wrong again. They have names like
`test_cleanup_removes_our_directory_only` and a comment explaining the bug.

## Which file pins what

| File | Pins |
|---|---|
| `test_apksmith.py` | M1 findings, risk curve, renderers, own-code prefix resolution |
| `test_understand.py` | Extraction, class ranking, chunking, spec merging |
| `test_pipeline_e2e.py` | Full M2 run through a stub model; M2 output consumed by M3 |
| `test_providers.py` | Provider routing, env isolation, cache separation, 429 messages |
| `test_generate_eval.py` | M3 generation, M5 scoring, the MCP server's live tool registry, LF output |
| `test_collisions.py` | Generated filename collisions, which used to overwrite files |
| `test_cli_validation.py` | Bad `--provider` and `--decompiled` fail before any work |
| `test_temp_cleanup.py` | The temp-directory deletion bug, by grepping for the pattern |
| `test_docs_claims.py` | The claim checker still passes, and can still fail |
| `test_finalize_repo.py` | The one-time publication helper |

## What the tests deliberately do not cover

- **A live model.** Requests cost money and are non-deterministic. The stub
  covers the parse path; the committed F-Droid run covers the live path once.
- **Obfuscated apps.** Every bundled fixture is unobfuscated. This is a known
  gap, not an oversight — see the roadmap in the README.
- **Groq.** The routing is pinned; no request has been made.
- **Decompilation itself.** `test_pipeline_e2e.py` uses pre-decompiled fixtures
  or `--dry-run`, because requiring a JRE would make the default suite
  un-runnable. CI installs Java and decompiles a real APK instead.

The MCP tests are the exception to "no live server": when the SDK is installed,
`build_server()` is asked for its tool list rather than the source being
grepped. A tool that is written but not registered is a real failure mode, and
it is invisible to a text search.

## What CI runs

| Job | What it proves |
|---|---|
| `test (os, py)` | The suite passes on Linux, Windows and macOS, Python 3.11–3.13 |
| `integration (real APK)` | Download, analyse, decompile, generate, evaluate — on a real app |
| `lint` | `ruff check`, `ruff format --check`, and `scripts/check_docs.py` |

The matrix is deliberately wide. Twice this project has been broken only on one
operating system: a removed `rmtree` path that behaved differently, and line
endings that made generated files differ by platform.

## Adding a test

Prefer a property over a string. Prefer a real input from `evaluation/` or
`samples/` over an invented one. If the test exists because of a specific bug,
name it after the bug and write the story in the docstring — the next person
needs to know what makes it worth keeping.
