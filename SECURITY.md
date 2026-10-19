# Security Policy

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

APKSmith parses untrusted input by design — that is the entire job — so a
crash, hang or excessive-resource-use bug in the parsers is a real finding.
Report it privately:

1. Use GitHub's **Report a vulnerability** button on the Security tab, if it
  is enabled for this repository.
2. Otherwise open a private security advisory.
3. If neither works, email the maintainer directly. The address is in the git
   log of the first commit.

Please include:

- The APK or input file, or a minimal reproduction that does not need one
- Your Python version and OS
- Whether the bug is a crash, a hang, unbounded memory, or an incorrect
  analysis result

## What is in scope

| Area | Concern |
|---|---|
| `ingest/apkfile.py` | ZIP bomb, path traversal on extraction, malformed DEX |
| `ingest/manifest.py` | Malformed binary XML, entity expansion |
| `ingest/jadx.py` | Command injection via APK path; `subprocess` is called without a shell |
| `understand/extract.py` | ReDoS in the regexes over hostile input |
| `understand/llm.py` | API key leakage into logs or the on-disk cache |
| Cache files | `~/.apksmith-cache` may contain decompiled source. Treat as sensitive. |
| MCP server | Tool input validation; the server runs with the caller's privileges |

## What is out of scope

- **APKSmith produces analysis of third-party apps.** That is its purpose and
  is not a vulnerability in this project.
- Findings that are technically wrong. Those are bugs, and very welcome as
  issues, but not security reports.
- Running the tool against an app you have no permission to analyse. That is a
  legal question, not a security one.

## Trust model

APKSmith is designed to handle hostile input, and these are the properties it
maintains:

- **No shell.** `jadx` is invoked as an argv list, never through a shell, so a
  filename cannot become a command.
- **No network except the LLM call.** `scan` and `generate` never touch the
  network. Only `understand` calls OpenRouter, and only with your key.
- **Nothing is written outside the output directory.** Decompiled output goes
  to a temp directory or to a path you pass.
- **Your key is never written to the repo.** It is read from the environment
  only. The on-disk response cache stores model responses, not credentials.

## Non-production warning

This is a research and educational tool. Do not run it as a service on
untrusted input without reading `ingest/` and `ingest/jadx.py` first.