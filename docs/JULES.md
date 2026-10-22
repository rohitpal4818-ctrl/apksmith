# Using Jules on this repository

[Jules](https://jules.google) is Google's asynchronous coding agent. It clones
the repository into a cloud VM, plans the change, writes code, runs what it can,
and opens a pull request. It never merges.

This page covers the one-time setup, what to hand it, and how to review what
comes back. Repository rules live in [`AGENTS.md`](../AGENTS.md), which Jules
reads automatically.

## One-time setup (browser, roughly five minutes)

1. Open <https://jules.google.com> and sign in with a Google account. Accept the
   privacy notice once.
2. Click **Connect to GitHub account**, complete the flow, and grant access to
   this repository.
3. Confirm the repository appears in the selector.
4. Create the `jules` label once under **Issues → Labels**, if it is not there
   already. Issue templates only apply labels that exist.

Nothing is installed locally. There is no CLI step for this project.

## Two ways to start a task

**From the web UI.** Pick the repository, pick the branch, write the prompt,
then **Give me a plan**. Review the plan before approving any code change.

**From GitHub.** Open an issue with the *Jules task* template and keep the
`jules` label. The template asks for the four things that make a task work:
what to change, what must not change, what "done" means, and optional context.

## What to hand it

Good tasks are small, testable, and produce a diff a human can read in a minute.

| Kind | Example |
|---|---|
| A test | "Write a test proving `write_text` emits LF when given CRLF" |
| A bug with a reproduction | "`generate` reports every nested file as skipped; here is the output" |
| Documentation | "Add the real error text to the error table in `docs/USAGE.md`" |
| A dependency bump | "Move the `mcp` pin to `>=1.0,<3` and run the suite" |
| CI plumbing | "Add Python 3.14 to the test matrix" |
| A small feature | "Add `--fail-on-risk N` to `scan`, exiting 3 above the threshold" |

## What not to hand it

| Task | Why it fails here |
|---|---|
| Running M2 on a real APK | `samples/*.apk` is gitignored; the VM has no APK, jadx or JRE |
| A live provider test | That needs an API key, and a key in a sandbox is a leak |
| "Refactor the architecture" | Too large to review, and the plan will be fiction |
| Verifying a measured number | Requires decompiling a real app; see `docs/TESTING.md` |
| A code review | Jules writes code; it is not a reviewer |

## Reviewing the pull request

CI runs eleven jobs on every pull request, so start there. Then, locally:

```bash
git fetch origin pull/<number>/head:jules-review
git checkout jules-review

python -m pytest
python -m ruff check src tests scripts
python scripts/check_docs.py
python scripts/check_docstrings.py
```

Red flags worth a second look:

- **A doc number changed but no test did.** `check_docs.py` derives those
  numbers from the tests; a hand-edited number is the failure this project has
  hit before.
- **A new `skip` or `xfail`.** The suite must not grow holes to make a change
  look green.
- **A rewritten file that the task never mentioned.** Reformatting hides the
  real diff.
- **A claim that the tool recovers something it cannot.** See *What this does
  not do* in the README.

## Limits

| Plan | Tasks per day | Concurrent |
|---|---|---|
| Free | 15 | 3 |
| Pro | 100 | 15 |
| Ultra | 300 | 60 |

Free tier runs on Gemini Flash models. The exact model is shown in the Jules
UI and changes as Google ships new ones, so this page does not pin it. The free
tier is enough for a few small pull requests a day.
