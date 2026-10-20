# Usage

Everything here works without an API key except `understand`, which needs one.
`scan` needs nothing at all: no key, no network, no Java.

## Install

Requires Python 3.11 or newer.

```bash
git clone https://github.com/rohitpal4818-ctrl/apksmith.git
cd apksmith

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Check it:

```bash
apksmith version
apksmith --help
```

## Get a sample APK

```bash
bash scripts/fetch_samples.sh    # Windows: .\scripts\fetch_samples.ps1
```

Or use any `.apk` you already have. Split bundles (`.xapk`, `.apks`) are not
supported; extract the base `.apk` first.

## Scan an APK (M1)

This is the command most people want.

```bash
apksmith scan samples/F-Droid.apk
```

You get identity, permissions with a risk weight, exported components, network
endpoints, third-party SDKs, obfuscation metrics and a 0-100 risk score.

Write the report out:

```bash
apksmith scan samples/F-Droid.apk \
    --json reports/my-app.json \
    --markdown reports/my-app.md

apksmith scan samples/F-Droid.apk --top 30   # more findings on screen
```

## Understand what it does (M2)

Needs **jadx** on `PATH` (<https://github.com/skylot/jadx/releases>) and one API
key, because this is the stage that calls a model.

See what would be sent, for free:

```bash
apksmith understand run samples/F-Droid.apk --dry-run
```

Then:

```bash
export OPENROUTER_API_KEY="sk-or-..."          # PowerShell: $env:OPENROUTER_API_KEY = "..."
apksmith understand run samples/F-Droid.apk \
    --json reports/spec.json \
    --out reports/spec.md
```

Groq instead:

```bash
export GROQ_API_KEY="gsk_..."
apksmith understand run app.apk --provider groq --json reports/spec.json
```

Useful options: `--max-classes` (default 60) controls how much of the app is
described; `--decompiled <dir>` reuses an existing jadx tree and skips
decompiling; `--keep-decompiled` stops the temporary tree being deleted.

## Generate a Flutter project (M3)

```bash
apksmith generate run reports/spec.json --out build/my-app
cd build/my-app
flutter pub get
flutter run
```

No model, no key, deterministic output. Be clear about what you get: routing,
theme, data classes and an API client are real; **screen logic is `TODO`**. The
generated `README.md` and `docs/SPEC.md` mark every file's origin.

## Score the pipeline (M5)

```bash
apksmith evaluate run evaluation/suite.json --out reports/evaluation.md
```

The references are hand-written from public documentation. The score measures
agreement with a human reading, not truth.

## Use it from an agent (M4)

```bash
pip install -e ".[mcp]"
apksmith mcp
```

The server speaks stdio, so an MCP client launches it. Claude Desktop or Cursor
configuration:

```json
{
  "mcpServers": {
    "apksmith": {
      "command": "apksmith",
      "args": ["mcp"],
      "env": { "OPENROUTER_API_KEY": "sk-or-..." }
    }
  }
}
```

Seven tools: `apk_identity`, `apk_analyse`, `apk_decompile`, `apk_extract`,
`apk_understand`, `apk_generate`, `apk_coverage`. Only `apk_understand` needs a
key, and it accepts `provider: "groq"`.

## When something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| `apksmith: command not found` | virtualenv not active | activate it, then `pip install -e ".[dev]"` |
| `Activate.ps1 cannot be loaded` | Windows execution policy | `Set-ExecutionPolicy -Scope Process RemoteSigned` |
| `jadx not found` | M2 decompiles the APK first | install jadx, or pass `--decompiled <dir>` |
| `No OPENROUTER_API_KEY set` | key missing | set the key, or use `--dry-run` |
| `The MCP SDK is installed ... needs the 1.x API` | mcp 2.x renamed `FastMCP` | `pip install "mcp>=1.0,<2"` |
| `429` from the provider | free-tier rate limit | wait for the window, or `--provider groq` |
| `Not a valid ZIP/APK` | corrupt or split bundle | use the base `.apk` |
| Spec parses but screens are empty | model described too little | raise `--max-classes`, check `docs/SPEC.md` |

## What this will not do

`apksmith coverage` prints the current list. In short: it does not run the app,
does not capture network traffic, cannot recover behaviour that only exists in
a native library or at run time, and leaves generated screen logic to you.
Obfuscated apps are a known untested area.
