'''Test the end-to-end integration of the scraper, loader, and web app.'''

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from tests._app_import import import_app_module
from tests.fakes import FakeDBConnection, FakeProcess
from tests.sample_data import (
    APPLICANT_RECORDS,
    integration_stats,
    iter_records_with_new_entry,
)

APP_MODULE = import_app_module("app")
load_data = import_app_module("load_data")


JSON_HEADERS = {"Accept": "application/json"}


@pytest.fixture(name="integration_state")
def _integration_state(monkeypatch, tmp_path):
    '''Set up a fake environment for end-to-end integration tests.'''
    FakeProcess.pid_counter = 4000

    fake_db = FakeDBConnection()
    monkeypatch.setattr(load_data, "get_conn", lambda: fake_db)

    state = SimpleNamespace(records=[], captured=[], calls=[], stats={})

    def set_records(items: list[dict[str, Any]]) -> None:
        state.records = list(items)

    monkeypatch.setattr(load_data, "iter_records", lambda path: list(state.records))

    def record_print(*args, **_kwargs) -> None:
        state.captured.append(" ".join(str(arg) for arg in args))

    monkeypatch.setattr("builtins.print", record_print)

    def loader_callback() -> str:
        state.captured.clear()
        load_data.main("ignored")
        return state.captured[-1] if state.captured else "Inserted rows: 0"

    def scraper_callback() -> tuple[str, str]:
        return f"appended {len(state.records)} records", ""

    def factory(cmd: list[str], **_kwargs: Any) -> FakeProcess:
        command = tuple(cmd)
        if command == tuple(APP_MODULE.SCRAPER_CMD):
            spec: dict[str, Any] = {"callback": scraper_callback}
        elif command == tuple(APP_MODULE.LOADER_CMD):
            spec = {"stdout": "", "stderr": "", "callback": loader_callback}
        else:
            raise AssertionError(f"Unexpected command: {cmd}")
        return FakeProcess(cmd, spec, state.calls)

    monkeypatch.setattr("app.subprocess.Popen", factory)
    monkeypatch.setattr(APP_MODULE, "set_lock", lambda pid: None)
    monkeypatch.setattr(APP_MODULE, "is_running", lambda: False)

    pull_ok = tmp_path / "last_pull_success.txt"
    analysis_file = tmp_path / "analysis.txt"
    lock_file = tmp_path / "lock.txt"
    monkeypatch.setattr(APP_MODULE, "PULL_OK_FILE", pull_ok)
    monkeypatch.setattr(APP_MODULE, "ANALYSIS_FILE", analysis_file)
    monkeypatch.setattr(APP_MODULE, "LOCK_FILE", lock_file)

    def compute_stats() -> dict[str, Any]:
        return state.stats.copy()

    def set_stats(data: dict[str, Any]) -> None:
        state.stats = data.copy()

    monkeypatch.setattr(APP_MODULE, "compute_stats", compute_stats)

    return SimpleNamespace(
        db=fake_db,
        set_records=set_records,
        set_stats=set_stats,
        calls=state.calls,
        pull_ok=pull_ok,
        analysis_file=analysis_file,
    )


@pytest.mark.integration
def test_end_to_end_flow(client, integration_state):
    '''Test the full end-to-end flow of pulling data and updating analysis.'''
    env = integration_state
    env.set_records(APPLICANT_RECORDS)

    pull_response = client.post("/pull-data", headers=JSON_HEADERS)
    assert pull_response.status_code == 200
    assert pull_response.get_json() == {"status": "ok", "scraped": 2, "inserted": 2}
    assert len(env.db.rows) == 2

    update_response = client.post("/update-analysis", headers=JSON_HEADERS)
    assert update_response.status_code == 200
    assert update_response.get_json() == {"status": "ok", "updated": True}
    assert env.analysis_file.exists()

    env.set_stats(integration_stats())

    page = client.get("/analysis")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Answer: Applicant count: 2" in html
    assert "50.00%" in html
    assert "66.67" in html


@pytest.mark.integration
def test_multiple_pulls_preserve_uniqueness(client, integration_state):
    '''Test that multiple pulls do not create duplicate entries.'''
    env = integration_state
    env.set_records(APPLICANT_RECORDS)
    first = client.post("/pull-data", headers=JSON_HEADERS)
    assert first.status_code == 200
    assert len(env.db.rows) == 2

    env.set_records(iter_records_with_new_entry())

    second = client.post("/pull-data", headers=JSON_HEADERS)
    assert second.status_code == 200
    assert len(env.db.rows) == 3
    urls = {row["url"] for row in env.db.rows}
    assert urls == {
        "https://example.com/applicant-1",
        "https://example.com/applicant-2",
        "https://example.com/applicant-3",
    }
