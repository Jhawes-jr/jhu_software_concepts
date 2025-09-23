"""Lint-friendly tests covering analysis page formatting behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest  # pylint: disable=import-error
import app  # pylint: disable=import-error


def _fake_stats() -> dict[str, object]:
    return {
        "q1": 123,
        "q3": {
            "avg_gpa": 3.5,
            "avg_gre_q": 160,
            "avg_gre_v": 157,
            "avg_gre_aw": 4.5,
        },
        "q4": 3.2,
        "q5": 12.3456,
        "q6": 3.8,
        "q7": 17,
        "q8": 5,
        "q9": {
            "avg_american": 3.4,
            "avg_international": 3.1,
            "diff": 0.3,
        },
        "q10": [
            SimpleNamespace(university="Test U", acceptance_rate_pct=42.6666, n=25),
        ],
    }


@pytest.fixture()
def patched_stats(monkeypatch):
    """Provide deterministic stats so tests can assert exact formatting."""
    data = _fake_stats()
    monkeypatch.setattr(app, "compute_stats", lambda: data)
    return data


@pytest.mark.analysis
@pytest.mark.usefixtures("patched_stats")
def test_analysis_page_includes_answer_labels(client):
    """The analysis page should render multiple labeled answer sections."""
    response = client.get("/analysis")
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert html.count("Answer:") >= 5


@pytest.mark.analysis
@pytest.mark.usefixtures("patched_stats")
def test_percentages_render_with_two_decimal_places(client):
    """All percentage values must render with two decimal places."""
    response = client.get("/analysis")
    html = response.get_data(as_text=True)

    assert "12.35%" in html
    assert "42.67" in html
