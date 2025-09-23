'''Integration tests for the /pull-data endpoint and data loading logic.'''

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import pytest

from tests._app_import import import_app_module

app = import_app_module("app")
load_data = import_app_module("load_data")
query_data = import_app_module("query_data")

JSON_HEADERS = {"Accept": "application/json"}


@dataclass
class FakeDBConnection:
    '''A fake database connection that records inserted rows.'''
    rows: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.seen_urls: set[str] = set()

    def __enter__(self) -> "FakeDBConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def cursor(self) -> "FakeCursor":
        '''Return a new fake cursor.'''
        return FakeCursor(self)


class FakeCursor:
    '''A fake database cursor that simulates inserts.'''
    def __init__(self, conn: FakeDBConnection) -> None:
        self.conn = conn

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        '''Simulate executing an SQL command.'''
        if params is None:
            params = {}
        if "INSERT INTO applicants" in sql:
            url = params.get("url")
            if url and url not in self.conn.seen_urls:
                self.conn.seen_urls.add(url)
                self.conn.rows.append(params.copy())

    def fetchone(self) -> None:
        '''Simulate fetching one row (not used in loader).'''
        return None

    def fetchall(self) -> list[Any]:
        '''Simulate fetching all rows (not used in loader).'''
        return []


class FakeProcess:
    '''A fake subprocess.Popen that simulates command execution.'''

    _pid_counter = 2000

    def __init__(self, cmd: list[str], spec: dict[str, Any], calls: list[list[str]]) -> None:
        self._cmd = tuple(cmd)
        self._spec = spec
        self._calls = calls
        self._calls.append(cmd)
        FakeProcess._pid_counter += 1
        self.pid = FakeProcess._pid_counter
        self.returncode = spec.get("returncode", 0)

    def __enter__(self) -> "FakeProcess":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def communicate(self) -> tuple[str, str]:
        '''Simulate process communication, returning stdout and stderr.'''
        stdout = self._spec.get("stdout", "")
        stderr = self._spec.get("stderr", "")
        callback: Callable[[], tuple[str, str] | str | None] | None = self._spec.get("callback")
        if callback:
            result = callback()
            if isinstance(result, tuple):
                stdout, stderr = result
            elif isinstance(result, str):
                stdout = result
        return stdout, stderr


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
    sample_records = [
        {
            "program": "MS in Computer Science",
            "comments": "Great profile",
            "date_added": "2025-01-10",
            "url": "https://example.com/applicant-1",
            "status": "Accepted on 01/15/2025",
            "term": "Fall 2025",
            "US/International": "American",
            "GPA": "3.80",
            "GRE": "166",
            "GRE V": "158",
            "GRE AW": "5.0",
            "Degree": "MS",
            "llm-generated-program": "Computer Science",
            "llm-generated-university": "Johns Hopkins University",
        }
    ]

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


class QueryCursor:
    '''A fake database cursor that returns predefined query results.'''
    def __init__(self, responses: Sequence[Any]):
        self._responses = list(responses)
        self._index = 0

    def __enter__(self) -> "QueryCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass

    def execute(self, sql: str, params: Any | None = None) -> None:
        '''Simulate executing an SQL command (no-op).'''
        del sql, params

    def _next(self) -> Any:
        if self._index >= len(self._responses):
            raise AssertionError("No more fake query responses defined")
        value = self._responses[self._index]
        self._index += 1
        return value

    def fetchone(self) -> Any:
        '''Return the next predefined response.'''
        return self._next()

    def fetchall(self) -> list[Any]:
        '''Return the next predefined response as a list.'''
        result = self._next()
        return list(result)


class QueryConnection:
    '''A fake database connection that returns a fake cursor with predefined responses.'''
    def __init__(self, responses: Sequence[Any]):
        self._responses = responses

    def __enter__(self) -> "QueryConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def cursor(self) -> QueryCursor:
        """Provide a query cursor configured with canned responses."""
        return QueryCursor(self._responses)


@pytest.mark.db
def test_compute_stats_returns_expected_keys(monkeypatch):
    '''Test that compute_stats returns expected keys and values.'''
    responses = [
        {"c": 2},
        {"pct_international": 33.33},
        {"avg_gpa": 3.5, "avg_gre_q": 160, "avg_gre_v": 155, "avg_gre_aw": 4.5},
        {"avg_gpa_american_2025": 3.4},
        {"pct_accept_2025": 72.15},
        {"avg_gpa_accepted_2025": 3.8},
        {"c": 5},
        {"c": 3},
        {"avg_american": 3.4, "avg_international": 3.2, "diff": 0.2},
        [
            {"university": "Uni A", "n": 25, "acceptance_rate_pct": 55.12},
            {"university": "Uni B", "n": 21, "acceptance_rate_pct": 50.00},
        ],
    ]

    fake_conn = QueryConnection(responses)
    monkeypatch.setattr(query_data, "get_conn", lambda: fake_conn)

    result = query_data.compute_stats()

    expected_keys = {f"q{i}" for i in range(1, 11)}
    assert expected_keys.issubset(result.keys())
    assert result["q1"] == 2
    assert result["q5"] == 72.15
    assert result["q3"]["avg_gre_q"] == 160
    assert result["q10"][0]["university"] == "Uni A"
