# AGENTS.md

Instructions for an automated coding agent working in this repository. Written
for Jules, which reads this file automatically, and useful to any other agent.

## What this project is

APKSmith turns an Android `.apk` into three artefacts: a static risk report, a
plain-English behaviour spec, and a runnable Flutter project. It is a Python
package under `src/apksmith`, tested with pytest, documented in `docs/`.

`README.md` explains the pipeline, `docs/ARCHITECTURE.md` explains why it is
built this way, and `docs/TESTING.md` explains what the tests do and do not
cover. Read the first one before changing anything.

## Set up

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Verify before opening a pull request

These are the exact commands CI runs:

```bash
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python scripts/check_docs.py
python scripts/check_docstrings.py
python -m pytest
```

`make check` runs the same set where make is available.

## Rules that are not negotiable

### 1. Do not invent behaviour

This is a reverse-engineering tool, and its value rests on being honest about
its limits. Never write a docstring, README line or CHANGELOG entry claiming
the tool recovers something it cannot: original source, comments, native code,
or runtime behaviour. If you are unsure whether a claim is defensible, read
"What this does not do" in `README.md` and stay inside it.

### 2. The test count is checked

`scripts/check_docs.py` re-derives numbers quoted in the documentation. Adding
or removing a test changes the count in `README.md` and `CONTRIBUTING.md`. Run
the checker after touching tests: it names every file that disagrees and the
value it expects. Fix the documentation, never the checker.

### 3. Every public symbol needs a docstring

`scripts/check_docstrings.py` fails the build otherwise. A docstring says why
the thing exists, not what the next line does.

### 4. Output bytes are part of the contract

All file output goes through `apksmith.fileio.write_text`, which writes UTF-8
with `\n` regardless of platform, so generated projects are byte-identical on
Windows and Linux. Do not write files with `open()`, `Path.write_text()` or
`print(..., file=...)` inside `src/`.

### 5. Tests never touch the network, a model, or a JRE

M2 is tested with a stub client in `tests/test_pipeline_e2e.py`. No test may
read a real API key, call a provider, or require jadx. A test that needs the
network is a test that will fail on somebody else's machine.

### 6. Never commit a secret

`tests/test_no_secrets.py` scans every tracked file for the shape of a real
key. Keys belong in the environment only.

### 7. Do not touch generated or byte-pinned artefacts

- `samples/*.apk` is gitignored; `scripts/fetch_samples.sh` downloads it.
- `reports/sample-f-droid.json` is byte-reproducible and marked binary in
  `.gitattributes`. Do not reformat or re-serialise it.
- `tools/` is vendored, gitignored third-party content.
- `build/`, `dist/`, `.apksmith-cache/` are output directories.

## What cannot run in a fresh sandbox

There is no API key and no jadx, so these fail by design:

- `apksmith understand run ...` without `--dry-run`
- anything that needs `samples/F-Droid.apk`, which is not in git
- the live MCP registry tests unless `pip install -e ".[mcp]"` has been run

Do not add a skip, a mock or a fallback to make one of these pass. If a task
needs them, say so in the pull request instead of hiding it.

## Style

- Python 3.11+, `from __future__ import annotations` in every module.
- Type hints on public functions.
- Tests are plain functions with a sentence saying what would break without
  them. No `unittest.TestCase`, no test classes.
- One pull request, one concern. Do not reformat files you did not need to
  change.
- User-visible changes get a `CHANGELOG.md` entry under `[Unreleased]`.

## Version

Single source: `src/apksmith/__init__.py`. `pyproject.toml` reads it
dynamically. Do not hard-code a version anywhere else.

## Where things live

| Question | File |
|---|---|
| How do I add a static finding? | `src/apksmith/analyze/` |
| How is the model prompt built? | `src/apksmith/understand/prompt.py` |
| How is the Flutter project written? | `src/apksmith/generate/flutter.py` |
| How is a command wired? | `src/apksmith/cli.py`, `src/apksmith/commands/` |
| What do the tests actually cover? | `docs/TESTING.md` |
