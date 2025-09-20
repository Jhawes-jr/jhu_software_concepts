# GradCafe Analytics – Module 4

This module ties together the GradCafe scraper (Module 2) and analytics queries
(Module 3) into a cohesive Flask dashboard backed by PostgreSQL.

## Documentation
The full developer guide (setup, architecture, API reference, testing) is
published on Read the Docs:

- https://pytest-and-sphinx.readthedocs.io/en/latest/

## Project Structure
- `src/app.py` – Flask UI and route handlers.
- `src/load_data.py` – Loads JSON data into PostgreSQL using psycopg.
- `src/query_data.py` – Analysis queries surfaced in the dashboard.
- `src/date_added_report.py`, `src/check_status.py` – Data quality checks.
- `module_2/scrape.py` – GradCafe scraper feeding the pipeline.
- `module_2/clean.py` – Normalises scraped JSON data.
- `tests/` – Pytest suite covering routes, ETL, DB, and integration behaviour.

## Environment variables
Provide either `DATABASE_URL` or the individual PostgreSQL variables:
`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD`.  The Flask secrets
use `FLASK_SECRET_KEY`.

## Running locally
```console
cd jhu_software_concepts/module_4
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python src/create_schema.py   # creates the applicants table
python src/app.py             # launch the dashboard at http://127.0.0.1:8080
```

Use the *Pull Data* button to run the scraper/loader and *Update Analysis* to
refresh the metrics.  Flash messages show scrape statistics or errors.

## Automated tests
All tests use pytest markers and enforce 100% coverage:
```console
python -m pytest -m "web or buttons or analysis or db or integration"
```
Coverage output is stored in `coverage_summary.txt` and checked in CI.

## Documentation build
```console
.\.venv\Scripts\Activate.ps1
python -m sphinx -b html source build/html
```
The docs above are published from the same source via Read the Docs.
