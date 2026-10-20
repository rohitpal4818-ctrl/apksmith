# Architecture

How APKSmith is put together, and why. For usage see the [README](README.md).

## The pipeline

```
                    ┌──────────────────────────────────────────┐
  app.apk ─────────▶│ M1  ingest/ + analyze/ + report/        │
                    │     static, no model, no network        │
                    └───────────────┬──────────────────────────┘
                                    │ RiskReport (JSON)
                                    ▼
                    ┌──────────────────────────────────────────┐
                    │ jadx  decompile to readable Java          │
                    └───────────────┬──────────────────────────┘
                                    ▼
                    ┌──────────────────────────────────────────┐
                    │ M2  understand/extract.py                │
                    │     decompiled Java -> ClassSummary      │
                    │              ↓                           │
                    │     understand/rank.py                   │
                    │     pick the classes that describe it    │
                    │              ↓                           │
                    │     [LLM]  chunk -> describe -> merge    │
                    │              ↓                           │
                    │     understand/spec.py                   │
                    │     BehaviourSpec                        │
                    └───────────────┬──────────────────────────┘
                                    │ BehaviourSpec (JSON)
                                    ▼
                    ┌──────────────────────────────────────────┐
                    │ M3  generate/   NO MODEL USED            │
                    │     spec -> runnable Flutter project     │
                    └──────────────────────────────────────────┘

  M4  mcp_server.py   exposes all of the above as agent tools
  M5  evaluate.py     scores the BehaviourSpec against references
```

## Stage boundaries

Each stage has one input type and one output type, and does not reach past its
neighbours. That is what makes the pipeline testable: M3 is tested with a
hand-written spec, M1 with a real APK, and the whole of M2 with a stub model.

The cost is some duplication — `BehaviourSpec` is defined in `understand/` and
consumed by `generate/`, which means M3 depends on M2's module layout. This was
accepted deliberately. A shared neutral `specs/` package would be tidier, and
it would also blur the boundary the tests rely on: that M3 can be exercised
without importing anything from `understand/pipeline.py`.

## Where things live

Two kinds of module, and the distinction is enforced by review rather than by
imports:

- **Library packages** (`ingest/`, `analyze/`, `understand/`, `generate/`,
  `report/`) hold logic. They do not import Typer, they do not print, and they
  do not read environment variables. `understand/llm.py` takes an API key as an
  argument rather than reaching for `os.environ`, which is what lets the
  end-to-end tests run it against a stub.
- **Command modules** (`commands/`) hold Typer apps. They validate input, call
  one library function, and format the result. `commands/understand.py` is the
  only place in the codebase that reads `OPENROUTER_API_KEY`, and it reads it
  once, to construct the client.

The root commands (`scan`, `coverage`, `version`, `mcp`) are small enough to
live in `cli.py` directly. Everything with more than one option group gets its
own module under `commands/`. `mcp` is four lines because the server it starts
lives in `mcp_server.py`; the command exists so that M4 is reachable the same
way as every other stage, rather than only through `python -m`.

Directory names describe responsibility, not milestone. The milestones are a
sequence of work, not a decomposition of the problem, and a file called
`m3_m5.py` tells a reader nothing about what it contains. Milestone numbers
remain in the docs, the changelog and the `--help` text, where they order the
work without deciding where code goes.

## Output goes through one door

Every artefact is text, and all of it is written by `fileio.write_text`. That
single function exists because the same three bugs got fixed four times
otherwise: a missing parent directory, an encoding that depended on the
platform's codepage, and line endings that made a Windows run produce different
bytes from a Linux run. Centralising it means the determinism claim in the
README has one implementation to point at.

## Why some things are hard

### The DEX string pool is 99% noise

A single decompiled Kotlin class contains a `@Metadata` annotation holding
kilobytes of escaped binary, forty framework imports, and dozens of
compiler-generated lambda classes. Feeding that to a model wastes the context
window on characters that mean nothing.

`understand/extract.py` reduces measured text by roughly **85%** on F-Droid,
keeping the class declaration, field names, method signatures, string literals,
and a short body window. Everything it discards is listed in that module's
docstring. That figure comes from a single hand measurement, not a CI
assertion, so treat it as an order of magnitude rather than a precise number.

### 84% of an APK is somebody else's code

On F-Droid, 3,881 of 24,520 DEX classes belong to the app. The rest is OkHttp,
Compose, bouncycastle and friends. `resolve_own_class_prefix` (for metrics) and
`resolve_app_prefixes` (for decompiled source) decide which subtree is the
app's own, and it is subtler than it looks:

- The manifest package is often **not** a source prefix. F-Droid declares
  `org.fdroid.fdroid`, but its launcher is `org.fdroid.IconActivity` and most
  of its code lives under `org.fdroid`. Counting the declared package finds 161
  classes instead of 3,881.
- A library can **inject components** into the manifest. Room registers a
  service, ACRA registers crash-reporting components. Counting components to
  find the app's package picks `androidx` or `org` instead.
- So: trim segments from the manifest package and from the launcher's package,
  and take the narrowest one that both covers the launcher and contains a
  meaningful number of classes.

Getting this wrong does not raise an error. It reports 161 own classes instead
of 3,881, the third-party ratio reads 99% instead of 84%, and the app looks
trivially small. That failure mode shipped in the first published report and is
now pinned by `test_own_prefix_follows_entry_point_past_a_deeper_manifest_package`.

### Chunking decides output quality

A batch dominated by Activities produces a class listing. A batch dominated by
repositories produces data descriptions. Neither is behaviour. `_chunk`
interleaves by role so every chunk contains a screen *and* the data class it
uses, which is the minimum context needed to say what a screen does and where
its data comes from.

### Free models return malformed JSON often enough to design for

`parse_json_loose` peels responses in stages: direct parse, then markdown
fence, then the outermost brace span, then trailing-comma repair. When all of
that fails, the pipeline asks the model to fix its own output rather than
guessing. The end-to-end tests feed it fenced, comma-broken, and prose-wrapped
JSON to prove the path works.

Responses are cached by content hash on disk. For a free tier limited to 50
requests a day, this is the difference between being able to iterate and not.
The cache key covers provider, model, system prompt, user prompt, temperature
and max tokens, so changing any of them is a miss rather than a wrong answer.

### Providers are a routing table, not an abstraction layer

M2 has two backends and both speak the OpenAI chat format, so there is no
adapter hierarchy: `ENDPOINTS`, `DEFAULT_MODEL` and a per-provider environment
variable lookup are the whole mechanism. The differences that matter are
operational, not structural.

| | OpenRouter | Groq |
|---|---|---|
| Free tier | 20 req/min, 50 req/day | set per model; check the provider |
| Binding limit | requests | usually tokens |

Limits move. Rather than hard-code numbers that will rot, the point worth
keeping is the shape of the problem: the token limit, not the request limit, is
usually what decides how many runs you get. The committed F-Droid run made 10
calls whose cached responses total about 54k characters, roughly 13k output
tokens, with prompts adding several thousand tokens each. Reporting usage per
run matters more than reporting requests per run.

**Only OpenRouter has served a real request.** Groq's endpoint, environment
variable, default model and cache separation are pinned by tests, but no Groq
call has been made, so treat its limits and behaviour as second-hand.

### Generation consults no model

M3 is pure code. Scaffolding, routing, theme, data classes and the API client
are fully determined by the spec, so they are generated deterministically and
are correct by construction. The project compiles with no API key.

Screen logic is where judgement would be needed, and it is left as `TODO`
rather than invented. This also means a failure in M2 degrades one module
instead of three.

## The honesty problem

Reverse engineering invites overclaiming, and the most dangerous failure mode
here is a confident, wrong spec fed into code generation. Three mechanisms
address it:

1. **Confidence separate from severity.** A manifest claim is high confidence.
   A string-pool match is medium at best, because presence is not dataflow.
   Every finding keeps its literal evidence so it can be checked.
2. **False positives designed out, and tested.** A launcher activity must be
   exported. All-zero strings are not keys. A test asserts F-Droid does not
   score above 95.
3. **Generated code says what it is.** Every file carries a provenance header.
   The generated README has a table separating what is real from what is
   `TODO`. `GenerationResult.open_questions` lists what analysis could not
   answer, so a developer sees the gaps before starting work.

## What evaluation does and does not do

`evaluate.py` compares a generated spec against a **hand-written** reference —
deliberately not another model's output, which would measure nothing.

It reports precision, recall and F1 over fuzzy label matches, plus token
overlap on the purpose statement. These are reproducible and every number could
be argued with, which is the point: disagreement is visible.

They measure agreement with a human description. They do not measure truth, and
two apps is a demonstration rather than a benchmark. The report says so.

## Known gaps

| Gap | Consequence |
|---|---|
| No cross-reference analysis | Findings stay at "a string exists" rather than "this method calls this API" |
| No runtime analysis | Dynamically loaded code, encrypted assets and runtime-decided endpoints are invisible |
| No native code analysis | `.so` libraries are inventoried and otherwise treated as black boxes |
| M2 measured on one unobfuscated app | The committed live run used F-Droid; obfuscated code may yield much less |
| Groq backend never run live | Routing and cache keys are tested against a stub, not against Groq |
| Evaluation suite is small | Scores are a regression signal, not a benchmark |