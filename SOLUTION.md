# Solution: unit test agent for pull requests

A custom agent with reusable skills creates or updates unit tests for code
changed in a pull request, runs them, and publishes verified tests and a report
in the pull request. It covers the FastAPI backend and the React frontend.

## Overview

```
pull_request ─► prepare ──► generate ─────────► verify ─────────► publish
                (diff →     (agent + skills;    (apply patch,      (commit tests to PR branch,
                 context)    tests in sandbox)   run all suites)    trigger CI, PR comment)
                no secrets   GEMINI_API_KEY      no secrets         contents/pull-requests write
                read-only    read-only token     read-only          runs no PR code
```

| Part | Location |
|---|---|
| Agent definition | [.gemini/agents/unit-test-agent.md](.gemini/agents/unit-test-agent.md) |
| Skills | [.gemini/skills/](.gemini/skills/) — `analyze-pr-changes`, `backend-unit-tests`, `frontend-unit-tests`, `run-unit-tests`, `test-report` |
| Agent runtime | [scripts/agent/agent_runner.py](scripts/agent/agent_runner.py) |
| Change analysis | [scripts/agent/collect_changes.py](scripts/agent/collect_changes.py) |
| Sandboxed test runner | [scripts/agent/run-tests.sh](scripts/agent/run-tests.sh) |
| Guard (test files only) | [scripts/agent/guard_changes.py](scripts/agent/guard_changes.py) |
| Verification and report | [scripts/agent/verify_tests.py](scripts/agent/verify_tests.py), [scripts/agent/render_report.py](scripts/agent/render_report.py) |
| PR workflow | [.github/workflows/unit-test-agent.yml](.github/workflows/unit-test-agent.yml) |
| CI | [.github/workflows/ci.yml](.github/workflows/ci.yml) |

## Main technical decisions

**Model: Gemini API, free tier.** No paid key was available. The free tier
allows about 20 requests per model per day and is often overloaded (HTTP 503).
Every other decision follows from this budget.

**Own lightweight runtime instead of Gemini CLI.** Gemini CLI was tested first
(local headless run). It made hidden extra requests (model routing used a
different model than requested) and needed extra requests for each subagent
and skill activation. Its workspace policy files are disabled in current
versions. A ~420-line runtime with the Python standard library gives:

- a hard request budget per run (`max_requests` in the agent definition) and a
  forced `finish` call on the last request, so a report always exists;
- model fallback that reads `QuotaFailure` and `RetryInfo` from API errors:
  wait for a short rate limit, switch model on a daily quota or repeated 503;
- tools that enforce access rules in code, not in prompts or regex policies;
- the change context, sources, existing tests, shared fixtures and a nearby
  example test in the first message, so the agent rarely spends requests on
  reading files. Typical run: 7 requests.

The agent definition and skills use the standard Markdown + front matter and
`SKILL.md` formats in `.gemini/`, so Gemini CLI can also use them locally.

**Deterministic work outside the model.** Finding changed files, mapping them
to test paths, formatting, accepting changes, running the final verification,
committing and rendering the comment are scripts. The model only decides what
to test and writes the tests.

**Skills hold repository knowledge.** Each skill is loaded on demand with
`activate_skill`: fixtures and mocking conventions of this repository, React
Query hook patterns (verified to work with the installed version), how to read
runner output, and the report contract.

**Bot commit to the PR branch.** Verified tests are committed with
`GITHUB_TOKEN`. Such pushes do not trigger workflows, which prevents loops;
the publish job then starts CI explicitly with `workflow_dispatch`.

## Security

| Risk | Control |
|---|---|
| Secret exfiltration by PR code | Only `generate` has `GEMINI_API_KEY`. Tests started by the agent run in `docker --network none` with no environment variables. `verify` runs all tests again without any secret. |
| Malicious PR changes the agent itself | Agent definition, skills and scripts are taken from the **base** commit (`git archive $BASE_SHA`) into `$RUNNER_TEMP`, outside the workspace that test containers can write. |
| Agent edits production code or CI | Tools allow writes only to `backend/tests/**/test_*.py`, `conftest.py`, `__init__.py` and `frontend/src/**/*.test.ts(x)`; path traversal is rejected. The guard re-checks every changed file and reverts the rest. |
| Agent weakens tests | Guard rejects added `skip`, `only`, `todo`, `xfail`; agent rules forbid removing assertions. |
| Prompt injection in PR content | Context is labelled untrusted; the agent has no network, shell, secret or git tools; all effects pass the guard and the verification. |
| Script injection in workflow | Branch names and other event data reach shell only through environment variables. |
| Fork PRs | Agent job is skipped (no secrets); `pull_request` is used, never `pull_request_target`. |
| Unsafe output in PR comment | Agent text is escaped (HTML, table pipes, `@` mentions) and length-limited. |
| Supply chain | Actions pinned to commit SHAs; least-privilege `permissions` per job. |

## How to run

Prerequisites:

1. Repository secret `GEMINI_API_KEY` (Settings → Secrets and variables →
   Actions), from Google AI Studio.
2. Optional repository variable `AGENT_MODELS` to override the model list.
3. The workflow files must be on the default branch (the agent configuration is
   read from the PR base commit).

The workflow runs automatically for non-draft pull requests that change
`backend/app/**` or `frontend/src/**`.

Local run:

```sh
python scripts/agent/collect_changes.py --base origin/main   # or --untested
GEMINI_API_KEY=... python scripts/agent/agent_runner.py
python scripts/agent/guard_changes.py        # report only; --revert deletes rejected changes
python -m pytest scripts/agent/tests         # tests for the agent scripts
```

## Example run: pull request #1

[PR #1 — feat: show task statistics](https://github.com/Vadym-Yarmoshuk/taskly-app/pull/1)
adds `GET /api/todos/stats`, a `useTodoStats` hook, a `TodoStatsSummary`
component, and makes the three mutation hooks refresh the statistics. It
contains no test changes, and it breaks one existing test
(`TodosPage.test.tsx` does not mock the new hook).

[Workflow run](https://github.com/Vadym-Yarmoshuk/taskly-app/actions/runs/39840471965):
all four jobs succeeded; model `gemini-3-flash-preview`.

**Agent decisions** (from the PR comment):

| Source | Action | Test file |
|---|---|---|
| `backend/.../repository.py` | update | `test_repository.py` — new `stats` test, SQL statement compared |
| `backend/.../router.py` | update | `test_router.py` — `/stats` returns repository result for `date.today()` |
| `backend/.../schemas.py`, `queryKeys.ts`, `types.ts` | skip | declarative code |
| `frontend/.../TodosPage.tsx` | update | `TodosPage.test.tsx` — mocks the new hook; fixes the failing test |
| `frontend/.../api/todos.ts` | update | `todos.test.ts` — new `stats` call |
| `TodoStatsSummary.tsx` | create | 4 cases: no data, empty, without and with overdue |
| `useTodoStats.ts` | create | data and abort signal |
| `useCreate/Update/DeleteTodoMutation.ts` | update | assert `invalidateQueries({ queryKey: todoKeys.stats })` |

**Skills used:** `analyze-pr-changes`, `backend-unit-tests`,
`frontend-unit-tests`, `run-unit-tests`, `test-report`.

**Verification (clean job, no secrets):**

| Suite | Before agent | After agent |
|---|---|---|
| backend | passed, 67.2% lines | passed, 70.1% |
| frontend | **failed** (broken `TodosPage` test) | passed, 70.2% |

The bot committed 9 test files (`c598830`) and started CI for that commit; CI
passed.

**Human review** found one problem: the agent removed an existing assertion in
`test_repository.py` (the SQL `ORDER BY` text check). It was restored in
`d073626`. The guard now rejects any change that removes an existing
assertion (`e20918a`); replaying the bot diff through the new rule flags
exactly that line.

**Update run.** The review push (`d073626`) started the workflow again
([run](https://github.com/Vadym-Yarmoshuk/taskly-app/actions/runs/39841705600)).
The agent re-analyzed the PR, found nothing to change, and the same PR comment
was updated: "No test changes were needed or accepted", coverage unchanged,
no commit. The bot's own commit did not start an agent run.

## Coverage of the existing code

The same agent and skills were run locally in "untested" mode
(`collect_changes.py --untested`) on files without tests. Every generated test
was reviewed before commit; review changes are listed in the commit messages.

| Suite | Before | After |
|---|---|---|
| backend (lines) | 42% | 68% |
| frontend (lines) | 47.7% | 68.2% |

Examples of review fixes: a config test loaded the real `.env` into the test
process (now patched); the lifespan failure path (`dispose()` after a failed
`initialize()`) was missing; cache tests did not prove that other tasks stay
unchanged.

## Assumptions

- Pull requests that need the agent come from branches of this repository;
  fork PRs get CI only.
- Unit tests only: no database or browser; repository tests compare SQLAlchemy
  statements instead of executing them.
- The PR author reviews the bot commit like any other commit. The agent is an
  assistant, not a merge gate.
- Declarative files (schemas, models, types, styles, stories, design system)
  do not need their own tests, in line with the existing coverage exclusions.

## Limitations

- **Free model quota.** About 20 requests per model per day, frequent 503
  responses. A run needs ~7 requests; the fallback chain covers a few runs per
  day. When all models are exhausted the run ends with `quota_exhausted`, posts
  a comment and changes nothing.
- **Whole-PR analysis on every push.** Each run analyzes the full PR diff, so a
  later push spends requests even when earlier runs already covered the
  change. The model's free-text summary can also repeat earlier work; the
  comment headline and the commit are derived from the guard and the
  verification, not from the model's text.
- **Model quality.** Fallback to "lite" models gives weaker tests. Human review
  remains necessary; the guard blocks only mechanical weakening (skips, removed
  assertions), not shallow tests.
- **Coverage gap.** `AppProviders.tsx`, `TodoEmptyState.tsx` and
  `useTodoFilters.ts` still have no tests; the quota was spent on the demo PR.
- **Bot commits** with `GITHUB_TOKEN` need `workflow_dispatch` to get CI;
  GitHub may also list `pull_request` runs for the bot commit as "approval
  required". They are skipped by the workflow if approved.
- `pull_request` workflows run the workflow file from the PR, so a
  collaborator with write access can still change the workflow itself. The
  agent configuration and scripts are taken from the base commit.

## Production version

- Paid model tier or self-hosted model, with a budget per PR and alerts.
- A GitHub App with a dedicated identity instead of `GITHUB_TOKEN`: CI runs
  normally on bot commits, and permissions are scoped to the repository.
- Required reviewers (environment protection) for the job that holds the API
  key; workflow changes require CODEOWNERS approval.
- Mutation testing (for example `mutmut`, Stryker) on changed lines to measure
  whether generated tests catch real faults, and diff coverage as a gate.
- Containers built from pinned image digests with dependencies pre-installed,
  and a read-only source mount for test runs.
- Incremental analysis: diff only the commits since the last agent run, and
  skip the model when no source file changed since then.
- Structured run telemetry (requests, tokens, decisions, review outcome) to
  tune skills and prompts over time.
