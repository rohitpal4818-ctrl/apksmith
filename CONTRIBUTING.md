# Contributing to APKSmith

Thanks for looking. This document covers how to set up, what the project
believes, and what a good pull request looks like.

## Setup

```bash
git clone https://github.com/rohitpal4818-ctrl/apksmith.git
cd apksmith

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
```

Optional but recommended — the integration tests:

```bash
bash scripts/fetch_samples.sh    # PowerShell: .\scripts\fetch_samples.ps1
```

They skip cleanly if the sample APK is absent, so this is never required.

### jadx

M2 needs jadx on `PATH`. Download from
<https://github.com/skylot/jadx/releases>. Everything else works without it.

## Running things

```bash
pytest                          # 101 tests, no key or network needed
ruff check src tests            # lint
ruff format src tests           # format
```

To try the pipeline on a real APK:

```bash
apksmith scan samples/F-Droid.apk
apksmith understand run samples/F-Droid.apk --dry-run    # free, shows prompts
```

## What this project believes

These are not style preferences. Changes that violate them will be declined,
because they break guarantees the tests enforce.

**1. Never claim more than we know.** Static analysis of a compiled binary is
inherently lossy. A string in the DEX pool is not proof a code path reaches it.
Findings carry a confidence level and their literal evidence. If you add an
analyser that cannot justify itself, it belongs in the evaluation harness, not
in the findings list.

**2. Design out false positives.** A launcher activity is *required* to be
exported. Flagging it is noise. All-zero sentinel strings are not encryption
keys. There is a test asserting F-Droid does not score above 95, and a new
analyser that breaks it is a bug in the analyser.

**3. Generation is deterministic.** M3 consults no model. Scaffolding that can
be derived from the spec is derived by code, so the output is correct by
construction and compiles with no API key. Screen logic stays `TODO` rather
than being invented. Please do not add a model call to the generator.

**4. Tests assert properties, not text.** "Every route resolves to a file",
"braces balance", "no unsubstituted placeholders", "every generated file
carries provenance", "no high-severity claim lacks evidence". Snapshot tests
break on every edit and prove nothing.

**5. The evaluation reference must be human-written.** Comparing model output
to another model's output measures nothing. References come from public
documentation, and `evaluation/suite.json` says so in a `_comment` field that a
test asserts on.

## Adding an analyser

1. Add the finding type to `models.py` if it is new.
2. Create `analyze/your_analyser.py` with a function taking the loaded APK and
   returning typed results plus findings.
3. Register it in `app.py`.
4. Add tests: one for a true positive, one for the obvious false positive you
   were tempted to skip, one for empty input.
5. Re-run the suite and check the F-Droid risk score has not moved much.

## Pull requests

- One concern per PR. Split refactors from behaviour changes.
- New behaviour comes with a test that fails without it.
- Update `README.md` if you change a CLI command or a design decision. The
  "Decisions worth knowing about" section is the most-read part of this repo.
- Add a line to `CHANGELOG.md` under Unreleased.

## Reporting a bug

Include the command you ran, the output, your Python version and OS. If it is
an analysis result that looks wrong, say what the app actually does — that
turns a vague bug report into a fixable one.

## Security

Report security issues privately rather than in a public issue. Use GitHub's
private vulnerability reporting if it is enabled for the repository.

## Licence

MIT. By contributing you agree your work is licensed under it.