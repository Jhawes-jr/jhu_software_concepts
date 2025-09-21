Testing Guide
=============

The project relies on pytest for exhaustive coverage of scraping, loading,
analysis, and the Flask interface.  Tests live under ``module_4/tests``.

Markers and selectors
---------------------
Markers are declared in ``pytest.ini`` and allow focused runs:

* ``web`` – smoke tests for the Flask routes and rendered HTML.
* ``buttons`` – behaviour of the Pull Data / Update Analysis endpoints, busy
  gating, and error paths.
* ``analysis`` – formatting assertions for the analysis page (labels,
  percentage rounding, etc.).
* ``db`` – database interactions covering ETL inserts, idempotency, and
  reporting scripts.
* ``integration`` – end-to-end pulls (fake scraper), updates, and rendered
  dashboard checks.

Run the full suite (with coverage enforcement) via::

   python -m pytest -m "web or buttons or analysis or db or integration"

Examples of targeted runs::

   python -m pytest -m web
   python -m pytest -m "db and not integration"

Fixtures
--------
* ``ensure_database_schema`` (session autouse) executes ``create_schema.DDL``
  to ensure the ``applicants`` table exists before any test touches the DB.
* ``test_app`` exposes the Flask application configured in testing mode.
* ``client`` returns a ``FlaskClient`` bound to ``test_app`` for exercising
  routes.
* Individual modules (``tests/test_db_insert.py``, etc.) define helper fixtures
  to fake subprocesses, database connections, and Sphinx outputs.

Coverage and reporting
----------------------
``pytest-cov`` is enabled in ``pytest.ini`` and requires 100 % coverage of
``module_4/src``.  The latest run is stored in ``coverage_summary.txt`` and the
terminal output appears in CI and Read the Docs builds.  Custom fixtures also
create deterministic fake data so integration tests remain fast and repeatable.
