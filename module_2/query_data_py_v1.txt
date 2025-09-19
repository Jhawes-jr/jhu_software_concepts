# module_3/query_data.py

from db import get_conn

# Fall 2025 window (explicit SQL literals used below)
FALL_START_SQL = "DATE '2025-01-01'"
FALL_END_SQL   = "DATE '2025-08-31'"

def one(cur):
    r = cur.fetchone()
    if r is None:
        return None
    # works with psycopg3 dict_row
    return list(r.values())[0]

# Parse status_type (prefix up to first digit) and status_date from `status`
# Include ALL statuses; let each query filter as needed.
DECISION_CTE = """
WITH decisions AS (
  SELECT
    p_id,
    status,
    btrim((regexp_match(status, '^([^0-9]+)'))[1]) AS status_type,
    us_or_international,
    gpa, gre, gre_v, gre_aw,
    llm_generated_university,
    llm_generated_program,
    degree,
    COALESCE(
      to_date((regexp_match(status, '([0-9]{4}-[0-9]{2}-[0-9]{2})'))[1], 'YYYY-MM-DD'),
      to_date(
        (regexp_match(status, '([0-9]{1,2})[/-]([0-9]{1,2})[/-]([0-9]{4})'))[1] || '/' ||
        (regexp_match(status, '([0-9]{1,2})[/-]([0-9]{1,2})[/-]([0-9]{4})'))[2] || '/' ||
        (regexp_match(status, '([0-9]{1,2})[/-]([0-9]{1,2})[/-]([0-9]{4})'))[3],
        'DD/MM/YYYY'
      )
    ) AS status_date
  FROM applicants
  WHERE status IS NOT NULL
)
"""

def main():
    with get_conn() as conn, conn.cursor() as cur:

        # 1) How many entries in Fall 2025 (by parsed status_date)?
        cur.execute(
            DECISION_CTE + f"""
            SELECT COUNT(*)
            FROM decisions
            WHERE status_date BETWEEN {FALL_START_SQL} AND {FALL_END_SQL};
            """
        )
        q1 = one(cur)
        total_fall = q1 or 1  # avoid div/0 later

        # Total (all rows) for % calcs used in Q2
        cur.execute("SELECT COUNT(*) FROM applicants;")
        total_all = one(cur) or 1

        # 2) % International (not American or Other) across ALL rows
        cur.execute("""
            SELECT COUNT(*)
            FROM applicants
            WHERE COALESCE(us_or_international,'') NOT ILIKE 'American'
              AND COALESCE(us_or_international,'') NOT ILIKE 'Other';
        """)
        international = one(cur) or 0
        q2 = round(international * 100.0 / total_all, 2)

        # 3) Averages (all rows) – NULLs ignored by AVG
        cur.execute("""
            SELECT
              ROUND(AVG(gpa)::numeric, 2)    AS avg_gpa,
              ROUND(AVG(gre)::numeric, 2)    AS avg_gre_q,
              ROUND(AVG(gre_v)::numeric, 2)  AS avg_gre_v,
              ROUND(AVG(gre_aw)::numeric, 2) AS avg_gre_aw
            FROM applicants;
        """)
        q3 = cur.fetchone()

        # 4) Avg GPA of American students in Fall 2025 (any status)
        cur.execute(
            DECISION_CTE + f"""
            SELECT ROUND(AVG(gpa)::numeric, 2)
            FROM decisions
            WHERE status_date BETWEEN {FALL_START_SQL} AND {FALL_END_SQL}
              AND us_or_international ILIKE 'American';
            """
        )
        q4 = one(cur)

        # 5) % of Fall 2025 entries that are Acceptances
        # exact match on status_type avoids '%' usage
        cur.execute(
            DECISION_CTE + f"""
            SELECT COUNT(*)
            FROM decisions
            WHERE status_date BETWEEN {FALL_START_SQL} AND {FALL_END_SQL}
              AND status_type = 'Accepted on';
            """
        )
        accepts_fall = one(cur) or 0
        q5 = round(accepts_fall * 100.0 / total_fall, 2)

        # 6) Avg GPA of Fall 2025 Acceptances
        cur.execute(
            DECISION_CTE + f"""
            SELECT ROUND(AVG(gpa)::numeric, 2)
            FROM decisions
            WHERE status_date BETWEEN {FALL_START_SQL} AND {FALL_END_SQL}
              AND status_type = 'Accepted on';
            """
        )
        q6 = one(cur)

        # 7) How many applied to JHU for a masters in Computer Science? (overall)
        # Avoid '%' by using POSITION(.. IN LOWER(col)) > 0
        cur.execute("""
            SELECT COUNT(*)
            FROM applicants
            WHERE POSITION('johns hopkins' IN LOWER(COALESCE(llm_generated_university, ''))) > 0
              AND (
                    POSITION('master' IN LOWER(COALESCE(degree, ''))) > 0 OR
                    POSITION('ms'     IN LOWER(COALESCE(degree, ''))) > 0 OR
                    POSITION('m.s'    IN LOWER(COALESCE(degree, ''))) > 0
                  )
              AND POSITION('computer science' IN LOWER(COALESCE(llm_generated_program, ''))) > 0;
        """)
        q7 = one(cur)

        # 8) Fall 2025 acceptances to Georgetown for a PhD in CS (parsed status_date)
        cur.execute(
            DECISION_CTE + f"""
            SELECT COUNT(*)
            FROM decisions
            WHERE status_date BETWEEN {FALL_START_SQL} AND {FALL_END_SQL}
              AND status_type = 'Accepted on'
              AND POSITION('georgetown' IN LOWER(COALESCE(llm_generated_university, ''))) > 0
              AND (
                    POSITION('phd'   IN LOWER(COALESCE(degree, ''))) > 0 OR
                    POSITION('ph.d'  IN LOWER(COALESCE(degree, ''))) > 0
                  )
              AND POSITION('computer science' IN LOWER(COALESCE(llm_generated_program, ''))) > 0;
            """
        )
        q8 = one(cur)

        # ---- extras ----

        # Extra A) GRE Q among Acceptances in Fall 2025 (American vs International)
        cur.execute(
            DECISION_CTE + f"""
            SELECT
              CASE WHEN us_or_international ILIKE 'American' THEN 'American' ELSE 'International' END AS group_label,
              ROUND(AVG(gre)::numeric, 2) AS avg_gre_q
            FROM decisions
            WHERE status_date BETWEEN {FALL_START_SQL} AND {FALL_END_SQL}
              AND status_type = 'Accepted on'
            GROUP BY 1
            ORDER BY 1;
            """
        )
        extraA = cur.fetchall()

        # Extra B) Top 10 universities by CS Acceptances in Fall 2025
        cur.execute(
            DECISION_CTE + f"""
            SELECT llm_generated_university AS university, COUNT(*) AS c
            FROM decisions
            WHERE status_date BETWEEN {FALL_START_SQL} AND {FALL_END_SQL}
              AND status_type = 'Accepted on'
              AND POSITION('computer science' IN LOWER(COALESCE(llm_generated_program, ''))) > 0
            GROUP BY 1
            ORDER BY c DESC NULLS LAST
            LIMIT 10;
            """
        )
        extraB = cur.fetchall()

    # ---- print nicely ----
    print(f"1) Fall 2025 entries: {q1}")
    print(f"2) % International (not American/Other): {q2}%")
    print(f"3) Averages (all rows) — GPA: {q3['avg_gpa']}, GRE Q: {q3['avg_gre_q']}, GRE V: {q3['avg_gre_v']}, GRE AW: {q3['avg_gre_aw']}")
    print(f"4) Avg GPA (American, Fall 2025): {q4}")
    print(f"5) % Acceptances (Fall 2025): {q5}%")
    print(f"6) Avg GPA among Acceptances (Fall 2025): {q6}")
    print(f"7) JHU Masters in CS entries: {q7}")
    print(f"8) 2025 Georgetown PhD CS Acceptances: {q8}")

    print("\nExtra A) GRE Q among Acceptances (Fall 2025):")
    for r in extraA:
        print(f"   - {r['group_label']}: {r['avg_gre_q']}")

    print("\nExtra B) Top 10 Universities by CS Acceptances (Fall 2025):")
    for r in extraB:
        print(f"   - {r['university'] or 'Unknown'} — {r['c']}")

if __name__ == "__main__":
    main()
