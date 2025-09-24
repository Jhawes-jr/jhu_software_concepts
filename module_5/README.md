# Module 5 - Security Tooling & Dependency Hygiene

This module extends the GradCafe analytics app with a focus on static analysis, database hardening, dependency visibility, and supply-chain scanning. The deliverables build confidence that the Flask UI and reporting stack can be shipped safely and maintained predictably.

## Highlights
- Enforced lint quality gates with `pylint` and a project-specific `.pylintrc`.
- Hardened database access patterns to prevent SQL injection by using parameterised queries and the `psycopg.sql` builder API.
- Generated Python dependency graphs with `pydeps` + Graphviz to make refactoring paths visible.
- Standardised virtual environment workflows and dependency pinning in `requirements.txt`.
- Ran Snyk tests against the Python dependency tree for CVE coverage.

## Environment & Dependencies
1. Create/refresh the module-specific virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
2. Upgrade pip and install the locked dependencies using the interpreter for this venv:
   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

## Linting with Pylint
- The `.pylintrc` in this module encodes naming conventions and selective suppressions for the venv.
- Run lint:
  ```powershell
  python -m pylint
  ```
- Failures surface quickly in CI, so keeping the lint score clean prevents regressions.

## SQL Injection Defenses
- All dynamic SQL is composed with `psycopg.sql.Identifier`, `SQL`, and `Placeholder` objects instead of string interpolation.
- Example: `src/query_data.py` builds the reporting CTE and filters using placeholders populated by dictionaries, so user input never reaches the query string unsanitised.
- The loader (`src/load_data.py`) also uses `cursor.execute(INSERT_SQL, payload)` with psycopg parameter binding when inserting scraped records.

## Dependency Graphs with Pydeps + Graphviz
- Pydeps visualises import relationships so architectural drift is easy to spot.
- Ensure Graphviz is installed on your PATH before generating diagrams.
- Typical workflow:
  ```powershell
  python -m pydeps app.py
  ```
  The command writes a DOT graph and renders it in the browser. Modify command with -o to output result to a specific location.

## Maintaining Requirements
- Dependency versions are pinned with upper/lower bounds in `requirements.txt` to avoid surprise upgrades.
- When adding a new package, update the file and reinstall via `python -m pip install -r requirements.txt` to enforce the lock.
- Regenerate the dependency graph and rerun lint/tests after any change to detect unexpected coupling.

## Snyk Vulnerability Scanning
1. Authenticate once: `snyk auth` (requires a Snyk account/token).
2. Scan the current dependency set:
   ```powershell
   snyk test
   ```
3. Address flagged CVEs, if any, by bumping packages (while staying within allowed version ranges) and re-running the scan.

## Potential Future Improvements
- Combine linting (`pylint`), testing (`pytest`), dependency graphs, and `snyk test` inside your CI pipeline for repeatability.
- Periodically review SQL query construction when new routes or analytics features are added to ensure parameterised patterns remain intact.
