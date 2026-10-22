---
name: test-report
description: Submit the structured result of a test-generation run with the finish tool. Use once, as the last step of every run.
---

# Test report

Call `finish` exactly once. The workflow validates the report and publishes it
in the pull request.

```json
{
  "summary": "One or two sentences: what changed and what you did.",
  "decisions": [
    {
      "source": "frontend/src/lib/http.ts",
      "action": "create",
      "test_file": "frontend/src/lib/http.test.ts",
      "reason": "New error mapping for 422 and network failures had no tests."
    }
  ],
  "test_runs": [
    {
      "suite": "frontend",
      "command": "run-tests.sh frontend src/lib/http.test.ts",
      "passed": true,
      "notes": "5 tests passed after fixing a wrong mock in round 1."
    }
  ],
  "findings": [
    "backend/app/features/todos/router.py: PATCH returns 200 for an empty body; expected 422."
  ]
}
```

## Rules

- `action` is one of `create`, `update`, `skip`. Omit `test_file` for `skip`.
- One decision for every changed source file listed in the context.
- `test_runs` contains the final run of each suite you touched, not every
  attempt.
- `findings` lists suspected bugs in production code and tests you could not
  make pass. Use an empty list when there are none.
- Facts only. Do not claim a test passed unless the last run printed
  `RESULT: passed`.
