from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_repository
from app.api.health import router


def test_health_check_returns_ok_and_queries_database(repository_mock):
    session = Mock()
    repository_mock.session = session

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository] = lambda: repository_mock

    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert session.execute.call_count == 1


def test_health_check_handles_database_error(repository_mock):
    session = Mock()
    session.execute.side_effect = RuntimeError("Database error")
    repository_mock.session = session

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository] = lambda: repository_mock

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/health")

    assert response.status_code == 500
