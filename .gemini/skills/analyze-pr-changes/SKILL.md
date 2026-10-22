---
name: analyze-pr-changes
description: Decide which changed source files in a pull request need new or updated unit tests. Use at the start of every test-generation run.
---

# Analyze pull request changes

The change context in the first message lists each changed source file with
its status, diff, category, expected test path and current content. Use it to
choose one action per file.

## Decision rules

| Situation | Action |
|---|---|
| New logic (function, branch, hook, endpoint, component state) and no test file | `create` |
| Changed logic and the test file exists | `update` — add or adjust cases for the changed behaviour only |
| Existing tests already cover every changed branch | `skip` — reason: "covered by <test name>" |
| Only formatting, comments, renames without behaviour change | `skip` |
| Declarative code (`schemas.py`, `models.py`, `types.ts`, styles, stories, barrels) | `skip`, unless it adds validation logic; then test it through the closest public API (router or validator tests) |
| Deleted source file | `skip`; mention stale tests in `findings` |

## What to look for in a diff

- New or changed conditions, early returns, error paths and default values.
- Changed function signatures: callers' tests may need updates.
- Changed user-visible text, labels or ARIA names: component tests that
  query by them must change.
- Changed API contract (paths, status codes, payload fields): update both the
  backend router tests and the frontend API tests.

## Output

Keep a short list of `{source, action, test_file, reason}`. It becomes the
`decisions` list of the `finish` report.
