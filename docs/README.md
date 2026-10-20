# Documentation

| Document | Read it when |
|---|---|
| [`../README.md`](../README.md) | You want to know what this does, how to install it, and what it cannot do. Start here. |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | You want to know how it is put together and why the hard parts are hard. |
| [`TESTING.md`](TESTING.md) | You are changing something and want to know what the tests pin, and what they deliberately do not. |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | You want to set up a development environment or send a change. |
| [`../reports/README.md`](../reports/README.md) | You want to know how the committed sample output was produced. |
| [`../CHANGELOG.md`](../CHANGELOG.md) | You want the history, including what was broken and why. |
| [`../SECURITY.md`](../SECURITY.md) | You found a vulnerability, or you are wondering what this tool assumes about its input. |

## A note on the numbers in these documents

Every figure that can be re-derived is re-derived, by
[`scripts/check_docs.py`](../scripts/check_docs.py), on every CI run. It compares
the prose with the committed artifacts — test count, MCP tool list, sample
report metrics, evaluation suite size — and fails the build when they disagree.
It also bans a list of phrases that were true at some point and are not true
now.

If you change a number in the README, either make the change consistent across
the repository or the lint job will tell you which document is lying.
