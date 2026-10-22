---
name: backend-unit-tests
description: Conventions for writing pytest unit tests for the Taskly FastAPI backend (backend/app). Use before creating or editing any file in backend/tests.
---

# Backend unit tests (pytest)

## Layout

- Source `backend/app/<path>/<module>.py` → test
  `backend/tests/<path>/test_<module>.py`.
- Every test package directory has an empty `__init__.py`. Create it when you
  add a new directory.
- Imports use the `app` package: `from app.features.todos.router import router`.

## Shared fixtures (`backend/tests/conftest.py`)

| Fixture | Provides |
|---|---|
| `repository_mock` | `create_autospec(TodoRepository, instance=True)`; `list` returns `[]` |
| `client` | `TestClient` for a bare `FastAPI()` with only the todos router and `get_repository` overridden by `repository_mock` |
| `todo_values` | dict with all `Todo` fields |
| `todo` | `Todo` built from `todo_values` |
| `model_factory` | `lambda values: TodoRecord(**values)` |

Reuse them. Add a new fixture to `conftest.py` only when two or more test
modules need it; otherwise keep it local to the test module.

## Patterns

- **Router:** use `client` and `repository_mock`. Assert status code, JSON
  body and the exact repository call (`assert_called_once_with(...)`). For
  invalid input assert `422` and `assert_not_called()`.
- **Repository:** use `Mock(spec=Session)`; assert the calls on the session
  (`add`, `commit`, `refresh`, `delete`) and the mapped result. Never connect
  to a real database.
- **Dependencies / lifespan / factory:** build a minimal `FastAPI()` or
  `SimpleNamespace` app state; patch collaborators with
  `unittest.mock.patch` at the import location used by the module under test
  (for example `app.core.lifespan.create_database_engine`).
- **Config:** use the `monkeypatch` fixture for environment variables and
  patch `load_dotenv` so a local `.env` file cannot change the result.
- **Endpoints that use the session directly** (for example health): the
  autospec mock has no `session`; set `repository_mock.session = Mock()`,
  assert the executed statement, and test the failure path with
  `side_effect` plus `TestClient(app, raise_server_exceptions=False)` → 500.
- Use `pytest.mark.parametrize` for input tables.
- Use `pytest.raises(..., match=...)` for errors.

## Style

- Test names describe behaviour: `test_update_returns_404_for_missing_task`.
- One behaviour per test. Arrange, act, assert without comments.
- No docstrings on test functions; the name is the description.
- No `time.sleep`, no network, no real `.env` dependency.
