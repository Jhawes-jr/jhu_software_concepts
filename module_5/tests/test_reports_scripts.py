'''Unit and integration tests for report scripts and db module.'''

from __future__ import annotations

import csv
import json
import runpy
import sys
from pathlib import Path
from typing import Callable
import types
import pytest

from tests._app_import import import_app_module
from tests.fakes import QueryConnection, ScriptConnection
from tests.sample_data import STAT_RESPONSES, configure_pg_env
check_status = import_app_module("check_status")
count_rows = import_app_module("count_rows")
date_added_report = import_app_module("date_added_report")
db = import_app_module("db")
query_data = import_app_module("query_data")


def _capture_lines(buffer: list[str]) -> Callable[..., None]:
    """Return a function that records print output into ``buffer``."""

    def record(*args, **_kwargs) -> None:
        buffer.append(" ".join(str(arg) for arg in args))

    return record

@pytest.mark.db
def test_check_status_main(monkeypatch):
    '''Test check_status.main with scripted DB responses.'''
    connections = [
        ScriptConnection(
            [[{"status": "Accepted on 01/01/2025"}, {"status": "Rejected on 02/02/2025"}]]
        ),
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
    monkeypatch.setattr("builtins.print", _capture_lines(captured))

    check_status.main()

    joined = "\n".join(captured)
    assert "Distinct prefixes" in joined
    assert "Accepted" in joined
    assert "GPA" in joined


@pytest.mark.db
def test_check_status_script_entry(monkeypatch, capsys):
    '''Running check_status.py as a script should print results.'''
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

    fake_db = types.SimpleNamespace(get_conn=fake_get_conn)
    monkeypatch.setitem(sys.modules, "db", fake_db)

    runpy.run_path(Path("src/check_status.py"), run_name="__main__")
    out = capsys.readouterr().out
    assert "Distinct prefixes" in out


@pytest.mark.db
def test_count_rows_main(monkeypatch):
    '''Test count_rows.main with scripted DB response.'''
    conn = ScriptConnection([{ "total": 12 }])
    monkeypatch.setattr(count_rows, "get_conn", lambda: conn)

    captured: list[str] = []
    monkeypatch.setattr("builtins.print", _capture_lines(captured))

    count_rows.main()
    assert captured[-1] == "Total rows in applicants: 12"


@pytest.mark.db
def test_count_rows_script_entry(monkeypatch, capsys):
    '''Running count_rows.py as a script should print total rows.'''
    fake_db = types.SimpleNamespace(get_conn=lambda: ScriptConnection([{ "total": 7 }]))
    monkeypatch.setitem(sys.modules, "db", fake_db)

    runpy.run_path(Path("src/count_rows.py"), run_name="__main__")
    out = capsys.readouterr().out
    assert "Total rows in applicants: 7" in out


@pytest.mark.db
def test_create_schema_script_entry(monkeypatch, capsys):
    '''Running create_schema.py as a script should create/verify schema and print result.'''

    executed: list[str] = []

    class Cursor:
        '''A dummy cursor that records executed SQL.'''
        def __enter__(self) -> "Cursor":
            return self
        def __exit__(self, exc_type, exc, tb) -> None:
            pass
        def execute(self, sql: str) -> None:
            '''Execute a SQL statement.'''
            executed.append(sql)

    class Conn:
        '''A dummy connection that can be used as a context manager.'''
        def __enter__(self) -> "Conn":
            return self
        def __exit__(self, exc_type, exc, tb) -> None:
            pass
        def cursor(self) -> Cursor:
            '''Return a dummy cursor.'''
            return Cursor()

    def build_conn() -> Conn:
        return Conn()

    fake_db = types.SimpleNamespace(get_conn=build_conn)
    monkeypatch.setitem(sys.modules, "db", fake_db)

    runpy.run_path(Path("src/create_schema.py"), run_name="__main__")
    out = capsys.readouterr().out
    assert "Schema created/verified." in out
    assert executed and "CREATE TABLE" in executed[0]


@pytest.mark.db
def test_date_added_report_main(monkeypatch, tmp_path):
    '''Test date_added_report.main with scripted DB responses.'''
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

    monkeypatch.setattr(
        date_added_report,
        "get_conn",
        lambda: ScriptConnection(responses),
    )
    monkeypatch.setattr(date_added_report, "Path", lambda _: tmp_path / "dummy.py")

    captured: list[str] = []
    monkeypatch.setattr("builtins.print", _capture_lines(captured))

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
    '''Running date_added_report.py as a script should print results and write CSV.'''
    responses = [
        {"total": 0, "with_date": 0, "null_date": 0},
        {"min_date": None, "max_date": None},
        [],
        [],
    ]

    fake_db = types.SimpleNamespace(get_conn=lambda: ScriptConnection(responses))
    monkeypatch.setitem(sys.modules, "db", fake_db)
    monkeypatch.setattr(date_added_report, "Path", lambda _: tmp_path / "dummy.py")

    runpy.run_path(Path("src/date_added_report.py"), run_name="__main__")
    out = capsys.readouterr().out
    assert "Wrote per-date counts" in out


@pytest.mark.db
def test_db_get_conn_uses_database_url(monkeypatch):
    '''If DATABASE_URL is set, get_conn should use it.'''
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
    '''If DATABASE_URL is not set, get_conn should build connection parameters'''
    configure_pg_env(monkeypatch)

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
@pytest.mark.integration
def test_query_data_main_prints_json(monkeypatch, capsys):
    '''Test query_data.main with scripted DB responses.'''
    monkeypatch.setattr(db, "get_conn", lambda: QueryConnection(STAT_RESPONSES))

    runpy.run_path(Path("src/query_data.py"), run_name="__main__")
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["q1"] == 2
    assert data["q10"][0]["university"] == "Uni A"
