from __future__ import annotations

import json
import runpy
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

import load_data


@pytest.mark.db
def test_parse_float_handles_valid_and_invalid_values():
    assert load_data.parse_float("3.25") == pytest.approx(3.25)
    assert load_data.parse_float(None) is None
    assert load_data.parse_float("not-a-number") is None


@pytest.mark.db
def test_parse_date_recognizes_supported_formats():
    assert load_data.parse_date("2025-09-14") == date(2025, 9, 14)
    assert load_data.parse_date("09/14/2025") == date(2025, 9, 14)
    assert load_data.parse_date("Sep 14, 2025") == date(2025, 9, 14)
    assert load_data.parse_date("September 14, 2025") == date(2025, 9, 14)
    assert load_data.parse_date("14-Sep-2025") == date(2025, 9, 14)
    assert load_data.parse_date("bad input") is None
    assert load_data.parse_date("") is None


@pytest.mark.db
def test_parse_status_extracts_type_and_date():
    status, when = load_data.parse_status("Accepted on 01/15/2025")
    assert status == "Accepted"
    assert when == date(2025, 1, 15)

    status, when = load_data.parse_status("Pending soon")
    assert status is None
    assert when is None

    assert load_data.parse_status(None) == (None, None)


@pytest.mark.db
def test_iter_records_read_json_array(tmp_path):
    payload = [{"id": 1}, {"id": 2}]
    path = tmp_path / "records.json"
    path.write_text("\n  " + json.dumps(payload), encoding="utf-8")

    rows = list(load_data.iter_records(path))
    assert rows == payload


@pytest.mark.db
def test_iter_records_read_jsonl(tmp_path):
    payload = [{"id": 1}, {"id": 2}]
    path = tmp_path / "records.jsonl"
    path.write_text("\n".join(json.dumps(obj) for obj in payload), encoding="utf-8")

    rows = list(load_data.iter_records(path))
    assert rows == payload


class RecordingCursor:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass

    def execute(self, sql: str, params: dict[str, Any]) -> None:
        self.rows.append(params.copy())

    def fetchone(self):  # pragma: no cover
        return None

    def fetchall(self):  # pragma: no cover
        return []


class RecordingConnection:
    def __init__(self, cursor: RecordingCursor) -> None:
        self.cursor_obj = cursor

    def __enter__(self) -> "RecordingConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass

    def cursor(self) -> RecordingCursor:
        return self.cursor_obj


@pytest.mark.db
def test_main_inserts_records_respects_limit(monkeypatch):
    cursor = RecordingCursor()
    conn = RecordingConnection(cursor)
    monkeypatch.setattr(load_data, "get_conn", lambda: conn)

    sample = [
        {
            "program": "Program A",
            "comments": "Comment",
            "date_added": "2025-01-10",
            "url": "https://example.com/1",
            "status": "Accepted on 01/11/2025",
            "term": "Fall 2025",
            "US/International": "American",
            "GPA": "3.90",
            "GRE": "167",
            "GRE V": "159",
            "GRE AW": "4.5",
            "Degree": "MS",
            "llm-generated-program": "Computer Science",
            "llm-generated-university": "Test U",
        },
        {
            "program": "Program B",
            "comments": "Comment",
            "date_added": "2025-02-10",
            "url": "https://example.com/2",
            "status": "Rejected on 02/12/2025",
            "term": "Fall 2025",
            "US/International": "International",
            "GPA": "3.50",
            "GRE": "160",
            "GRE V": "155",
            "GRE AW": "4.0",
            "Degree": "MS",
            "llm-generated-program": "Computer Science",
            "llm-generated-university": "Test U",
        },
    ]
    monkeypatch.setattr(load_data, "iter_records", lambda path: list(sample))

    captured: list[str] = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: captured.append(" ".join(str(a) for a in args)))

    load_data.main("ignored", limit=1)

    assert len(cursor.rows) == 1
    row = cursor.rows[0]
    assert row["url"] == "https://example.com/1"
    assert row["gpa"] == pytest.approx(3.9)
    assert str(row["date_added"]) == "2025-01-10"
    assert captured[-1] == "Inserted rows: 1"


@pytest.mark.db
def test_load_data_script_usage(monkeypatch, capsys):
    import types

    fake_db = types.SimpleNamespace(get_conn=lambda: None)
    monkeypatch.setitem(sys.modules, "db", fake_db)
    monkeypatch.setattr(sys, "argv", ["load_data.py"])

    def fake_exit(code=0):
        raise SystemExit(code)

    monkeypatch.setattr(sys, "exit", fake_exit)

    with pytest.raises(SystemExit):
        runpy.run_path(Path("src/load_data.py"), run_name="__main__")

    out = capsys.readouterr().out
    assert "Usage:" in out


@pytest.mark.db
def test_load_data_script_invokes_main(monkeypatch, tmp_path):
    import types

    payload = {
        "program": "Program",
        "comments": "",
        "date_added": "2025-01-02",
        "url": "https://example.com/1",
        "status": "Accepted on 01/03/2025",
        "term": "Fall 2025",
        "US/International": "American",
        "GPA": "3.75",
        "GRE": "165",
        "GRE V": "158",
        "GRE AW": "5.0",
        "Degree": "MS",
        "llm-generated-program": "CS",
        "llm-generated-university": "Test U",
    }
    sample_path = tmp_path / "input.jsonl"
    sample_path.write_text(json.dumps(payload), encoding="utf-8")

    cursor = RecordingCursor()
    conn = RecordingConnection(cursor)

    fake_db = types.SimpleNamespace(get_conn=lambda: conn)
    monkeypatch.setitem(sys.modules, "db", fake_db)
    monkeypatch.setattr(sys, "argv", ["load_data.py", str(sample_path), "1"])

    runpy.run_path(Path("src/load_data.py"), run_name="__main__")
    assert cursor.rows and cursor.rows[0]["url"] == "https://example.com/1"
