from unittest.mock import patch

import pytest
from sqlalchemy import URL

from app.core.config import resolve_database_url

DB_ENV = {
    "POSTGRES_USER": "myuser",
    "POSTGRES_PASSWORD": "mypass",
    "POSTGRES_HOST": "myhost",
    "DB_PORT": "5433",
    "POSTGRES_DB": "mydb",
}


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    for name in ("DATABASE_URL", *DB_ENV):
        monkeypatch.delenv(name, raising=False)
    with patch("app.core.config.load_dotenv") as load_dotenv:
        yield load_dotenv


def test_explicit_url_takes_precedence_over_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://env@localhost/envdb")
    assert resolve_database_url("postgresql+psycopg://arg@localhost/argdb") == "postgresql+psycopg://arg@localhost/argdb"


def test_database_url_from_environment_is_used_when_no_argument_is_given(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://env@localhost/envdb")
    assert resolve_database_url() == "postgresql+psycopg://env@localhost/envdb"


def test_url_is_built_from_postgres_variables_without_database_url(monkeypatch):
    for name, value in DB_ENV.items():
        monkeypatch.setenv(name, value)
    expected = URL.create(
        "postgresql+psycopg",
        username="myuser",
        password="mypass",
        host="myhost",
        port=5433,
        database="mydb",
    ).render_as_string(hide_password=False)
    assert resolve_database_url() == expected


def test_missing_postgres_variable_raises_key_error(monkeypatch):
    for name, value in DB_ENV.items():
        if name != "POSTGRES_HOST":
            monkeypatch.setenv(name, value)
    with pytest.raises(KeyError, match="POSTGRES_HOST"):
        resolve_database_url()


def test_dotenv_is_loaded_without_overriding_existing_variables(isolated_env):
    resolve_database_url("postgresql+psycopg://arg@localhost/argdb")
    path = isolated_env.call_args.args[0]
    assert path.name == ".env"
    assert isolated_env.call_args.kwargs == {"override": False}
