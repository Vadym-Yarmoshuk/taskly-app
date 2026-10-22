from datetime import date
from unittest.mock import Mock

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.features.todos.models import TodoRecord
from app.features.todos.repository import TodoRepository
from app.features.todos.schemas import TodoStats


def test_list_maps_models_and_orders_tasks_newest_first(model_factory, todo_values, todo):
    session = Mock(spec=Session)
    session.scalars.return_value = [model_factory(todo_values)]
    assert TodoRepository(session).list() == [todo]
    statement = session.scalars.call_args.args[0]
    expected = select(TodoRecord).order_by(TodoRecord.created_at.desc(), TodoRecord.id.desc())
    assert statement.compare(expected)
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "ORDER BY todos.created_at DESC, todos.id DESC" in compiled


def test_stats_derives_active_count_and_filters_overdue_active_tasks():
    session = Mock(spec=Session)
    session.execute.return_value.one.return_value = (10, 4, 2)
    today = date(2026, 10, 20)

    stats = TodoRepository(session).stats(today)

    assert stats == TodoStats(total=10, active=6, completed=4, overdue=2)
    statement = session.execute.call_args.args[0]
    overdue = ~TodoRecord.completed & (TodoRecord.due_date < today)
    expected = select(
        func.count(TodoRecord.id),
        func.count(TodoRecord.id).filter(TodoRecord.completed),
        func.count(TodoRecord.id).filter(overdue),
    )
    assert statement.compare(expected)
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "FILTER (WHERE todos.completed)" in compiled
    assert "FILTER (WHERE NOT todos.completed AND todos.due_date <" in compiled


def test_get_returns_none_for_missing_task():
    session = Mock(spec=Session)
    session.get.return_value = None
    assert TodoRepository(session).get(404) is None
    session.get.assert_called_once_with(TodoRecord, 404)
