"""Load applicant data from JSON sources into the database."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

from db import get_conn

DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",  # 2025-09-14
    "%m/%d/%Y",  # 09/14/2025
    "%b %d, %Y",  # Sep 14, 2025
    "%B %d, %Y",  # September 14, 2025
    "%d-%b-%Y",  # 14-Sep-2025
)

STATUS_PATTERN = re.compile(r"^(?P<status>[^\d]+)\s+on\s+(?P<date>\d{2}/\d{2}/\d{4})")


def parse_float(value: Any) -> float | None:
    """Convert value to float when possible, otherwise return None."""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_date(value: Any) -> date | None:
    """Parse *value* into a date value, returning None when unsupported."""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_status(raw_status: Any) -> tuple[str | None, date | None]:
    """Split a raw status string into (status, date) when possible."""

    if raw_status is None:
        return None, None
    match = STATUS_PATTERN.match(str(raw_status).strip())
    if not match:
        return None, None
    status_date = parse_date(match.group("date"))
    return match.group("status").strip(), status_date


def iter_records(source_path: str | Path) -> Iterator[dict[str, Any]]:
    """Yield JSON records from *source_path*, supporting JSONL and JSON arrays."""

    path = Path(source_path)
    with path.open(encoding="utf-8") as handle:
        first_char = handle.read(1)
        while first_char and first_char.isspace():
            first_char = handle.read(1)
        handle.seek(0)
        if first_char == "[":
            yield from json.load(handle)
        else:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)


INSERT_SQL = """
INSERT INTO applicants
(program, comments, date_added, url, status, term, us_or_international,
 gpa, gre, gre_v, gre_aw, degree, llm_generated_program, llm_generated_university)
VALUES (%(program)s, %(comments)s, %(date_added)s, %(url)s, %(status)s, %(term)s,
        %(us_or_international)s, %(gpa)s, %(gre)s, %(gre_v)s, %(gre_aw)s, %(degree)s,
        %(llm_generated_program)s, %(llm_generated_university)s)
ON CONFLICT (url) DO NOTHING;
"""


def build_payload(record: dict[str, Any]) -> dict[str, Any]:
    """Normalise a raw applicant record for database insertion."""

    return {
        "program": record.get("program"),
        "comments": record.get("comments"),
        "date_added": parse_date(record.get("date_added")),
        "url": record.get("url"),
        "status": record.get("status"),
        "term": record.get("term"),
        "us_or_international": record.get("US/International"),
        "gpa": parse_float(record.get("GPA")),
        "gre": parse_float(record.get("GRE")),
        "gre_v": parse_float(record.get("GRE V")),
        "gre_aw": parse_float(record.get("GRE AW")),
        "degree": record.get("Degree"),
        "llm_generated_program": record.get("llm-generated-program"),
        "llm_generated_university": record.get("llm-generated-university"),
    }


def main(source_path: str | Path, limit: int | None = None) -> int:
    """Load applicant data from *source_path* into the database and return rows inserted."""

    inserted = 0
    with get_conn() as conn, conn.cursor() as cursor:
        for record in iter_records(source_path):
            payload = build_payload(record)
            cursor.execute(INSERT_SQL, payload)
            inserted += 1
            if limit is not None and inserted >= limit:
                break
    print(f"Inserted rows: {inserted}")
    return inserted


def _parse_limit(raw_limit: str | None) -> int | None:
    """Convert the CLI limit argument to an int when provided."""

    if raw_limit is None:
        return None
    try:
        limit_value = int(raw_limit)
    except ValueError as exc:
        raise ValueError("limit must be an integer") from exc
    if limit_value < 0:
        raise ValueError("limit must be non-negative")
    return limit_value


def _cli(argv: Sequence[str]) -> int:
    """Command-line entrypoint returning a process exit status."""

    if len(argv) not in (1, 2):
        print("Usage: python module_3/load_data.py <path.jsonl|.json> [limit]")
        return 1

    source_path = argv[0]
    try:
        limit = _parse_limit(argv[1] if len(argv) == 2 else None)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    try:
        main(source_path, limit)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
