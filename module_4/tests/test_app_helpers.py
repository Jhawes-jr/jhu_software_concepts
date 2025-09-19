from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path
from typing import Any

import pytest

import app

JSON_HEADERS = {"Accept": "application/json"}


@pytest.mark.buttons
def test_datetimeformat_returns_empty_on_error():
    assert app.datetimeformat("not-a-timestamp") == ""


@pytest.mark.buttons
def test_wants_json_response_branches(client):
    with app.app.test_request_context("/", json={"ping": "pong"}):
        assert app.wants_json_response() is True

    with app.app.test_request_context("/", headers={"Accept": "application/json"}):
        assert app.wants_json_response() is True

    with app.app.test_request_context("/", headers={"Accept": "text/html"}):
        assert app.wants_json_response() is False


@pytest.mark.buttons
def test_set_lock_creates_and_clears_file(monkeypatch, tmp_path):
    lock_path = tmp_path / "locks" / "scrape.lock"
    monkeypatch.setattr(app, "LOCK_FILE", str(lock_path))

    app.set_lock(999)
    assert lock_path.exists()

    app.set_lock(None)
    assert not lock_path.exists()

    app.set_lock(None)


@pytest.mark.buttons
def test_is_running_true_when_pid_alive(monkeypatch, tmp_path):
    lock_path = tmp_path / "lock.txt"
    monkeypatch.setattr(app, "LOCK_FILE", str(lock_path))

    called = {}
    monkeypatch.setattr(app.os, "kill", lambda pid, sig: called.setdefault("pid", pid))

    app.set_lock(123)
    assert app.is_running() is True
    assert called["pid"] == 123


@pytest.mark.buttons
def test_is_running_handles_missing_or_bad_lock(monkeypatch, tmp_path):
    lock_path = tmp_path / "missing.lock"
    monkeypatch.setattr(app, "LOCK_FILE", str(lock_path))
    assert app.is_running() is False

    lock_path.write_text("not-a-pid", encoding="utf-8")
    removed: list[str] = []
    monkeypatch.setattr(app.os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))
    monkeypatch.setattr(app.os, "remove", lambda path: removed.append(path))
    assert app.is_running() is False
    assert str(lock_path) in removed


@pytest.mark.buttons
def test_is_running_handles_missing_lock_removal(monkeypatch, tmp_path):
    lock_path = tmp_path / "stale.lock"
    monkeypatch.setattr(app, "LOCK_FILE", str(lock_path))
    lock_path.write_text("invalid", encoding="utf-8")
    monkeypatch.setattr(app.os, "kill", lambda pid, sig: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(app.os, "remove", lambda path: (_ for _ in ()).throw(FileNotFoundError()))
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

    def communicate(self) -> tuple[str, str]:
        return "", "failure"


@pytest.mark.buttons
def test_pull_data_reports_subprocess_failure(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "PULL_OK_FILE", str(tmp_path / "ok.txt"))
    monkeypatch.setattr(app, "set_lock", lambda pid: None)
    monkeypatch.setattr(app.os, "makedirs", lambda *a, **k: None)

    monkeypatch.setattr(app.subprocess, "Popen", lambda cmd, **kwargs: ErrorProcess(cmd))

    response = client.post("/pull-data", headers=JSON_HEADERS)
    data = response.get_json()
    assert response.status_code == 500
    assert data["status"] == "error"
    assert "Command failed" in data["message"]


@pytest.mark.buttons
def test_pull_data_handles_unexpected_exception(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "PULL_OK_FILE", str(tmp_path / "ok.txt"))
    monkeypatch.setattr(app, "set_lock", lambda pid: None)

    def boom(*_args, **_kwargs):
        raise RuntimeError("spawn failed")

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

    def communicate(self) -> tuple[str, str]:
        return self._spec.get("stdout", ""), self._spec.get("stderr", "")


@pytest.mark.buttons
def test_pull_data_generates_flash_messages(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "PULL_OK_FILE", str(tmp_path / "ok.txt"))
    monkeypatch.setattr(app, "set_lock", lambda pid: None)
    monkeypatch.setattr(app.os, "makedirs", lambda *a, **k: None)

    responses = {
        tuple(app.SCRAPER_CMD): {"stdout": "appended 3 records", "stderr": ""},
        tuple(app.LOADER_CMD): {"stdout": "Inserted rows: 3", "stderr": ""},
    }

    def factory(cmd: list[str], **kwargs: Any) -> SuccessProcess:
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
    monkeypatch.setattr(app, "PULL_OK_FILE", str(tmp_path / "ok.txt"))
    monkeypatch.setattr(app, "set_lock", lambda pid: None)
    monkeypatch.setattr(app.os, "makedirs", lambda *a, **k: None)

    call_count = {"n": 0}

    def factory(cmd: list[str], **kwargs: Any):
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
    monkeypatch.setattr(app, "PULL_OK_FILE", str(tmp_path / "ok.txt"))
    monkeypatch.setattr(app, "set_lock", lambda pid: None)
    monkeypatch.setattr(app.os, "makedirs", lambda *a, **k: None)

    responses = {
        tuple(app.SCRAPER_CMD): {"stdout": "", "stderr": ""},
        tuple(app.LOADER_CMD): {"stdout": "", "stderr": ""},
    }

    def factory(cmd: list[str], **kwargs: Any) -> SuccessProcess:
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
        raise RuntimeError("html fail")

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
    monkeypatch.setattr(app, "ANALYSIS_FILE", str(tmp_path / "analysis.txt"))
    monkeypatch.setattr(app.os, "makedirs", lambda *a, **k: None)

    def failing_open(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", failing_open)

    response = client.post("/update-analysis", headers=JSON_HEADERS)
    data = response.get_json()
    assert response.status_code == 500
    assert data == {"status": "error", "message": "Update failed: disk full"}


@pytest.mark.buttons
def test_update_analysis_write_failure_html(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "compute_gate_state", lambda: (123, 100, True))
    monkeypatch.setattr(app, "ANALYSIS_FILE", str(tmp_path / "analysis.txt"))
    monkeypatch.setattr(app.os, "makedirs", lambda *a, **k: None)

    def failing_open(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", failing_open)

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
    monkeypatch.setattr(app, "ANALYSIS_FILE", str(tmp_path / "analysis.txt"))
    monkeypatch.setattr(app.os, "makedirs", lambda *a, **k: None)

    flashes: list[tuple[str, str]] = []
    monkeypatch.setattr(app, "flash", lambda message, category: flashes.append((message, category)))

    response = client.post("/update-analysis")
    assert response.status_code == 302
    assert flashes and flashes[-1][1] == "success"
    assert Path(app.ANALYSIS_FILE).exists()


@pytest.mark.buttons
def test_app_module_can_run_as_script(monkeypatch):
    import types
    from flask.app import Flask

    fake_db = types.SimpleNamespace(get_conn=lambda: None)
    monkeypatch.setitem(sys.modules, "db", fake_db)

    run_calls = []
    monkeypatch.setattr(Flask, "run", lambda self, **kwargs: run_calls.append(kwargs))

    runpy.run_path(Path("src/app.py"), run_name="__main__")
    assert run_calls and run_calls[0]["port"] == 8080
