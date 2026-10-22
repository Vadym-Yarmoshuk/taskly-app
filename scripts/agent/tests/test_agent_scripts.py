import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent_runner  # noqa: E402
import collect_changes  # noqa: E402
import guard_changes  # noqa: E402
import render_report  # noqa: E402


@pytest.fixture
def tools():
    return agent_runner.Tools({"demo": {"description": "d", "body": "steps"}}, ["activate_skill", "read_file", "write_file", "list_files"])


@pytest.mark.parametrize("path", [
    "backend/tests/test_factory.py",
    "backend/tests/api/test_health.py",
    "backend/tests/conftest.py",
    "frontend/src/lib/http.test.ts",
    "frontend/src/features/todos/hooks/useTodosBusy.test.tsx",
])
def test_guard_allows_unit_test_files(path):
    assert any(pattern.match(path) for pattern in guard_changes.ALLOWED)


@pytest.mark.parametrize("path", [
    "backend/app/main.py",
    "frontend/src/lib/http.ts",
    ".github/workflows/ci.yml",
    "frontend/package.json",
    "backend/tests/../app/main.py",
    "scripts/agent/guard_changes.py",
])
def test_guard_rejects_non_test_files(path):
    assert guard_changes.review(" M", path) == "not a unit test file"


@pytest.mark.parametrize("code", [
    "it.skip('x', () => {})",
    "it.only('x', () => {})",
    "describe.skip('x', () => {})",
    "xit('x', () => {})",
    "@pytest.mark.skip(reason='x')",
    "@pytest.mark.xfail",
    "pytest.skip('x')",
])
def test_guard_detects_disabled_or_focused_tests(code):
    assert guard_changes.FORBIDDEN_CODE.search(code)


def test_guard_accepts_regular_test_code():
    assert not guard_changes.FORBIDDEN_CODE.search("it('skips nothing', () => expect(skip).toBe(1))")


@pytest.mark.parametrize("path", ["../outside.txt", "/../../etc/passwd", "frontend/../../x"])
def test_repo_path_rejects_paths_outside_the_repository(path):
    with pytest.raises(agent_runner.ToolError, match="outside the repository"):
        agent_runner.repo_path(path)


@pytest.mark.parametrize("path", [".env", "backend/.venv/pyvenv.cfg", ".git/config", ".env.local"])
def test_read_file_rejects_secret_and_internal_files(tools, path):
    with pytest.raises(agent_runner.ToolError, match="not readable"):
        tools.call("read_file", {"path": path})


@pytest.mark.parametrize("path", ["backend/app/main.py", "frontend/src/lib/http.ts", "frontend/src/../../evil.test.ts"])
def test_write_file_rejects_non_test_paths(tools, path):
    with pytest.raises(agent_runner.ToolError, match="Only unit test files"):
        tools.call("write_file", {"path": path, "content": "x"})


def test_tool_outside_the_agent_definition_is_rejected(tools):
    with pytest.raises(agent_runner.ToolError, match="Tool not allowed"):
        tools.call("run_tests", {"suite": "backend"})


def test_activate_skill_returns_skill_body(tools):
    assert tools.call("activate_skill", {"name": "demo"}) == {"skill": "demo", "instructions": "steps"}


def test_declarations_expose_only_allowed_tools(tools):
    assert {d["name"] for d in tools.declarations()} == {"activate_skill", "read_file", "write_file", "list_files"}


@pytest.mark.parametrize(("suite", "path", "expected"), [
    ("frontend", "frontend/src/lib/http.test.ts", "src/lib/http.test.ts"),
    ("frontend", "lib/http.test.ts", "src/lib/http.test.ts"),
    ("frontend", "src/lib/http.test.ts", "src/lib/http.test.ts"),
    ("backend", "backend/tests/api/test_health.py", "tests/api/test_health.py"),
    ("backend", "api/test_health.py", "tests/api/test_health.py"),
])
def test_normalize_test_path(suite, path, expected):
    assert agent_runner.normalize_test_path(suite, path) == expected


def test_sandbox_env_removes_credentials(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    monkeypatch.setenv("GH_TOKEN", "secret")
    monkeypatch.setenv("SAFE_VALUE", "kept")
    env = agent_runner.sandbox_env()
    assert "GEMINI_API_KEY" not in env and "GH_TOKEN" not in env
    assert env["SAFE_VALUE"] == "kept"


def test_quota_info_detects_daily_quota_and_delay():
    error = {"error": {"details": [
        {"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
        {"retryDelay": "43470s"},
    ]}}
    assert agent_runner.quota_info(error) == (True, 43471)


def test_quota_info_returns_short_delay_for_rate_limits():
    error = {"error": {"details": [{"retryDelay": "37.2s"}]}}
    assert agent_runner.quota_info(error) == (False, 38)


def test_parse_front_matter_reads_scalars_and_lists():
    meta, body = agent_runner.parse_front_matter("---\nname: a\ntools:\n  - x\n  - y\n---\nBody\n")
    assert meta == {"name": "a", "tools": ["x", "y"]}
    assert body == "Body"


@pytest.mark.parametrize(("path", "expected"), [
    ("backend/app/api/health.py", "backend/tests/api/test_health.py"),
    ("backend/app/factory.py", "backend/tests/test_factory.py"),
    ("frontend/src/lib/http.ts", "frontend/src/lib/http.test.ts"),
    ("frontend/src/App.tsx", "frontend/src/App.test.tsx"),
])
def test_expected_test_path(path, expected):
    assert collect_changes.expected_test_path(path) == expected


@pytest.mark.parametrize(("path", "category"), [
    ("backend/app/factory.py", "source"),
    ("backend/app/features/todos/schemas.py", "declarative"),
    ("frontend/src/design-system/components/Button/Button.tsx", "declarative"),
    ("frontend/src/features/todos/types.ts", "declarative"),
    ("frontend/src/lib/http.test.ts", "test"),
    ("README.md", None),
])
def test_classify(path, category):
    assert collect_changes.classify(path) == category


def test_clean_neutralises_markdown_html_and_mentions():
    text = render_report.clean("<img src=x> | @maintainer\nnext")
    assert "<" not in text and "\\|" in text and "@​maintainer" in text and "\n" not in text


def test_validate_reports_invalid_actions():
    report = {"summary": "s", "decisions": [{"source": "a", "action": "delete"}], "test_runs": [], "findings": []}
    assert render_report.validate(report) == ["invalid decision: {'source': 'a', 'action': 'delete'}"]


def test_validate_accepts_a_complete_report():
    report = {"summary": "s", "decisions": [{"source": "a", "action": "skip"}], "test_runs": [], "findings": []}
    assert render_report.validate(report) == []


def test_guard_detects_removed_assertions(monkeypatch):
    diff = "\n".join([
        "--- a/x",
        "+++ b/x",
        "-    assert result == 1",
        "-    expect(a).toBe(1)",
        "+    expect(a).toBe(1)",
    ])
    monkeypatch.setattr(guard_changes, "git", lambda *args: diff)
    assert guard_changes.removed_assertions(" M", "x") == ["assert result == 1"]


def test_guard_rejects_changes_that_remove_assertions(monkeypatch):
    monkeypatch.setattr(guard_changes, "added_lines", lambda status, path: "")
    monkeypatch.setattr(guard_changes, "removed_assertions", lambda status, path: ["assert compiled"])
    assert guard_changes.review(" M", "backend/tests/test_x.py") == "removes existing assertions: assert compiled"


def test_coverage_row_marks_failed_baseline():
    verify = {"before": {"frontend": {"passed": False, "coverage": None}},
              "after": {"frontend": {"passed": True, "coverage": 70.2}}}
    assert render_report.coverage_row("frontend", verify) == "| frontend | ✅ passed | ❌ failed | 70.2% |"
