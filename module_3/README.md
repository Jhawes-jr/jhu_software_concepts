# GradCafe Analytics – Module 3

This assignment builds on Module 2’s GradCafe scraper. In Module 3 we:
- Load the scraped data into a PostgreSQL database.
- Write SQL queries to analyze it.
- Display results via a Flask web application (to be added later).
- Provide written reflections on the limitations of the dataset.

---

## Project Structure

db.py # Database connection logic
create_schema.sql # One-time schema definition for applicants table
load_data.py # Loads JSONL data into PostgreSQL
query_data.py # SQL queries for analysis
check_status.py # Sanity checks (distinct statuses, GPA/GRE ranges)
README.md # This document


---

## Implementation Notes

### Database Setup
- Installed PostgreSQL on Windows.
- Created a dedicated database (`gradcafe`).
- Defined a single table `applicants` via `create_schema.sql`.
- Chose `url` as the unique identifier (every record has a distinct GradCafe detail URL).
- Environment variables (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`) are used for credentials.

### Python Driver
- First attempts used **`psycopg2`**, but professor flagged it as not accpetable (much later in the week...)
- Updated all code to use **`psycopg` (psycopg3)** with `dict_row` for row results.

### Loading Data
- Implemented `load_data.py` to parse JSONL records.
- Issues:
  - **Too much defensive parsing at first** (aliases, upserts, constraints) made the code difficult to deal with and run consistently.  
    ➝ Simplified: directly parse floats/dates and insert.
  - **GPA constraints** originally blocked inserts when data was missing.  
    ➝ Dropped constraints and allow `NULL`, handle in queries later.
- Final behavior: accepts cleaned JSONL from Module 2 and inserts directly into the `applicants` table.

### Queries
- Wrote `query_data.py` to answer assignment questions.
- Problems:
  - Finding a "term" field on GradCafe resulted in the field being **always null** → had to derive Fall 2025 window differently.
  - Original approach used `date_added`, but many records had `NULL`.  
    ➝ Switched to parsing **dates embedded in the `status` field** (`Accepted on …`, `Rejected on …`, `Wait listed on …`).
  - Regex had to strip decision prefix and pull only the date.
- Key queries include:
  - Total Fall 2025 entries.
  - % international (not “American” or “Other”).
  - Average GPA, GRE Q/V/AW.
  - Avg GPA of American students (Fall 2025).
  - % acceptances among Fall 2025 entries.
  - Avg GPA among Fall 2025 acceptances.
  - JHU Masters in CS applications.
  - Georgetown PhD CS acceptances (Fall 2025).
  - Extras: #9 Average GPA breakown by American vs international, #10 Universities with highest acceptance rate.

### Status Field
- Distinct values discovered: `"Accepted on ..."`, `"Rejected on ..."`, `"Wait listed on ..."`.
- Originally used `ILIKE '%accept%'`, but realized status is **structured, not free text**.  
  ➝ Fixed by parsing prefix before the date.

### GRE Fields
- Initial scrapes returned `NULL` for GRE values.
- Cause: Didn't have enough time to ensure data quality before module 2 submission. Scraper only looked for labeled fields (“GRE General”, “GRE Verbal”, “Analytical Writing”), but many posts embed scores in free text.
- Fixed by adding a regex parser (`extract_gre`) to capture:
  - `Q 170 V 165 AW 4.5`
  - `(Q/V/W): 170/165/4.5`
  - `170Q/165V/4.5W`
- Sanity-checked with `check_status.py` to confirm ranges.

### Incremental Scraping
- Running for ~31,000 records takes 6 hours even with compute offloaded to GPU (much longer when only utilizing CPU for compute).
- Needed to **avoid full re-scrape**.
- Fix:
  - Added `--since YYYY-MM-DD` argument to scraper.
  - Created flat file `last_run.txt` that stores the last scraped “Added on” date.
  - On each run:
    - Reads cutoff date from `last_run.txt`.
    - Skips older records.
    - Appends new ones to `llm_extend_applicant_data.jsonl`.
    - Updates `last_run.txt` to the latest scraped date.
- This makes the “Pull Data” button feasible (only new data is ever scraped).

### Testing Issues and Fixes
- **Imports unresolved in VS Code:** caused by using Python 3.13, which wasn’t compatible with psycopg at the time.  
  ➝ Switched interpreter to Python 3.11, fixed squiggles.
- **Payload undefined in `load_data.py`:** solved by explicitly building payload dictionary before insert.
- **% signs in SQL (`ILIKE '%accept%'`):** early attempts double-escaped with `%%` → psycopg treated `%m` as a date token.  
  ➝ Fixed ultimately by removing `ILIKE '%accept%'` becasue status was structured with consistent formatting.
- **Null GPA/GRE values:** initially blocked inserts.  
  ➝ Removed constraints and let queries ignore `NULL`.

- **Flask Web App (Module 3 Part 3):**
  - Add “Pull Data” button → runs scraper and loader.
  - Add “Update Analysis” button → refreshes query results.
  - Prevent concurrent pulls with a simple lock file.
  - Display query results dynamically with CSS styling.

- **Error Handling:**
  - Scraper should log HTTP errors or malformed pages more gracefully.
  - Loader could log rejected inserts instead of skipping silently.

- **Data Quality:**
  - GRE regex could be expanded for edge cases (e.g., different AW notation).
  - May want to normalize program names further (e.g., “CompSci” vs “Computer Science”).

---

- **Usage:**
  - run app.py after dealing with dependencies/requirements
  - naviaget to website, click pull data, wait, message will apear with stats on pull (number scraped, total number of records in db, etc)
  - Click Update Analysis, message will appear confirming that analysis has been updated. Note: If number scraped = 0 then analysis won't change

