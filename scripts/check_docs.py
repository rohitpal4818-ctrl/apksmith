"""Fail when a documented fact disagrees with the repository's own artifacts.

Every number in the README is a claim. Claims drift: a test count goes stale
after one new test, a metric changes when the code under it is fixed, a roadmap
item keeps saying "not done" long after it shipped. Reviewers cannot tell a
stale number from an invented one, so both damage the project equally.

This script re-derives the checkable claims and compares them with the prose.
History files are exempt: the CHANGELOG is allowed to quote an old number while
explaining that it was wrong.

Run with::

    python scripts/check_docs.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Prose scanned for stale claims. CHANGELOG.md is deliberately absent.
SCANNED = ("README.md", "docs/ARCHITECTURE.md", "CONTRIBUTING.md")

#: Phrases that were true at some point and are not true now. Keeping them out
#: of the live docs stops a wrong number from being copied into a blog post.
STALE = {
    "990 of 11,949": "own-code counts came from a different, wrong prefix",
    "54 classes instead of 845": "the real pair is 161 and 3,881",
    "97%": "extract.py measures roughly 85%",
    "~1% of an APK": "own code is about 16% of classes",
    "Three apps": "the suite has two",
    "never been run against a live model": "M2 has been run live on OpenRouter",
    "needs an API key to prove live": "the live run is committed",
    "1,000 req/day free": "Groq's limits are per model and change",
    "56k tokens": "the artifact holds ~54k characters, not tokens",
}

problems: list[str] = []


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def check(label: str, ok: bool, detail: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"        {detail}")
        problems.append(label)


# --------------------------------------------------------------- test count
collected = subprocess.run(
    [sys.executable, "-m", "pytest", "--collect-only", "-q"],
    cwd=ROOT,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)
# pyproject sets addopts = "-q", so this is -qq and pytest prints one
# "tests/test_x.py: N" line per file instead of a summary.
per_file = [int(n) for n in re.findall(r":\s*(\d+)\s*$", collected.stdout or "", re.M)]
total_tests = sum(per_file)

for doc in ("README.md", "CONTRIBUTING.md"):
    for claimed in re.findall(r"#\s*(\d+)\s+tests", read(doc)):
        check(
            f"{doc} test count",
            int(claimed) == total_tests,
            f"says {claimed}, pytest collects {total_tests}",
        )

# ----------------------------------------------------------------- MCP tools
server = read("src/apksmith/mcp_server.py")
implemented = re.findall(r"@mcp\.tool\(\)\s*def\s+(\w+)", server)

readme = read("README.md")
documented_block = re.search(r"Tools: (.+?)\. Only", readme, re.S)
documented = (
    re.findall(r"`(apk_\w+)`", documented_block.group(1)) if documented_block else []
)
check(
    "README MCP tool list",
    documented == implemented,
    f"README lists {documented}; server defines {implemented}",
)

# -------------------------------------------------------- evaluation suite
suite = json.loads(read("evaluation/suite.json"))
n_cases = len(suite.get("cases", []))
evaluation = read("reports/sample-evaluation.md")
claimed_cases = re.search(r"A suite of (\d+) apps", evaluation)
check(
    "sample-evaluation case count",
    bool(claimed_cases) and int(claimed_cases.group(1)) == n_cases,
    f"report says {claimed_cases.group(1) if claimed_cases else 'nothing'}, "
    f"suite.json has {n_cases}",
)

# --------------------------------------------------------- sample report
report = json.loads(read("reports/sample-f-droid.json"))
metrics = report["metrics"]
check(
    "sample report own + third party == total",
    metrics["own_classes"] + metrics["third_party_classes"] == metrics["total_classes"],
    f"{metrics['own_classes']} + {metrics['third_party_classes']} "
    f"!= {metrics['total_classes']}",
)
check(
    "sample report third-party ratio",
    abs(
        metrics["third_party_ratio"]
        - round(metrics["third_party_classes"] / metrics["total_classes"], 4)
    )
    < 1e-9,
    "ratio does not match the class counts it is derived from",
)

# The README quotes these two numbers directly.
for claimed, actual in re.findall(r"([\d,]+) of ([\d,]+)\s*\n?classes", readme):
    check(
        f"README own/total classes {claimed} of {actual}",
        (int(claimed.replace(",", "")), int(actual.replace(",", "")))
        == (metrics["own_classes"], metrics["total_classes"]),
        f"report says {metrics['own_classes']} of {metrics['total_classes']}",
    )

# ------------------------------------------------------------ stale prose
for doc in SCANNED:
    text = read(doc)
    for phrase, why in STALE.items():
        check(f"{doc} does not say {phrase!r}", phrase not in text, why)

# The architecture doc names the failure mode with the real numbers, so make
# sure those numbers are still the ones in the report.
arch = read("docs/ARCHITECTURE.md")
quoted = {
    int(x.replace(",", "")) for x in re.findall(r"instead\s+of\s+([\d,]{4,})", arch)
}
check(
    "ARCHITECTURE prefix-failure numbers",
    bool(quoted) and quoted == {metrics["own_classes"]},
    f"quotes {sorted(quoted)}, report says {metrics['own_classes']} own classes",
)

print()
if problems:
    print(f"{len(problems)} documented claim(s) disagree with the repository:")
    for problem in problems:
        print(f"  - {problem}")
    sys.exit(1)

print("All documented claims agree with the repository.")
