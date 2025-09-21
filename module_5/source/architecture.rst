System Architecture
===================

The solution is organised into three cooperating layers.  Each layer is kept in
its own module so that tests and documentation can focus on a single
responsibility.

Web application (presentation)
------------------------------
* :mod:`app` exposes the Flask ``app`` factory, Jinja templates, and UI logic.
* Buttons trigger background tasks via HTTP POSTs and display status messages.
* Templates in ``src/templates`` and CSS in ``src/static`` provide the visual
  layer.

ETL & data preparation
----------------------
* :mod:`scrape` (Module 2) collects the latest GradCafe survey entries and keeps
  track of the last successful run via ``last_run.txt``.
* :mod:`clean` normalises the scraped JSON (HTML sanitising, status parsing,
  GRE extraction, etc.).
* :mod:`load_data` performs inserts into PostgreSQL and reports the number of
  newly inserted rows.
* :mod:`check_status` and :mod:`date_added_report` provide sanity checks on the
  incoming data (GPA/GRE ranges, date distributions).

Database & analytics
--------------------
* PostgreSQL hosts the ``applicants`` schema created by :mod:`create_schema`.
* :mod:`db` encapsulates connection handling using ``psycopg``.
* :mod:`query_data` contains the analytics queries used by the dashboard, such
  as counts, acceptance rates, and GPA summaries.

Request flow
------------
1. ``/pull-data`` locks the pipeline, runs :mod:`scrape` and :mod:`load_data`,
   then flashes a summary of the scrape/insert counts.
2. ``/update-analysis`` runs the SQL in :mod:`query_data` and updates the
   cached analysis timestamp.
3. ``/analysis`` renders the latest metrics along with run history and control
   state.

The modular design makes it easy to run the scraper/loader standalone (e.g. for
scheduled jobs) while still maintaining an interactive dashboard for analysts.
