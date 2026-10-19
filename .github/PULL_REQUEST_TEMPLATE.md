## What this changes

<!-- One or two sentences. What does this PR do, and why? -->

## Type of change

- [ ] Bug fix (non-breaking change that fixes a problem)
- [ ] New feature (non-breaking change that adds capability)
- [ ] Breaking change (existing behaviour changes)
- [ ] Documentation only
- [ ] Refactor (no behaviour change)

## Checklist

- [ ] `pytest` passes
- [ ] `ruff check src tests` passes
- [ ] New behaviour has a test that fails without it
- [ ] README updated if a CLI command or design decision changed
- [ ] `CHANGELOG.md` has an entry under Unreleased

## Testing notes

<!-- How did you verify this? Which APK? Which fixtures? -->

## Honesty check

If this adds an analyser, a finding type, or anything that influences output:

- [ ] Every finding carries evidence or a confidence level
- [ ] False positives were considered, and there is a test for the obvious one
- [ ] The F-Droid risk score did not move by more than a few points
      (`pytest tests/test_apksmith.py -k sane`)

## Checklist for confidence claims

- [ ] I have not described anything as "recovered" or "original" — static
      analysis cannot recover original source
- [ ] If this touches generation, the output still compiles with no API key
- [ ] If this touches evaluation, the reference is human-written, not
      model-derived