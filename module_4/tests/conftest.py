from __future__ import annotations

import sys
from pathlib import Path

import pytest
from flask import Flask

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import app as flask_app_module


@pytest.fixture(scope="module")
def test_app() -> Flask:
    """Flask application configured for testing."""
    app = flask_app_module.app
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
def client(test_app: Flask):
    """Provide a test client for issuing requests."""
    return test_app.test_client()
