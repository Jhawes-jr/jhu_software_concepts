# module_3/create_schema.py
''' Create the applicants table schema in the database '''

from db import get_conn

DDL = """ -- 1) Main applicants table

CREATE TABLE IF NOT EXISTS applicants (
  p_id SERIAL PRIMARY KEY,

  -- Raw / scraped fields 
  program                   TEXT,      -- original scraped program text
  comments                  TEXT,
  date_added                DATE,
  url                       TEXT,
  status                    TEXT,      -- e.g., 'Accepted', 'Rejected', 'Waitlisted', etc.
  term                      TEXT,      -- e.g., 'Fall 2025'
  us_or_international       TEXT,      -- e.g., 'American', 'International', 'Other'
  gpa                       REAL,      -- allow NULL; Postgres AVG ignores NULLs
  gre                       REAL,      -- GRE Quantitative (per your column label)
  gre_v                     REAL,      -- GRE Verbal
  gre_aw                    REAL,      -- GRE Analytical Writing
  degree                    TEXT,      -- e.g., 'MS', 'M.S.', 'Master', 'PhD', 'Ph.D.'
  llm_generated_program     TEXT,      -- normalized by your Module 2 LLM pass
  llm_generated_university  TEXT,      -- normalized by your Module 2 LLM pass

  -- Contraints for NULL values and ranges
  CONSTRAINT gpa_range CHECK (gpa IS NULL OR (gpa >= 0 AND gpa <= 4.3)),
  CONSTRAINT gre_q_range CHECK (gre IS NULL OR (gre >= 130 AND gre <= 170)),
  CONSTRAINT gre_v_range CHECK (gre_v IS NULL OR (gre_v >= 130 AND gre_v <= 170)),
  CONSTRAINT gre_aw_range CHECK (gre_aw IS NULL OR (gre_aw >= 0 AND gre_aw <= 6)),

  -- Uniqueness constraint to prevent duplicate entries
  CONSTRAINT applicants_uniq UNIQUE (program, url, date_added)
);

-- 2) Indexes to speed up common queries
CREATE INDEX IF NOT EXISTS idx_applicants_term ON applicants (term);
CREATE INDEX IF NOT EXISTS idx_applicants_status ON applicants (status);
CREATE INDEX IF NOT EXISTS idx_applicants_country ON applicants (us_or_international);
CREATE INDEX IF NOT EXISTS idx_applicants_university ON applicants (llm_generated_university);
CREATE INDEX IF NOT EXISTS idx_applicants_program ON applicants (llm_generated_program);

-- Case-insensitive indexes for text fields
CREATE INDEX IF NOT EXISTS idx_applicants_term_lower
  ON applicants (LOWER(term));
CREATE INDEX IF NOT EXISTS idx_applicants_status_lower
  ON applicants (LOWER(status));
CREATE INDEX IF NOT EXISTS idx_applicants_university_lower
  ON applicants (LOWER(llm_generated_university));
CREATE INDEX IF NOT EXISTS idx_applicants_program_lower
  ON applicants (LOWER(llm_generated_program));
"""

if __name__ == "__main__":
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(DDL)
    print("Schema created/verified.")
