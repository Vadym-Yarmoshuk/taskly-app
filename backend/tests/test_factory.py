from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.dependencies import get_repository
from app.factory import create_app


def test_create_app_resolves_database_url_and_sets_metadata():
    with patch("app.factory.resolve_database_url", return_value="postgresql+psycopg://resolved/db") as resolve:
        app = create_app("postgresql+psycopg://custom/db")
    resolve.assert_called_once_with("postgresql+psycopg://custom/db")
    assert app.state.database_url == "postgresql+psycopg://resolved/db"
    assert (app.title, app.version) == ("Taskly API", "1.0.0")


def test_create_app_registers_health_and_todo_routes():
    with patch("app.factory.resolve_database_url", return_value="postgresql+psycopg://resolved/db"):
        app = create_app()
    assert {"/api/health", "/api/todos", "/api/todos/{todo_id}"} <= set(app.openapi()["paths"])


def test_create_app_runs_the_application_lifespan_on_startup():
    started = []

    @asynccontextmanager
    async def fake_lifespan(app):
        started.append(app)
        yield

    with patch("app.factory.resolve_database_url", return_value="postgresql+psycopg://resolved/db"),          patch("app.factory.lifespan", fake_lifespan):
        app = create_app()
    with TestClient(app):
        assert started == [app]


def test_created_app_serves_health_endpoint_through_repository_dependency():
    with patch("app.factory.resolve_database_url", return_value="postgresql+psycopg://resolved/db"):
        app = create_app()
    repository = MagicMock()
    app.dependency_overrides[get_repository] = lambda: repository
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    repository.session.execute.assert_called_once()
