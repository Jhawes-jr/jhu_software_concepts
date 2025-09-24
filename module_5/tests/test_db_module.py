'''Test db module for database connection handling.'''

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from tests._app_import import import_app_module
from tests.sample_data import configure_pg_env

db = import_app_module("db")


@pytest.mark.db
def test_get_conn_uses_database_url(monkeypatch):
    '''If DATABASE_URL is set, get_conn should use it.'''
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")

    recorded = {}

    def fake_connect(url, row_factory):
        recorded["url"] = url
        recorded["row_factory"] = row_factory
        return "connection"

    monkeypatch.setattr(db.psycopg, "connect", fake_connect)

    conn = db.get_conn()
    assert conn == "connection"
    assert recorded["url"].startswith("postgresql://")
    assert recorded["row_factory"] == db.dict_row


@pytest.mark.db
def test_get_conn_builds_keyword_arguments(monkeypatch):
    '''If DATABASE_URL is not set, get_conn should build connection parameters'''
    configure_pg_env(monkeypatch)

    recorded = {}

    def fake_connect(**kwargs):
        recorded.update(kwargs)
        return "connection"

    monkeypatch.setattr(db.psycopg, "connect", fake_connect)

    conn = db.get_conn()
    assert conn == "connection"
    assert recorded["host"] == "db-host"
    assert str(recorded["port"]) == "6543"
    assert recorded["dbname"] == "dbname"
    assert recorded["user"] == "dbuser"
    assert recorded["password"] == "secret"
    assert recorded["row_factory"] == db.dict_row


@pytest.mark.db
def test_db_module_script_entry(monkeypatch, capsys):
    '''Running db.py as a script should attempt a DB connection and print result.'''

    class DummyCursor:
        '''A dummy cursor that can be used as a context manager.'''
        def __enter__(self) -> "DummyCursor":
            return self
        def __exit__(self, exc_type, exc, tb) -> None:
            return None
        def execute(self, sql: str) -> None:
            '''Execute a SQL statement.'''
            del sql
        def fetchone(self):
            '''Fetch one row from the result set.'''
            return {"version": "PostgreSQL"}

    class DummyConn:
        '''A dummy connection that can be used as a context manager.'''
        def __enter__(self) -> "DummyConn":
            return self
        def __exit__(self, exc_type, exc, tb) -> None:
            return None
        def cursor(self) -> DummyCursor:
            '''Return a dummy cursor.'''
            return DummyCursor()

    recorded = []

    def fake_connect(**kwargs):
        recorded.append(kwargs)
        return DummyConn()

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(db.psycopg, "connect", fake_connect)

    runpy.run_path(Path("src/db.py"), run_name="__main__")
    out = capsys.readouterr().out
    assert "DB connection OK" in out
    assert recorded
