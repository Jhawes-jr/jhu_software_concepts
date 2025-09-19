from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any, Callable

import builtins
import pytest

import app
import load_data

JSON_HEADERS = {"Accept": "application/json"}


class FakeDBConnection:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self._seen: set[str] = set()

    def __enter__(self) -> "FakeDBConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass

    def cursor(self) -> "FakeCursor":
        return FakeCursor(self)


class FakeCursor:
    def __init__(self, conn: FakeDBConnection) -> None:
        self.conn = conn

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        params = params or {}
        if "INSERT INTO applicants" in sql:
            url = params.get("url")
            if url and url not in self.conn._seen:
                self.conn._seen.add(url)
                self.conn.rows.append(params.copy())

    def fetchone(self) -> Any:  # pragma: no cover - not used here
        return None

    def fetchall(self) -> list[Any]:  # pragma: no cover - not used here
        return []


class FakeProcess:
    _pid = 4000

    def __init__(self, cmd: list[str], spec: dict[str, Any], calls: list[list[str]]) -> None:
        self._spec = spec
        self._cmd = cmd
        calls.append(cmd)
        FakeProcess._pid += 1
        self.pid = FakeProcess._pid
        self.returncode = spec.get("returncode", 0)

    def communicate(self) -> tuple[str, str]:
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


@pytest.fixture()
def integration_env(monkeypatch, tmp_path):
    FakeProcess._pid = 4000

    db = FakeDBConnection()
    monkeypatch.setattr(load_data, "get_conn", lambda: db)

    records: list[dict[str, Any]] = []

    def set_records(items: list[dict[str, Any]]) -> None:
        records.clear()
        records.extend(items)

    monkeypatch.setattr(load_data, "iter_records", lambda path: list(records))

    captured: list[str] = []

    def fake_print(*args, **kwargs) -> None:
        captured.append(" ".join(str(a) for a in args))

    monkeypatch.setattr("builtins.print", fake_print)

    def loader_callback() -> str:
        captured.clear()
        load_data.main("ignored")
        return captured[-1] if captured else "Inserted rows: 0"

    def scraper_callback() -> tuple[str, str]:
        return f"appended {len(records)} records", ""

    calls: list[list[str]] = []
    process_specs = {
        tuple(app.SCRAPER_CMD): {"callback": scraper_callback},
        tuple(app.LOADER_CMD): {"stdout": "", "stderr": "", "callback": loader_callback},
    }

    def factory(cmd: list[str], **kwargs: Any) -> FakeProcess:
        spec = process_specs[tuple(cmd)]
        return FakeProcess(cmd, spec, calls)

    monkeypatch.setattr(app.subprocess, "Popen", factory)
    monkeypatch.setattr(app, "set_lock", lambda pid: None)
    monkeypatch.setattr(app, "is_running", lambda: False)

    pull_ok = tmp_path / "last_pull_success.txt"
    analysis_file = tmp_path / "analysis.txt"
    lock_file = tmp_path / "lock.txt"
    monkeypatch.setattr(app, "PULL_OK_FILE", str(pull_ok))
    monkeypatch.setattr(app, "ANALYSIS_FILE", str(analysis_file))
    monkeypatch.setattr(app, "LOCK_FILE", str(lock_file))

    latest_stats: dict[str, Any] = {}

    def compute_stats() -> dict[str, Any]:
        return latest_stats.copy()

    def set_stats(data: dict[str, Any]) -> None:
        latest_stats.clear()
        latest_stats.update(data)

    monkeypatch.setattr(app, "compute_stats", compute_stats)

    return SimpleNamespace(
        db=db,
        set_records=set_records,
        set_stats=set_stats,
        calls=calls,
        pull_ok=pull_ok,
        analysis_file=analysis_file,
    )


@pytest.mark.integration
def test_end_to_end_flow(client, integration_env):
    env = integration_env
    env.set_records([
        {
            "program": "MS in Computer Science",
            "comments": "Profile A",
            "date_added": "2025-01-05",
            "url": "https://example.com/applicant-1",
            "status": "Accepted on 01/20/2025",
            "term": "Fall 2025",
            "US/International": "American",
            "GPA": "3.80",
            "GRE": "166",
            "GRE V": "158",
            "GRE AW": "5.0",
            "Degree": "MS",
            "llm-generated-program": "Computer Science",
            "llm-generated-university": "Johns Hopkins University",
        },
        {
            "program": "MS in Computer Science",
            "comments": "Profile B",
            "date_added": "2025-02-01",
            "url": "https://example.com/applicant-2",
            "status": "Rejected on 02/10/2025",
            "term": "Fall 2025",
            "US/International": "International",
            "GPA": "3.40",
            "GRE": "161",
            "GRE V": "155",
            "GRE AW": "4.0",
            "Degree": "MS",
            "llm-generated-program": "Computer Science",
            "llm-generated-university": "Johns Hopkins University",
        },
    ])

    pull_response = client.post("/pull-data", headers=JSON_HEADERS)
    assert pull_response.status_code == 200
    assert pull_response.get_json() == {"status": "ok", "scraped": 2, "inserted": 2}
    assert len(env.db.rows) == 2

    update_response = client.post("/update-analysis", headers=JSON_HEADERS)
    assert update_response.status_code == 200
    assert update_response.get_json() == {"status": "ok", "updated": True}
    assert env.analysis_file.exists()

    env.set_stats(
        {
            "q1": 2,
            "q2": 50.0,
            "q3": {
                "avg_gpa": 3.6,
                "avg_gre_q": 163.5,
                "avg_gre_v": 156.5,
                "avg_gre_aw": 4.5,
            },
            "q4": 3.8,
            "q5": 50.0,
            "q6": 3.8,
            "q7": 1,
            "q8": 0,
            "q9": {
                "avg_american": 3.8,
                "avg_international": 3.4,
                "diff": 0.4,
            },
            "q10": [SimpleNamespace(university="Test U", acceptance_rate_pct=66.6667, n=30)],
        }
    )

    page = client.get("/analysis")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Answer: Applicant count: 2" in html
    assert "50.00%" in html
    assert "66.67" in html


@pytest.mark.integration
def test_multiple_pulls_preserve_uniqueness(client, integration_env):
    env = integration_env
    env.set_records([
        {
            "program": "MS in Computer Science",
            "comments": "Profile A",
            "date_added": "2025-01-05",
            "url": "https://example.com/applicant-1",
            "status": "Accepted on 01/20/2025",
            "term": "Fall 2025",
            "US/International": "American",
            "GPA": "3.80",
            "GRE": "166",
            "GRE V": "158",
            "GRE AW": "5.0",
            "Degree": "MS",
            "llm-generated-program": "Computer Science",
            "llm-generated-university": "Johns Hopkins University",
        },
        {
            "program": "MS in Computer Science",
            "comments": "Profile B",
            "date_added": "2025-02-01",
            "url": "https://example.com/applicant-2",
            "status": "Rejected on 02/10/2025",
            "term": "Fall 2025",
            "US/International": "International",
            "GPA": "3.40",
            "GRE": "161",
            "GRE V": "155",
            "GRE AW": "4.0",
            "Degree": "MS",
            "llm-generated-program": "Computer Science",
            "llm-generated-university": "Johns Hopkins University",
        },
    ])
    first = client.post("/pull-data", headers=JSON_HEADERS)
    assert first.status_code == 200
    assert len(env.db.rows) == 2

    env.set_records([
        {
            "program": "MS in Computer Science",
            "comments": "Profile A",
            "date_added": "2025-01-05",
            "url": "https://example.com/applicant-1",
            "status": "Accepted on 01/20/2025",
            "term": "Fall 2025",
            "US/International": "American",
            "GPA": "3.80",
            "GRE": "166",
            "GRE V": "158",
            "GRE AW": "5.0",
            "Degree": "MS",
            "llm-generated-program": "Computer Science",
            "llm-generated-university": "Johns Hopkins University",
        },
        {
            "program": "MS in Computer Science",
            "comments": "Profile B",
            "date_added": "2025-02-01",
            "url": "https://example.com/applicant-2",
            "status": "Rejected on 02/10/2025",
            "term": "Fall 2025",
            "US/International": "International",
            "GPA": "3.40",
            "GRE": "161",
            "GRE V": "155",
            "GRE AW": "4.0",
            "Degree": "MS",
            "llm-generated-program": "Computer Science",
            "llm-generated-university": "Johns Hopkins University",
        },
        {
            "program": "MS in Data Science",
            "comments": "Profile C",
            "date_added": "2025-03-01",
            "url": "https://example.com/applicant-3",
            "status": "Accepted on 03/15/2025",
            "term": "Fall 2025",
            "US/International": "International",
            "GPA": "3.90",
            "GRE": "168",
            "GRE V": "160",
            "GRE AW": "5.0",
            "Degree": "MS",
            "llm-generated-program": "Data Science",
            "llm-generated-university": "Georgetown University",
        },
    ])

    second = client.post("/pull-data", headers=JSON_HEADERS)
    assert second.status_code == 200
    assert len(env.db.rows) == 3
    urls = {row["url"] for row in env.db.rows}
    assert urls == {
        "https://example.com/applicant-1",
        "https://example.com/applicant-2",
        "https://example.com/applicant-3",
    }
