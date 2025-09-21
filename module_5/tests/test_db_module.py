from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

import db


@pytest.mark.db
def test_get_conn_uses_database_url(monkeypatch):
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
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PGHOST", "db-host")
    monkeypatch.setenv("PGPORT", "6543")
    monkeypatch.setenv("PGDATABASE", "dbname")
    monkeypatch.setenv("PGUSER", "dbuser")
    monkeypatch.setenv("PGPASSWORD", "secret")

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
    import types

    class DummyCursor:
        def __enter__(self) -> "DummyCursor":
            return self
        def __exit__(self, exc_type, exc, tb) -> None:
            pass
        def execute(self, sql: str) -> None:
            pass
        def fetchone(self):
            return {"version": "PostgreSQL"}

    class DummyConn:
        def __enter__(self) -> "DummyConn":
            return self
        def __exit__(self, exc_type, exc, tb) -> None:
            pass
        def cursor(self) -> DummyCursor:
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

