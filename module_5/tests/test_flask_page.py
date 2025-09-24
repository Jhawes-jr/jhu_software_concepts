'''Tests for the Flask web application page.'''

from __future__ import annotations

import pytest
from flask import Flask


@pytest.mark.web
def test_app_factory_provides_flask_instance(test_app):
    """The app factory should expose a usable Flask instance for testing."""
    assert isinstance(test_app, Flask)
    # Ensure a test client can be created without raising errors.
    client = test_app.test_client()
    assert client is not None


@pytest.mark.web
def test_app_registers_expected_routes(test_app):
    """Verify that all required routes are registered with the Flask app."""
    routes = {
        rule.rule: rule
        for rule in test_app.url_map.iter_rules()
        if rule.endpoint != "static"
    }

    expected_routes = {
        "/analysis": {"GET"},
        "/pull-data": {"POST"},
        "/update-analysis": {"POST"},
    }

    for path, methods in expected_routes.items():
        assert path in routes, f"Missing route for {path}"
        rule_methods = routes[path].methods
        # Flask implicitly adds HEAD/OPTIONS; we only require our explicit verbs.
        assert methods.issubset(rule_methods), f"Route {path} missing expected methods {methods}"


@pytest.mark.web
def test_analysis_page_loads_with_buttons(client):
    """GET /analysis should render the analysis page with required controls."""
    response = client.get("/analysis")
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert "Pull Data" in html
    assert "Update Analysis" in html
    assert "Analysis" in html
    assert "Answer:" in html
