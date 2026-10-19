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

## Why some things are hard

### The DEX string pool is 99% noise

A single decompiled Kotlin class contains a `@Metadata` annotation holding
kilobytes of escaped binary, forty framework imports, and dozens of
compiler-generated lambda classes. Feeding that to a model wastes the context
window on characters that mean nothing.

`understand/extract.py` reduces measured text by **97%** on F-Droid, keeping the
class declaration, field names, method signatures, string literals, and a short
body window. Everything it discards is listed in that module's docstring.

### 92% of an APK is somebody else's code

On F-Droid, 990 of 11,949 decompiled files belong to the app. The rest is
OkHttp, Compose, Room and friends. `resolve_app_prefixes` decides which subtree
is the app's own, and it is subtler than it looks:

- The manifest package is often **not** a source prefix. F-Droid declares
  `org.fdroid.fdroid` and ships code under `org/fdroid/`.
- A library can **inject components** into the manifest. Room registers a
  service, ACRA registers crash-reporting components. Counting components to
  find the app's package picks `androidx` or `org` instead.
- So: trim segments from the manifest package and from the entry point's
  package, and take the narrowest one that both covers the entry point and
  contains a meaningful number of source files.

Getting this wrong does not raise an error. It returns 54 classes instead of
845 and the app looks trivially small. That failure mode is why
`test_resolve_prefix_handles_manifest_package_with_extra_segment` exists.

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
three apps is a demonstration rather than a benchmark. The report says so.

## Known gaps

| Gap | Consequence |
|---|---|
| No cross-reference analysis | Findings stay at "a string exists" rather than "this method calls this API" |
| No runtime analysis | Dynamically loaded code, encrypted assets and runtime-decided endpoints are invisible |
| No native code analysis | `.so` libraries are inventoried and otherwise treated as black boxes |
| M2 never run live | The prompt and parse paths are proven by tests, not by a real free model |
| Evaluation suite is small | Scores are a regression signal, not a benchmark |