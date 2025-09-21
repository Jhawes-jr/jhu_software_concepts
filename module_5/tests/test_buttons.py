from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest

import app

JSON_HEADERS = {"Accept": "application/json"}


class FakeProcess:
    """Minimal stand-in for subprocess.Popen used in pull-data tests."""

    _pid_counter = 1000

    def __init__(self, cmd: list[str], *, outputs: dict[tuple[str, ...], tuple[str, str]], calls: list[list[str]], **_: Any) -> None:
        self._cmd = tuple(cmd)
        self.returncode = 0
        self._outputs = outputs
        self._calls = calls
        self._calls.append(cmd)
        FakeProcess._pid_counter += 1
        self.pid = FakeProcess._pid_counter

    def communicate(self) -> tuple[str, str]:
        return self._outputs[self._cmd]


@pytest.mark.buttons
def test_pull_data_triggers_scrape_and_load(client, monkeypatch, tmp_path):
    """Successful POST /pull-data should run scraper then loader and return details."""
    monkeypatch.setattr(app, "is_running", lambda: False)

    calls: list[list[str]] = []
    outputs = {
        tuple(app.SCRAPER_CMD): ("appended 5 records", ""),
        tuple(app.LOADER_CMD): ("Inserted rows: 4", ""),
    }

    def factory(cmd: list[str], **kwargs: Any) -> FakeProcess:
        return FakeProcess(cmd, outputs=outputs, calls=calls, **kwargs)

    monkeypatch.setattr(app.subprocess, "Popen", factory)
    monkeypatch.setattr(app, "set_lock", lambda pid: None)

    pull_ok_file = tmp_path / "last_pull_success.txt"
    monkeypatch.setattr(app, "PULL_OK_FILE", str(pull_ok_file))

    response = client.post("/pull-data", headers=JSON_HEADERS)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {"status": "ok", "scraped": 5, "inserted": 4}

    assert calls == [app.SCRAPER_CMD, app.LOADER_CMD]
    assert pull_ok_file.exists()


@pytest.mark.buttons
def test_update_analysis_returns_200_when_allowed(client, monkeypatch, tmp_path):
    """POST /update-analysis should succeed when not busy and update is needed."""
    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "compute_gate_state", lambda: (1234, 1200, True))

    analysis_file = tmp_path / "analysis.txt"
    monkeypatch.setattr(app, "ANALYSIS_FILE", str(analysis_file))

    response = client.post("/update-analysis", headers=JSON_HEADERS)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {"status": "ok", "updated": True}
    assert analysis_file.exists()


@pytest.mark.buttons
def test_busy_state_blocks_mutating_posts(client, monkeypatch):
    """When busy, both pull and update endpoints should respond with 409."""
    monkeypatch.setattr(app, "is_running", lambda: True)

    pull_response = client.post("/pull-data", headers=JSON_HEADERS)
    assert pull_response.status_code == 409
    assert pull_response.get_json()["status"] == "busy"

    update_response = client.post("/update-analysis", headers=JSON_HEADERS)
    assert update_response.status_code == 409
    assert update_response.get_json()["status"] == "busy"


@pytest.mark.buttons
def test_update_analysis_returns_409_when_no_update_needed(client, monkeypatch):
    """If no new data is available, update endpoint should return 409."""
    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "compute_gate_state", lambda: (None, None, False))

    response = client.post("/update-analysis", headers=JSON_HEADERS)

    assert response.status_code == 409
    assert response.get_json() == {"status": "noop", "reason": "no-new-data"}
