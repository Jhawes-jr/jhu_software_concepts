"""Pylint-friendly tests validating pull/update button flows."""

from __future__ import annotations

from typing import Any

import pytest

from tests._app_import import import_app_module

APP_MODULE = import_app_module("app")
SCRAPER_CMD = getattr(APP_MODULE, "SCRAPER_CMD")
LOADER_CMD = getattr(APP_MODULE, "LOADER_CMD")

JSON_HEADERS = {"Accept": "application/json"}


class FakeProcess:
    """Minimal stand-in for subprocess.Popen used in pull-data tests."""

    _pid_counter = 1000

    def __init__(
        self,
        cmd: list[str],
        *,
        outputs: dict[tuple[str, ...], tuple[str, str]],
        calls: list[list[str]],
        **_: Any,
    ) -> None:
        self._cmd = tuple(cmd)
        self.returncode = 0
        self._outputs = outputs
        self._calls = calls
        self._calls.append(cmd)
        FakeProcess._pid_counter += 1
        self.pid = FakeProcess._pid_counter

    def __enter__(self) -> "FakeProcess":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def communicate(self) -> tuple[str, str]:
        """Return canned stdout/stderr output for the fake process."""
        return self._outputs[self._cmd]


@pytest.mark.buttons
def test_pull_data_triggers_scrape_and_load(client, monkeypatch, tmp_path):
    """Successful POST /pull-data should run scraper then loader and return details."""
    monkeypatch.setattr(APP_MODULE, "is_running", lambda: False)

    calls: list[list[str]] = []
    outputs = {
        tuple(SCRAPER_CMD): ("appended 5 records", ""),
        tuple(LOADER_CMD): ("Inserted rows: 4", ""),
    }

    def factory(cmd: list[str], **kwargs: Any) -> FakeProcess:
        return FakeProcess(cmd, outputs=outputs, calls=calls, **kwargs)

    monkeypatch.setattr("app.subprocess.Popen", factory)
    monkeypatch.setattr(APP_MODULE, "set_lock", lambda pid: None)

    pull_ok_file = tmp_path / "last_pull_success.txt"
    monkeypatch.setattr(APP_MODULE, "PULL_OK_FILE", pull_ok_file)

    response = client.post("/pull-data", headers=JSON_HEADERS)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {"status": "ok", "scraped": 5, "inserted": 4}

    assert calls == [SCRAPER_CMD, LOADER_CMD]
    assert pull_ok_file.exists()


@pytest.mark.buttons
def test_update_analysis_returns_200_when_allowed(client, monkeypatch, tmp_path):
    """POST /update-analysis should succeed when not busy and update is needed."""
    monkeypatch.setattr(APP_MODULE, "is_running", lambda: False)
    monkeypatch.setattr(APP_MODULE, "compute_gate_state", lambda: (1234, 1200, True))

    analysis_file = tmp_path / "analysis.txt"
    monkeypatch.setattr(APP_MODULE, "ANALYSIS_FILE", analysis_file)

    response = client.post("/update-analysis", headers=JSON_HEADERS)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {"status": "ok", "updated": True}
    assert analysis_file.exists()


@pytest.mark.buttons
def test_busy_state_blocks_mutating_posts(client, monkeypatch):
    """When busy, both pull and update endpoints should respond with 409."""
    monkeypatch.setattr(APP_MODULE, "is_running", lambda: True)

    pull_response = client.post("/pull-data", headers=JSON_HEADERS)
    assert pull_response.status_code == 409
    assert pull_response.get_json()["status"] == "busy"

    update_response = client.post("/update-analysis", headers=JSON_HEADERS)
    assert update_response.status_code == 409
    assert update_response.get_json()["status"] == "busy"


@pytest.mark.buttons
def test_update_analysis_returns_409_when_no_update_needed(client, monkeypatch):
    """If no new data is available, update endpoint should return 409."""
    monkeypatch.setattr(APP_MODULE, "is_running", lambda: False)
    monkeypatch.setattr(APP_MODULE, "compute_gate_state", lambda: (None, None, False))

    response = client.post("/update-analysis", headers=JSON_HEADERS)

    assert response.status_code == 409
    assert response.get_json() == {"status": "noop", "reason": "no-new-data"}
