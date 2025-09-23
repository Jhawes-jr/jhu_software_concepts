"""Pylint-friendly coverage of helper behaviors exposed by the Flask app."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path
from typing import Any
import types

import pytest
from flask.app import Flask

# pylint: disable=missing-function-docstring, missing-class-docstring, protected-access, too-few-public-methods, no-member

import app  # pylint: disable=import-error

JSON_HEADERS = {"Accept": "application/json"}


@pytest.mark.buttons
def test_datetimeformat_returns_empty_on_error():
    assert app.datetimeformat("not-a-timestamp") == ""


@pytest.mark.buttons
@pytest.mark.usefixtures("client")
def test_wants_json_response_branches():
    with app.app.test_request_context("/", json={"ping": "pong"}):
        assert app.wants_json_response() is True

    with app.app.test_request_context("/", headers={"Accept": "application/json"}):
        assert app.wants_json_response() is True

    with app.app.test_request_context("/", headers={"Accept": "text/html"}):
        assert app.wants_json_response() is False


@pytest.mark.buttons
def test_set_lock_creates_and_clears_file(monkeypatch, tmp_path):
    lock_path = tmp_path / "locks" / "scrape.lock"
    monkeypatch.setattr(app, "LOCK_FILE", lock_path)

    app.set_lock(999)
    assert lock_path.exists()

    app.set_lock(None)
    assert not lock_path.exists()

    app.set_lock(None)


@pytest.mark.buttons
def test_is_running_true_when_pid_alive(monkeypatch, tmp_path):
    lock_path = tmp_path / "lock.txt"
    monkeypatch.setattr(app, "LOCK_FILE", lock_path)

    called = {}

    def record_pid(pid: int, _sig: int) -> None:
        called["pid"] = pid

    monkeypatch.setattr(app.os, "kill", record_pid)

    app.set_lock(123)
    assert app.is_running() is True
    assert called["pid"] == 123


@pytest.mark.buttons
def test_is_running_handles_missing_or_bad_lock(monkeypatch, tmp_path):
    lock_path = tmp_path / "missing.lock"
    monkeypatch.setattr(app, "LOCK_FILE", lock_path)
    assert app.is_running() is False

    lock_path.write_text("not-a-pid", encoding="utf-8")

    def raise_process_lookup(_pid: int, _sig: int) -> None:
        raise ProcessLookupError()

    monkeypatch.setattr(app.os, "kill", raise_process_lookup)
    assert app.is_running() is False
    assert not lock_path.exists()


@pytest.mark.buttons
def test_is_running_handles_missing_lock_removal(monkeypatch, tmp_path):
    lock_path = tmp_path / "stale.lock"
    monkeypatch.setattr(app, "LOCK_FILE", lock_path)
    lock_path.write_text("invalid", encoding="utf-8")

    def raise_os_error(_pid: int, _sig: int) -> None:
        raise OSError()

    monkeypatch.setattr(app.os, "kill", raise_os_error)
    assert app.is_running() is False


@pytest.mark.buttons
def test_parse_pull_counts_handles_missing_numbers():
    scraped, inserted = app._parse_pull_counts("Scraper appended 5 records", "Inserted rows: 3")
    assert scraped == 5
    assert inserted == 3

    scraped, inserted = app._parse_pull_counts("no counts", "")
    assert scraped is None and inserted is None


class ErrorProcess:
    def __init__(self, cmd: list[str]) -> None:
        self.cmd = cmd
        self.returncode = 1
        self.pid = 4321

    def __enter__(self) -> "ErrorProcess":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def communicate(self) -> tuple[str, str]:
        return "", "failure"


@pytest.mark.buttons
def test_pull_data_reports_subprocess_failure(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "PULL_OK_FILE", tmp_path / "ok.txt")
    monkeypatch.setattr(app, "set_lock", lambda pid: None)
    monkeypatch.setattr(app.os, "makedirs", lambda *a, **k: None)

    def popen_factory(cmd: list[str], **_kwargs: Any) -> ErrorProcess:
        return ErrorProcess(cmd)

    monkeypatch.setattr(app.subprocess, "Popen", popen_factory)

    response = client.post("/pull-data", headers=JSON_HEADERS)
    data = response.get_json()
    assert response.status_code == 500
    assert data["status"] == "error"
    assert "Command failed" in data["message"]


@pytest.mark.buttons
def test_pull_data_handles_unexpected_exception(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "PULL_OK_FILE", tmp_path / "ok.txt")
    monkeypatch.setattr(app, "set_lock", lambda pid: None)

    def boom(*_args, **_kwargs):
        raise OSError("spawn failed")

    monkeypatch.setattr(app.subprocess, "Popen", boom)

    response = client.post("/pull-data", headers=JSON_HEADERS)
    data = response.get_json()
    assert response.status_code == 500
    assert data == {"status": "error", "message": "Pull failed: spawn failed"}


class SuccessProcess:
    def __init__(self, cmd: list[str], spec: dict[str, Any]) -> None:
        self._spec = spec
        self.cmd = cmd
        self.returncode = 0
        self.pid = 1111

    def __enter__(self) -> "SuccessProcess":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def communicate(self) -> tuple[str, str]:
        return self._spec.get("stdout", ""), self._spec.get("stderr", "")


@pytest.mark.buttons
def test_pull_data_generates_flash_messages(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "PULL_OK_FILE", tmp_path / "ok.txt")
    monkeypatch.setattr(app, "set_lock", lambda pid: None)
    monkeypatch.setattr(app.os, "makedirs", lambda *a, **k: None)

    responses = {
        tuple(app.SCRAPER_CMD): {"stdout": "appended 3 records", "stderr": ""},
        tuple(app.LOADER_CMD): {"stdout": "Inserted rows: 3", "stderr": ""},
    }

    def factory(cmd: list[str], **_kwargs: Any) -> SuccessProcess:
        return SuccessProcess(cmd, responses[tuple(cmd)])

    monkeypatch.setattr(app.subprocess, "Popen", factory)

    flashes: list[tuple[str, str]] = []
    monkeypatch.setattr(app, "flash", lambda message, category: flashes.append((message, category)))

    response = client.post("/pull-data", headers={"Accept": "text/html"})
    assert response.status_code == 302
    assert any("Pull complete" in msg for msg, _ in flashes)


@pytest.mark.buttons
def test_pull_data_reports_busy_html(client, monkeypatch):
    monkeypatch.setattr(app, "is_running", lambda: True)
    flashes: list[tuple[str, str]] = []
    monkeypatch.setattr(app, "flash", lambda message, category: flashes.append((message, category)))

    response = client.post("/pull-data", headers={"Accept": "text/html"})
    assert response.status_code == 302
    assert flashes and flashes[-1][1] == "error"


@pytest.mark.buttons
def test_loader_failure_html(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "PULL_OK_FILE", tmp_path / "ok.txt")
    monkeypatch.setattr(app, "set_lock", lambda pid: None)
    monkeypatch.setattr(app.os, "makedirs", lambda *a, **k: None)

    call_count = {"n": 0}

    def factory(cmd: list[str], **_kwargs: Any):
        if call_count["n"] == 0:
            call_count["n"] += 1
            return SuccessProcess(cmd, {"stdout": "appended 1 records", "stderr": ""})
        return ErrorProcess(cmd)

    monkeypatch.setattr(app.subprocess, "Popen", factory)

    flashes: list[tuple[str, str]] = []
    monkeypatch.setattr(app, "flash", lambda message, category: flashes.append((message, category)))

    response = client.post("/pull-data", headers={"Accept": "text/html"})
    assert response.status_code == 302
    assert any("Command failed" in msg for msg, _ in flashes)


@pytest.mark.buttons
def test_pull_data_no_counts_html(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "PULL_OK_FILE", tmp_path / "ok.txt")
    monkeypatch.setattr(app, "set_lock", lambda pid: None)
    monkeypatch.setattr(app.os, "makedirs", lambda *a, **k: None)

    responses = {
        tuple(app.SCRAPER_CMD): {"stdout": "", "stderr": ""},
        tuple(app.LOADER_CMD): {"stdout": "", "stderr": ""},
    }

    def factory(cmd: list[str], **_kwargs: Any) -> SuccessProcess:
        return SuccessProcess(cmd, responses[tuple(cmd)])

    monkeypatch.setattr(app.subprocess, "Popen", factory)

    flashes: list[tuple[str, str]] = []
    monkeypatch.setattr(app, "flash", lambda message, category: flashes.append((message, category)))

    response = client.post("/pull-data", headers={"Accept": "text/html"})
    assert response.status_code == 302
    assert any("New data pulled" in msg for msg, _ in flashes)


@pytest.mark.buttons
def test_pull_data_handles_unexpected_exception_html(client, monkeypatch):
    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "set_lock", lambda pid: None)

    def boom(*_args, **_kwargs):
        raise OSError("html fail")

    monkeypatch.setattr(app.subprocess, "Popen", boom)

    flashes: list[tuple[str, str]] = []
    monkeypatch.setattr(app, "flash", lambda message, category: flashes.append((message, category)))

    response = client.post("/pull-data", headers={"Accept": "text/html"})
    assert response.status_code == 302
    assert any("Pull failed" in msg for msg, _ in flashes)


@pytest.mark.buttons
def test_update_analysis_returns_error_when_write_fails(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "compute_gate_state", lambda: (123, 100, True))
    monkeypatch.setattr(app, "ANALYSIS_FILE", tmp_path / "analysis.txt")
    monkeypatch.setattr(app.os, "makedirs", lambda *a, **k: None)

    original_write_text = Path.write_text

    def fail_write_text(self, *args, **kwargs):
        if self == app.ANALYSIS_FILE:
            raise OSError("disk full")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_write_text)

    response = client.post("/update-analysis", headers=JSON_HEADERS)
    data = response.get_json()
    assert response.status_code == 500
    assert data == {"status": "error", "message": "Update failed: disk full"}


@pytest.mark.buttons
def test_update_analysis_write_failure_html(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "compute_gate_state", lambda: (123, 100, True))
    monkeypatch.setattr(app, "ANALYSIS_FILE", tmp_path / "analysis.txt")
    monkeypatch.setattr(app.os, "makedirs", lambda *a, **k: None)

    original_write_text = Path.write_text

    def fail_write_text(self, *args, **kwargs):
        if self == app.ANALYSIS_FILE:
            raise OSError("disk full")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_write_text)

    flashes: list[tuple[str, str]] = []
    monkeypatch.setattr(app, "flash", lambda message, category: flashes.append((message, category)))

    response = client.post("/update-analysis", headers={"Accept": "text/html"})
    assert response.status_code == 302
    assert any("Update failed" in msg for msg, _ in flashes)


@pytest.mark.buttons
def test_update_analysis_no_new_data_html(client, monkeypatch):
    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "compute_gate_state", lambda: (None, None, False))

    response = client.post("/update-analysis")
    assert response.status_code == 302


@pytest.mark.buttons
def test_update_analysis_no_new_data_after_pull(client, monkeypatch):
    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "compute_gate_state", lambda: (123, 200, False))

    response = client.post("/update-analysis")
    assert response.status_code == 302


@pytest.mark.buttons
def test_update_analysis_busy_html(client, monkeypatch):
    monkeypatch.setattr(app, "is_running", lambda: True)
    flashes: list[tuple[str, str]] = []
    monkeypatch.setattr(app, "flash", lambda message, category: flashes.append((message, category)))

    response = client.post("/update-analysis")
    assert response.status_code == 302
    assert flashes and flashes[-1][1] == "error"


@pytest.mark.buttons
def test_update_analysis_success_html(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "compute_gate_state", lambda: (123, 100, True))
    monkeypatch.setattr(app, "ANALYSIS_FILE", tmp_path / "analysis.txt")
    monkeypatch.setattr(app.os, "makedirs", lambda *a, **k: None)

    flashes: list[tuple[str, str]] = []
    monkeypatch.setattr(app, "flash", lambda message, category: flashes.append((message, category)))

    response = client.post("/update-analysis")
    assert response.status_code == 302
    assert flashes and flashes[-1][1] == "success"
    assert Path(app.ANALYSIS_FILE).exists()


@pytest.mark.buttons
def test_app_module_can_run_as_script(monkeypatch):
    fake_db = types.SimpleNamespace(get_conn=lambda: None)
    monkeypatch.setitem(sys.modules, "db", fake_db)

    run_calls = []
    monkeypatch.setattr(Flask, "run", lambda self, **kwargs: run_calls.append(kwargs))

    runpy.run_path(Path("src/app.py"), run_name="__main__")
    assert run_calls and run_calls[0]["port"] == 8080
