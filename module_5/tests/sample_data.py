"""Shared sample data used across tests to avoid duplication."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Iterable

STAT_RESPONSES: list[Any] = [
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

APPLICANT_RECORDS: list[dict[str, Any]] = [
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
]


def iter_records_with_new_entry() -> Iterable[dict[str, Any]]:
    """Return sample records plus an additional entry used in idempotency tests."""

    extended = list(APPLICANT_RECORDS)
    extended.append(
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
        }
    )
    return extended


def configure_pg_env(monkeypatch) -> None:
    """Populate environment variables with deterministic Postgres settings."""

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PGHOST", "db-host")
    monkeypatch.setenv("PGPORT", "6543")
    monkeypatch.setenv("PGDATABASE", "dbname")
    monkeypatch.setenv("PGUSER", "dbuser")
    monkeypatch.setenv("PGPASSWORD", "secret")



def integration_stats() -> dict[str, Any]:
    """Return stats resembling the integration fixture expectations."""

    return {
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
        "q10": [
            SimpleNamespace(university="Test U", acceptance_rate_pct=66.6667, n=30)
        ],
    }


__all__ = [
    "APPLICANT_RECORDS",
    "STAT_RESPONSES",
    "configure_pg_env",
    "integration_stats",
    "iter_records_with_new_entry",
]
