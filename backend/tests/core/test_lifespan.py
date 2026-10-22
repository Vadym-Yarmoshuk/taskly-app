import asyncio
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI

from app.core.lifespan import lifespan

DATABASE_URL = "postgresql+psycopg://user:pass@localhost:5432/db"


@pytest.fixture
def app():
    app = FastAPI()
    app.state.database_url = DATABASE_URL
    return app


def test_lifespan_initializes_database_and_disposes_engine_on_shutdown(app):
    engine, session_factory = Mock(), Mock()
    with patch("app.core.lifespan.create_database_engine", return_value=engine) as create_engine, \
         patch("app.core.lifespan.initialize") as initialize, \
         patch("app.core.lifespan.create_session_factory", return_value=session_factory) as create_factory:

        async def run():
            async with lifespan(app):
                create_engine.assert_called_once_with(DATABASE_URL)
                initialize.assert_called_once_with(engine)
                create_factory.assert_called_once_with(engine)
                assert app.state.session_factory is session_factory
                engine.dispose.assert_not_called()

        asyncio.run(run())
    engine.dispose.assert_called_once_with()


def test_lifespan_disposes_engine_when_initialization_fails(app):
    engine = Mock()
    with patch("app.core.lifespan.create_database_engine", return_value=engine), \
         patch("app.core.lifespan.initialize", side_effect=RuntimeError("Database unavailable")), \
         patch("app.core.lifespan.create_session_factory") as create_factory:

        async def run():
            async with lifespan(app):
                pass

        with pytest.raises(RuntimeError, match="Database unavailable"):
            asyncio.run(run())
    create_factory.assert_not_called()
    engine.dispose.assert_called_once_with()
