# Module 4 - Test Suite & Documentation

This module focused on rounding out the GradCafe analytics project with a
comprehensive pytest suite and developer documentation. The earlier modules
(ETL, queries, Flask UI) are treated as the system under test.

## Test Suite
- Added **11 dedicated test modules** under `tests/` covering Flask routes,
  button endpoints, busy-state gating, formatting, DB inserts/idempotency,
  analysis output, integration flows, helper utilities, and CLI/report scripts.
- Standardised pytest markers in `pytest.ini`:
  - `web`, `buttons`, `analysis`, `db`, `integration`.
- Introduced fixtures in `tests/conftest.py` to expose the Flask app and ensure
  the PostgreSQL schema exists for every run.
- Heavy use of `monkeypatch`, fake subprocesses, and in-memory database doubles
  so tests are fast and deterministic.
- Added coverage enforcement (`--cov=src --cov-fail-under=100`) with results
  recorded in `coverage_summary.txt`.
- GitHub Actions workflow (`.github/workflows/tests.yml`) runs the full suite on
  every push/PR using a Postgres service.

### Running the tests
```console
python -m pytest -m "web or buttons or analysis or db or integration"
```
Select smaller groups with markers, e.g. `-m web` or `-m "db and not integration"`.

## Documentation (Sphinx + Read the Docs)
- Created a Sphinx project in `module_4/source/` with the Read the Docs theme
  and autodoc configured to pull docstrings from:
  - `module_2.scrape`, `module_2.clean`
  - `src.load_data`, `src.query_data`, `src.app`
- Added narrative sections:
  - `overview.rst` - local setup, environment variables, ETL flow, how to run
    app/tests/docs.
  - `architecture.rst` - breakdown of UI/ETL/DB responsibilities.
  - `testing.rst` - markers, fixtures, coverage strategy.
  - `api_reference.rst` - autodoc API reference.
- `.readthedocs.yaml` at the repo root configures RTD to build from the same
  requirements; RTD automatically builds on push.
- Built HTML docs live at: https://module-4-pytest-and-sphinx.readthedocs.io/en/latest/index.html

### Build docs locally
```console
python -m sphinx -b html source build/html
```
Open `build/html/index.html` for the local preview.

## Status
- Test suite: **56 passing / 0 failing**, 100% coverage (see `coverage_summary.txt`).
- Documentation: published via Read the Docs and linked above.
