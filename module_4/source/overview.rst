Overview & Setup
================

This project pulls GradCafe admissions data, loads it into PostgreSQL, performs
analysis queries, and serves the results through a Flask dashboard. The
workflows from scraping through reporting are automated so the dashboard always
has fresh answers, while a comprehensive pytest suite keeps the code reliable.

Environment variables
---------------------
The application reads connection information from the environment. Either
provide a single ``DATABASE_URL`` or the individual PostgreSQL variables:

* ``DATABASE_URL`` - optional convenience URI used by :mod:`db`
* ``PGHOST`` - database host (default ``localhost``)
* ``PGPORT`` - port number (default ``5432``)
* ``PGDATABASE`` - database name (default ``gradcafe``)
* ``PGUSER`` - database user (default ``postgres``)
* ``PGPASSWORD`` - database password (empty by default)
* ``FLASK_SECRET_KEY`` - optional secret key for session messages in the web app

Local installation
------------------

.. code-block:: console

   cd jhu_software_concepts/module_4
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt

Database setup
--------------
1. Start PostgreSQL (locally or via Docker/cloud).
2. Create the ``gradcafe`` database and user if they do not already exist.
3. Run ``python src/create_schema.py`` to create the ``applicants`` table and
   indexes.

Running the ETL pipeline
------------------------
1. **Scrape new records** - ``python ..\module_2\scrape.py --since 2025-08-01``
   appends new results to ``llm_extend_applicant_data.jsonl``.
2. **Clean the JSON** - ``python ..\module_2\clean.py`` removes HTML noise and
   normalises the status/date fields.
3. **Load into PostgreSQL** - ``python src/load_data.py llm_extend_applicant_data.jsonl``
   inserts the cleaned records.

Running the Flask dashboard
---------------------------

.. code-block:: console

   .\.venv\Scripts\Activate.ps1
   set FLASK_APP=src.app
   flask run --port 8080

Then open ``http://127.0.0.1:8080`` and use the *Pull Data* and *Update
Analysis* buttons to refresh the metrics. Flash messages show scrape and insert
counts as well as any error conditions.

Running the automated tests
---------------------------

The entire suite is grouped under pytest markers so developers can slice the
runs:

.. code-block:: console

   python -m pytest -m "web or buttons or analysis or db or integration"

The command enforces 100 percent coverage via ``pytest-cov``. Individual groups
can be executed with for example ``-m web`` or ``-m db`` when iterating on a
feature.

Building the documentation locally
----------------------------------

.. code-block:: console

   .\.venv\Scripts\Activate.ps1
   python -m sphinx -b html source build/html

The generated HTML lives in ``build/html/index.html`` and is also published on
Read the Docs for sharing with the team.
