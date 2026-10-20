# Sample reports

Committed output, so a reader can judge the tool without installing it. Each
file records what produced it and what it does **not** prove.

| File | Produced by | Needs a model? |
|---|---|---|
| `sample-f-droid.json` | `apksmith scan samples/F-Droid.apk --json ...` | No |
| `sample-f-droid.md` | the same command, `--markdown` | No |
| `fdroid-understanding.json` | `apksmith understand run ...` | Yes |
| `fdroid-understanding.md` | the same run, rendered | Yes |
| `sample-evaluation.md` | `apksmith evaluate run evaluation/suite.json` | No |

## The static report

Deterministic: re-running the command on the same APK reproduces the same
metrics. No network, no model, no jadx. Verified by regenerating it and
diffing:

```
total classes 24,520   own classes 3,881   third-party 84.2%   risk 78/100
```

`own classes` counts classes under the prefix that covers the launcher activity,
not under the manifest package. See `resolve_own_class_prefix` — an earlier
version used the declared package and reported 161.

## The understanding spec

Produced once, in October 2026, against a live API:

```
provider   OpenRouter
model      nvidia/nemotron-3-ultra-550b-a55b:free
calls      10   (10 entries in the response cache)
failures   0
app        F-Droid 2.0.1, unobfuscated
```

Token usage was not recorded by the tool at the time, so no token figure is
quoted here. The cached responses total about 54k characters, roughly 13k
output tokens; prompts add several thousand tokens each. That is an estimate,
not a measurement.

What it demonstrates: the free model returned parseable JSON for every chunk,
and every screen in the output cites source evidence. What it does not
demonstrate: that M2 works on obfuscated code, on other apps, or through the
Groq backend. Those are open items in the README roadmap.

## The evaluation report

Two hand-written references, not model-derived. F1 is agreement with those
references, not truth. The F-Droid case scores 0.619 while the small expense
tracker scores 1.000, which is the honest shape of the result: the tool handles
a toy app well and a real app partly.
