'''Integration tests for the /pull-data endpoint and data loading logic.'''

from __future__ import annotations

from typing import Any

import pytest

from tests._app_import import import_app_module
from tests.fakes import FakeDBConnection, FakeProcess, QueryConnection
from tests.sample_data import APPLICANT_RECORDS, STAT_RESPONSES

app = import_app_module("app")
load_data = import_app_module("load_data")
query_data = import_app_module("query_data")

JSON_HEADERS = {"Accept": "application/json"}


@pytest.fixture(name="fake_db")
def fixture_fake_db(monkeypatch) -> FakeDBConnection:
    '''Patch the database connection to use a fake in-memory implementation.'''
    conn = FakeDBConnection()
    monkeypatch.setattr(load_data, "get_conn", lambda: conn)
    return conn


@pytest.fixture(name="patched_loader")
def fixture_patched_loader(monkeypatch, fake_db):
    '''Patch the loader to use a fake database and simulate input data.'''
    del fake_db  # fixture invoked for side effects
    sample_record = APPLICANT_RECORDS[0].copy()
    sample_record.update({
        "comments": "Great profile",
        "date_added": "2025-01-10",
        "status": "Accepted on 01/15/2025",
    })
    sample_records = [sample_record]

    monkeypatch.setattr(load_data, "iter_records", lambda path: list(sample_records))

    captured: list[str] = []

    def fake_print(*args, **_kwargs) -> None:
        message = " ".join(str(a) for a in args)
        captured.append(message)

    monkeypatch.setattr("builtins.print", fake_print)

    def loader_callback() -> str:
        captured.clear()
        load_data.main("ignored")
        return captured[-1] if captured else "Inserted rows: 0"

    monkeypatch.setattr(app, "is_running", lambda: False)
    monkeypatch.setattr(app, "set_lock", lambda pid: None)

    return {
        tuple(app.SCRAPER_CMD): {"stdout": "appended 1 records", "stderr": ""},
        tuple(app.LOADER_CMD): {"stdout": "", "stderr": "", "callback": loader_callback},
    }


@pytest.fixture(name="fake_popen")
def fixture_fake_popen(monkeypatch, patched_loader):
    '''Patch subprocess.Popen to use a fake implementation.'''
    calls: list[list[str]] = []

    def factory(cmd: list[str], **_kwargs: Any) -> FakeProcess:
        spec = patched_loader[tuple(cmd)]
        return FakeProcess(cmd, spec, calls)

    monkeypatch.setattr(app.subprocess, "Popen", factory)
    return calls


@pytest.mark.db
@pytest.mark.usefixtures("patched_loader", "fake_popen")
def test_pull_data_inserts_rows(client, fake_db, monkeypatch, tmp_path):
    '''Test that pulling data inserts expected rows into the database.'''
    monkeypatch.setattr(app, "PULL_OK_FILE", tmp_path / "pull_ok.txt")

    response = client.post("/pull-data", headers=JSON_HEADERS)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {"status": "ok", "scraped": 1, "inserted": 1}

    assert len(fake_db.rows) == 1
    inserted = fake_db.rows[0]
    assert inserted["url"].startswith("https://example.com")
    assert inserted["program"] == "MS in Computer Science"
    assert inserted["term"] == "Fall 2025"
    assert inserted["gpa"] == 3.8
    assert str(inserted["date_added"]) == "2025-01-10"


@pytest.mark.db
@pytest.mark.usefixtures("patched_loader", "fake_popen")
def test_pull_data_is_idempotent(fake_db, client, monkeypatch, tmp_path):
    '''Test that pulling data twice does not create duplicate rows.'''
    monkeypatch.setattr(app, "PULL_OK_FILE", tmp_path / "pull_ok.txt")

    first = client.post("/pull-data", headers=JSON_HEADERS)
    assert first.status_code == 200
    assert len(fake_db.rows) == 1

    second = client.post("/pull-data", headers=JSON_HEADERS)
    assert second.status_code == 200
    assert len(fake_db.rows) == 1, "Duplicate pull should not create duplicate rows"


@pytest.mark.db
def test_compute_stats_returns_expected_keys(monkeypatch):
    '''Test that compute_stats returns expected keys and values.'''
    fake_conn = QueryConnection(STAT_RESPONSES)
    monkeypatch.setattr(query_data, "get_conn", lambda: fake_conn)

    result = query_data.compute_stats()

    expected_keys = {f"q{i}" for i in range(1, 11)}
    assert expected_keys.issubset(result.keys())
    assert result["q1"] == 2
    assert result["q5"] == 72.15
    assert result["q3"]["avg_gre_q"] == 160
    assert result["q10"][0]["university"] == "Uni A"
