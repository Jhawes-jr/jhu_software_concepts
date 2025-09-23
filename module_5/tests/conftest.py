"""Fixtures for pytest to set up the testing environment."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest
from flask import Flask
from psycopg import OperationalError

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _load_module(name: str) -> Any:
    """Import a first-party module after ensuring ``src`` is on the path."""

    return importlib.import_module(name)


class _FakeCursor:
    """Minimal cursor that records executed statements during test setup."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def __enter__(self) -> "_FakeCursor":
        """Return the cursor instance for context manager use."""

        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        """Support context manager exit signature."""

        return None

    def execute(self, sql: str) -> None:
        """Record the SQL statement that would have been executed."""

        self.statements.append(sql)


class _FakeConn:
    """Context manager that mimics the subset of psycopg connection API we need."""

    def __enter__(self) -> "_FakeConn":
        """Return the fake connection for context manager use."""

        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        """Support context manager exit signature."""

        return None

    def cursor(self) -> _FakeCursor:
        """Provide a fake cursor supporting the context manager protocol."""

        return _FakeCursor()


@pytest.fixture(scope="session", autouse=True)
def ensure_database_schema():
    """Ensure the Postgres schema exists before any tests run."""

    create_schema = _load_module("create_schema")
    db = _load_module("db")
    try:
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(create_schema.DDL)
    except (OperationalError, OSError):  # pragma: no cover - only in CI without Postgres
        # In environments without Postgres, fall back to a lightweight fake
        # connection so tests that rely on schema setup can still proceed.
        with _FakeConn() as conn, conn.cursor() as cur:
            cur.execute(create_schema.DDL)


@pytest.fixture(scope="module", name="test_app")
def fixture_test_app() -> Flask:
    """Flask application configured for testing."""

    flask_app_module = _load_module("app")
    app = flask_app_module.app  # type: ignore[attr-defined]
    original_testing = app.config.get("TESTING")
    app.config.update(TESTING=True)
    try:
        yield app
    finally:
        if original_testing is None:
            app.config.pop("TESTING", None)
        else:
            app.config["TESTING"] = original_testing


@pytest.fixture(name="client")
def client_fixture(test_app: Flask):
    """Provide a test client for issuing requests."""

    return test_app.test_client()
