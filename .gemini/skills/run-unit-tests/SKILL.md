---
name: run-unit-tests
description: Run backend or frontend unit tests in the isolated test runner and read the results. Use after writing or changing any test file.
---

# Run unit tests

Use the `run_tests` tool. It calls `scripts/agent/run-tests.sh`, which runs
the suite without network access and without secrets.

| Suite | Path format (relative to the suite directory) |
|---|---|
| `backend` | `tests/features/todos/test_router.py` |
| `frontend` | `src/lib/http.test.ts` |

- Pass only the files you touched. Empty `paths` runs the whole suite.
- Path segments may contain only letters, digits, `_` and `-`; other paths
  are rejected.
- Tests that need network, a database or secrets fail by design.

## Reading results

- The output ends with `RESULT: passed` or `RESULT: failed (exit N)`.
- On failure read the first assertion message. Decide what is wrong:
  - the test (wrong import path, wrong mock, wrong selector, wrong async
    handling) → fix the test;
  - the source behaviour → follow the agent rule for findings.
- Typical fixes:
  - `Cannot find module` → check the relative import depth.
  - `Unable to find role` → the design system is mocked; query the native
    element the mock renders.
  - `act(...)` warnings or stale values → wrap updates in `act` or use
    `await waitFor(...)`.
  - pytest `fixture not found` → the fixture lives in `tests/conftest.py`
    under a different name.
