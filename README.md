# APKSmith

Static analysis and behaviour reconstruction from Android APKs.

APKSmith takes an `.apk`, works out what it **declares** it can do and what it
**actually** does, infers a plain-English description of its behaviour, and
generates a runnable project skeleton from that description.

```
APK  ->  static report  ->  decompiled Java  ->  behaviour spec  ->  Flutter project
       (M1)                (jadx)                (M2, LLM)          (M3, no LLM)

plus:  MCP server so an agent can drive it (M4)
       evaluation harness that scores the output (M5)
```

**Status:** all five milestones have code and tests. M2 has never been run
against a live model, because that needs an API key.

---

## What this does not do

Read this before trusting any output.

- **It cannot recover original source.** Comments, variable names and structure
  are destroyed at compile time. Obfuscation removes what is left. Native `.so`
  libraries cannot be decompiled at all.
- **Generated projects are scaffolds.** Structure, routing and data models are
  real. Screen logic, state and business rules are `TODO`, and the code says so
  in every file.
- **Findings are not proofs.** String-pool matching is not dataflow analysis. A
  present string is not proof a code path reaches it. Every finding carries its
  evidence and a confidence level so you can check it.
- **The eval numbers measure agreement with a human-written reference**, not
  truth, and not with a model-derived reference.

---

## Install

Requires Python 3.11+, and for decompilation, jadx.

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"
```

### jadx (optional, needed for M2)

Download from <https://github.com/skylot/jadx/releases> and put `jadx` on
PATH. The CLI build needs a JRE; the `-with-jre-win` bundle includes one and
runs on Windows ARM via x64 emulation.

---

## Usage

```bash
# M1: static analysis. No API key, no jadx.
apksmith scan app.apk
apksmith scan app.apk --json reports/app.json --markdown reports/app.md

# M2: what does it do? Needs jadx and an API key (OpenRouter or Groq).
apksmith understand run app.apk --dry-run          # see the prompts, free
apksmith understand run app.apk --json reports/understanding.json
apksmith understand run app.apk --provider groq    # 1,000 req/day free

# M3: spec -> project. No API key.
apksmith generate run reports/understanding.json --out build/recon

# M5: score against hand-written references.
apksmith evaluate run evaluation/suite.json

# What this tool cannot do.
apksmith coverage
```

Exit codes: `0` clean, `1` error, `2` risk score ≥ 80.

### Model providers for M2

M2 is the only stage that calls a model. Two backends, both with a free tier:

| Provider | Flag | Env var | Default model | Free tier |
|---|---|---|---|---|
| OpenRouter | *(default)* | `OPENROUTER_API_KEY` | `nvidia/nemotron-3-ultra-550b-a55b:free` | 20 req/min, 50 req/day |
| Groq | `--provider groq` | `GROQ_API_KEY` | `openai/gpt-oss-120b` | 30 req/min, 1,000 req/day, 200k tokens/day |

```bash
# OpenRouter
export OPENROUTER_API_KEY=sk-or-v1-...
apksmith understand run app.apk

# Groq
export GROQ_API_KEY=gsk_...
apksmith understand run app.apk --provider groq

# Any other model on either backend
apksmith understand run app.apk --provider groq --model openai/gpt-oss-20b
```

Free keys: <https://openrouter.ai/keys> and <https://console.groq.com/keys>.
Neither needs a card.

Two things to know before you budget a run:

- **Responses are cached by content hash** under `.apksmith-cache/`. Re-running
  on an unchanged APK costs nothing. The cache key includes the provider and
  model, so switching backends does not replay another provider's answer.
- **Tokens bind before requests do.** An F-Droid-sized run is roughly 56k
  tokens across 10 calls. That is 3 runs/day on Groq's free tier even though
  the request cap would allow 1,000.

Groq's 8k tokens/minute limit is the practical constraint: one chunk prompt is
around 4k tokens, so expect two calls a minute. Batch work only, not interactive.

### As an MCP server

```bash
pip install mcp
python -m apksmith.mcp_server
```

Tools: `apk_identity`, `apk_analyse`, `apk_decompile`, `apk_extract`,
`apk_understand`, `apk_generate`, `apk_coverage`. Only `apk_understand` needs
an API key.

---

## Architecture

```
apksmith/
  ingest/       APK -> parsed objects
    apkfile.py    validation, SHA-256, DEX strings/classes/methods, native libs
    manifest.py   AndroidManifest.xml -> identity, components, deep links
    jadx.py       optional decompilation to readable Java
  analyze/      parsed -> typed findings
    permissions.py  risk-weighted table; declared vs actually-used
    code.py        endpoints, WebView bridges, crypto primitives
    sdks.py        third-party SDK fingerprinting
    structure.py   exported surface, native libs, obfuscation metrics
  understand/   M2: source -> behaviour spec
    extract.py     decompiled Java -> compact class summaries
    rank.py        role classification, class selection
    llm.py         provider routing (OpenRouter/Groq), disk cache, rate limits
    prompt.py      prompt construction and the JSON contract
    spec.py        BehaviourSpec output model
    pipeline.py    resolve package, chunk, extract, merge, synthesise
  generate/     M3: spec -> project
    naming.py      identifier derivation
    templates.py   Dart/Flutter templates
    flutter.py     project builder
  evaluate.py   M5: scoring against references
  mcp_server.py M4: MCP tools
  report/       terminal | markdown | JSON
  app.py        pipeline orchestration
  models.py     every finding, as validated Pydantic models
  cli.py        command-line interface
```

### Decisions worth knowing about

**Declared is not used.** A permission in the manifest is a claim. A call to
`TelephonyManager.getDeviceId()` in the DEX is evidence. Both are recorded,
because a dangerous permission that is declared but never used is a different
situation from one that is used.

**Confidence is separate from severity.** Manifest claims are high confidence.
Code-derived claims are capped lower, because finding a string does not prove a
code path reaches it.

**Only ~1% of an APK is the app's own code.** On F-Droid, 990 of 11,949
decompiled files. Filtering by package before spending any tokens is the single
biggest cost saving in the pipeline. Decompiled text is then reduced a further
97% by stripping `@Metadata` blobs, framework imports and synthetic lambda
classes.

**The manifest package is not a source prefix.** F-Droid declares
`org.fdroid.fdroid` but ships code under `org/fdroid/`. Filtering on the package
name found 54 classes instead of 845 and looked like "this app is trivial"
rather than like a bug. The resolver trims segments and anchors on the entry
point; see `resolve_app_prefixes`.

**Risk score saturates.** Summing severity weights pins every app at 100.
Instead `100 × (1 − e^(−total/200))`, so growth stays meaningful:
total 100 → 39, 400 → 86.

**Generation is deterministic.** M3 consults no model. Scaffolding, routing,
theme, data classes and the API client are generated by code and are correct by
construction, so the output compiles with no API key. Only screen logic would
need a model, and it is left as `TODO` rather than invented.

**False positives are designed out.** A launcher activity must be exported, so
flagging it is noise. All-zero sentinel strings are not encryption keys. There
is a test asserting F-Droid does not score above 95.

---

## Testing

```bash
pytest                    # 101 tests, no key or network needed
ruff check src tests      # lint
ruff format src tests     # format
```

Integration tests need a real APK and skip cleanly without it:

```bash
bash scripts/fetch_samples.sh      # PowerShell: .\scripts\fetch_samples.ps1
pytest
```

F-Droid is Apache-2.0 and is used as a known-good baseline: a legitimate app
that should not produce a wall of false positives.

**M2 is tested without an API key.** `tests/test_pipeline_e2e.py` drives the
whole understanding pipeline with a stub model that deliberately returns fenced
JSON, trailing commas and prose wrapping. If the pipeline survives that, it
survives a free model.

Tests assert properties rather than exact text — every route resolves to a real
file, Dart braces balance, no unsubstituted placeholders remain, every generated
file carries provenance, no high-severity claim lacks evidence, and no
third-party or synthetic code reaches a prompt.

## Sample output

Committed so you can see results without running anything:

| File | What it is |
|---|---|
| [`reports/sample-f-droid.md`](reports/sample-f-droid.md) | Static report on F-Droid, rendered |
| [`reports/sample-f-droid.json`](reports/sample-f-droid.json) | The same report, machine-readable |
| [`reports/sample-evaluation.md`](reports/sample-evaluation.md) | Evaluation against hand-written references |

Try it yourself without any of that committed:

```bash
apksmith scan samples/F-Droid.apk
apksmith generate run evaluation/example_spec.json --out build/recon
```

## Further reading

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how it fits together and
  why the hard parts are hard
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — setup, and what this project believes
- [`CHANGELOG.md`](CHANGELOG.md) — what changed and what is still broken

---

## Roadmap

| Milestone | Contents | Status |
|---|---|---|
| M1 | Static analysis + reporting | Done |
| M2 | LLM understanding layer | Built and tested; **needs an API key to prove live** |
| M3 | Flutter project generation | Done |
| M4 | MCP server | Done |
| M5 | Evaluation harness | Done |

Next steps, in order of value:

1. Run M2 on F-Droid with a real key and see whether the free model returns
   usable JSON. The pipeline is tested with a stub, but real-model behaviour is
   unverified.
2. Grow the evaluation suite past two apps. Two is a demonstration, not a
   benchmark.
3. Add real cross-reference analysis so findings can be promoted from
   "a string exists" to "this method calls this API".

---

## Legal

Use this on APKs you own, on open-source apps, in security research, or where
you have permission. Reverse engineering for interoperability, study and
defensive security is legitimate. Repackaging someone else's commercial app to
defeat its licensing is not — the tools are the same, the line is not.

## Licence

MIT