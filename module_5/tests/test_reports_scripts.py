from __future__ import annotations

import csv
import json
import runpy
import sys
from pathlib import Path
from typing import Any, Iterable, Iterator

import pytest

import check_status
import count_rows
import date_added_report
import db
import query_data


class ScriptCursor:
    def __init__(self, responses: Iterator[Any]) -> None:
        self._responses = responses
        self._current: Any | None = None

    def __enter__(self) -> "ScriptCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass

    def execute(self, sql: str, params: Any | None = None) -> None:
        try:
            self._current = next(self._responses)
        except StopIteration as exc:
            raise AssertionError("No scripted response available for execute call") from exc

    def fetchone(self) -> Any:
        if self._current is None:
            raise AssertionError("fetchone called without prior execute")
        value = self._current
        self._current = None
        return value

    def fetchall(self) -> list[Any]:
        if self._current is None:
            raise AssertionError("fetchall called without prior execute")
        value = self._current
        self._current = None
        return list(value)


class ScriptConnection:
    def __init__(self, responses: Iterable[Any]) -> None:
        self._responses = iter(responses)

    def __enter__(self) -> "ScriptConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass

    def cursor(self) -> ScriptCursor:
        return ScriptCursor(self._responses)


@pytest.mark.db
def test_check_status_main(monkeypatch):
    connections = [
        ScriptConnection([[{"status": "Accepted on 01/01/2025"}, {"status": "Rejected on 02/02/2025"}]]),
        ScriptConnection([
            {
                "min_gpa": 3.1,
                "max_gpa": 4.0,
                "min_gre_q": 150,
                "max_gre_q": 168,
                "min_gre_v": 145,
                "max_gre_v": 165,
                "min_gre_aw": 2.5,
                "max_gre_aw": 5.5,
            }
        ]),
    ]

    monkeypatch.setattr(check_status, "get_conn", lambda: connections.pop(0))

    captured: list[str] = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: captured.append(" ".join(str(a) for a in args)))

    check_status.main()

    joined = "\n".join(captured)
    assert "Distinct prefixes" in joined
    assert "Accepted" in joined
    assert "GPA" in joined


@pytest.mark.db
def test_check_status_script_entry(monkeypatch, capsys):
    connections = [
        ScriptConnection([[{"status": "Accepted on 01/01/2025"}]]),
        ScriptConnection([
            {
                "min_gpa": 3.0,
                "max_gpa": 4.0,
                "min_gre_q": 150,
                "max_gre_q": 165,
                "min_gre_v": 145,
                "max_gre_v": 160,
                "min_gre_aw": 3.0,
                "max_gre_aw": 5.0,
            }
        ]),
    ]

    def fake_get_conn():
        if not connections:
            raise AssertionError("No more connections")
        return connections.pop(0)

    import types
    fake_db = types.SimpleNamespace(get_conn=fake_get_conn)
    monkeypatch.setitem(sys.modules, "db", fake_db)

    runpy.run_path(Path("src/check_status.py"), run_name="__main__")
    out = capsys.readouterr().out
    assert "Distinct prefixes" in out


@pytest.mark.db
def test_count_rows_main(monkeypatch):
    conn = ScriptConnection([{ "total": 12 }])
    monkeypatch.setattr(count_rows, "get_conn", lambda: conn)

    captured: list[str] = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: captured.append(" ".join(str(a) for a in args)))

    count_rows.main()
    assert captured[-1] == "Total rows in applicants: 12"


@pytest.mark.db
def test_count_rows_script_entry(monkeypatch, capsys):
    import types
    fake_db = types.SimpleNamespace(get_conn=lambda: ScriptConnection([{ "total": 7 }]))
    monkeypatch.setitem(sys.modules, "db", fake_db)

    runpy.run_path(Path("src/count_rows.py"), run_name="__main__")
    out = capsys.readouterr().out
    assert "Total rows in applicants: 7" in out


@pytest.mark.db
def test_create_schema_script_entry(monkeypatch, capsys):
    import types

    executed: list[str] = []

    class Cursor:
        def __enter__(self) -> "Cursor":
            return self
        def __exit__(self, exc_type, exc, tb) -> None:
            pass
        def execute(self, sql: str) -> None:
            executed.append(sql)

    class Conn:
        def __enter__(self) -> "Conn":
            return self
        def __exit__(self, exc_type, exc, tb) -> None:
            pass
        def cursor(self) -> Cursor:
            return Cursor()

    fake_db = types.SimpleNamespace(get_conn=lambda: Conn())
    monkeypatch.setitem(sys.modules, "db", fake_db)

    runpy.run_path(Path("src/create_schema.py"), run_name="__main__")
    out = capsys.readouterr().out
    assert "Schema created/verified." in out
    assert executed and "CREATE TABLE" in executed[0]


@pytest.mark.db
def test_date_added_report_main(monkeypatch, tmp_path):
    responses = [
        {"total": 3, "with_date": 2, "null_date": 1},
        {"min_date": "2025-01-01", "max_date": "2025-02-01"},
        [
            {"date_added": "2025-01-01", "n": 1},
            {"date_added": "2025-02-01", "n": 1},
        ],
        [
            {"date_added": "1999-12-31", "n": 1},
        ],
    ]

    monkeypatch.setattr(date_added_report, "get_conn", lambda: ScriptConnection(responses))
    monkeypatch.setattr(date_added_report, "Path", lambda _: tmp_path / "dummy.py")

    captured: list[str] = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: captured.append(" ".join(str(a) for a in args)))

    date_added_report.main()

    out_file = tmp_path / "date_added_counts.csv"
    assert out_file.exists()
    rows = list(csv.reader(out_file.open()))
    assert rows[0] == ["date_added", "count"]
    assert rows[1] == ["2025-01-01", "1"]
    joined = "\n".join(captured)
    assert "Out-of-range" in joined


@pytest.mark.db
def test_date_added_report_script_entry(monkeypatch, tmp_path, capsys):
    responses = [
        {"total": 0, "with_date": 0, "null_date": 0},
        {"min_date": None, "max_date": None},
        [],
        [],
    ]

    import types
    fake_db = types.SimpleNamespace(get_conn=lambda: ScriptConnection(responses))
    monkeypatch.setitem(sys.modules, "db", fake_db)
    monkeypatch.setattr(date_added_report, "Path", lambda _: tmp_path / "dummy.py")

    runpy.run_path(Path("src/date_added_report.py"), run_name="__main__")
    out = capsys.readouterr().out
    assert "Wrote per-date counts" in out


@pytest.mark.db
def test_db_get_conn_uses_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/dbname")
    called = {}

    def fake_connect(url, row_factory):
        called["url"] = url
        called["row_factory"] = row_factory
        return "connection"

    monkeypatch.setattr(db.psycopg, "connect", fake_connect)

    conn = db.get_conn()
    assert conn == "connection"
    assert called["url"].startswith("postgresql://")


@pytest.mark.db
def test_db_get_conn_builds_arguments(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PGHOST", "db-host")
    monkeypatch.setenv("PGPORT", "6543")
    monkeypatch.setenv("PGDATABASE", "dbname")
    monkeypatch.setenv("PGUSER", "dbuser")
    monkeypatch.setenv("PGPASSWORD", "secret")

    called = {}

    def fake_connect(**kwargs):
        called.update(kwargs)
        return "connection"

    monkeypatch.setattr(db.psycopg, "connect", fake_connect)

    conn = db.get_conn()
    assert conn == "connection"
    assert called["host"] == "db-host"
    assert str(called["port"]) == "6543"
    assert called["row_factory"] == db.dict_row


class QueryCursor:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = iter(responses)
        self._current: Any | None = None

    def __enter__(self) -> "QueryCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass

    def execute(self, sql: str, params: Any | None = None) -> None:
        try:
            self._current = next(self._responses)
        except StopIteration as exc:
            raise AssertionError("No more responses for execute") from exc

    def _next(self) -> Any:
        if self._current is None:
            raise AssertionError("fetch called without execute")
        value = self._current
        self._current = None
        return value

    def fetchone(self) -> Any:
        return self._next()

    def fetchall(self) -> list[Any]:
        result = self._next()
        return list(result)


class QueryConnection:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = responses

    def __enter__(self) -> "QueryConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass

    def cursor(self) -> QueryCursor:
        return QueryCursor(self._responses)


@pytest.mark.integration
def test_query_data_main_prints_json(monkeypatch, capsys):
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

    monkeypatch.setattr(db, "get_conn", lambda: QueryConnection(responses))

    runpy.run_path(Path("src/query_data.py"), run_name="__main__")
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["q1"] == 2
    assert data["q10"][0]["university"] == "Uni A"
