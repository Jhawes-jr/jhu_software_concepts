"""Fixtures for pytest to set up the testing environment."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _load_module(name: str) -> Any:
    """Import a first-party module after ensuring ``src`` is on the path."""

    return importlib.import_module(name)


@pytest.fixture(scope="session", autouse=True)
def ensure_database_schema():
    """Ensure the Postgres schema exists before any tests run."""

    create_schema = _load_module("create_schema")
    db = _load_module("db")
    with db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(create_schema.DDL)


@pytest.fixture(scope="module")
def test_app() -> Flask:
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


@pytest.fixture()
def client(test_app: Flask):  # pylint: disable=redefined-outer-name
    """Provide a test client for issuing requests."""

    return test_app.test_client()
