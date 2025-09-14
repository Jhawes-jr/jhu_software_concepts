# module_3/query_data.py
from datetime import date
from db import get_conn

START = date(2025, 1, 1)
END   = date(2025, 8, 31)

# Variant lists for exact matching (all lowercase)
JHU_UNI_VARIANTS = [
    "johns hopkins",
    "johns hopkins university",
    "jhu",
]
GEORGETOWN_UNI_VARIANTS = [
    "georgetown",
    "georgetown university",
]
CS_PROGRAM_VARIANTS = [
    "computer science",
    "cs",
    "comp sci",
    "mse in computer science",
    "ms in computer science",
]
MS_DEGREE_VARIANTS = [
    "ms",
    "m.s.",
    "masters",
    "master",
    "master of science",
    "mse",
]
PHD_DEGREE_VARIANTS = [
    "phd",
    "ph.d.",
    "doctor of philosophy",
]

def _one(cur):
    r = cur.fetchone()
    return None if r is None else list(r.values())[0]

def _row(cur):
    r = cur.fetchone()
    return None if r is None else dict(r)

def compute_stats():
    """
    Returns: dict with q1..q8
      q1: count Fall 2025
      q2: % International (not 'American'/'Other') within Fall 2025 (float 0..100)
      q3: dict {avg_gpa, avg_gre_q, avg_gre_v, avg_gre_aw} over ALL data
      q4: avg GPA of American students in Fall 2025
      q5: % Acceptances in Fall 2025
      q6: avg GPA among Fall 2025 acceptances
      q7: count JHU Masters in CS (exact-variant lists)
      q8: count Georgetown PhD CS acceptances (Fall 2025; exact-variant lists)
    """
    with get_conn() as conn, conn.cursor() as cur:
        decision_cte = r"""
        WITH parsed AS (
          SELECT
            a.*,
            regexp_match(a.status, '(\d{4}-\d{2}-\d{2})')      AS iso_m,
            regexp_match(a.status, '(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})') AS slash_m
          FROM applicants a
        ),
        sp AS (
          SELECT
            p.url,
            p.program,
            p.gpa, p.gre, p.gre_v, p.gre_aw,
            p.degree,
            p.us_or_international,
            p.llm_generated_university,
            p.llm_generated_program,

            -- exact status type like 'Accepted on', 'Rejected on', etc. (strip trailing date/time)
            trim(regexp_replace(p.status, '\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}.*$', '')) AS status_type_parsed,

            -- Safely parse date:
            --  1) ISO  YYYY-MM-DD
            --  2) Validated slash dates:
            --       if first part <= 12 -> treat as MM/DD/YYYY
            --       else                -> treat as DD/MM/YYYY
            --  3) Discard (NULL) if outside [2000-01-01, 2030-12-31]
            CASE
              WHEN p.iso_m IS NOT NULL THEN
                CASE
                  WHEN to_date(p.iso_m[1], 'YYYY-MM-DD') BETWEEN DATE '2000-01-01' AND DATE '2030-12-31'
                  THEN to_date(p.iso_m[1], 'YYYY-MM-DD')
                  ELSE NULL
                END
              WHEN p.slash_m IS NOT NULL THEN
                -- pick parts
                CASE
                  -- Try MM/DD/YYYY if first token looks like a month
                  WHEN (p.slash_m[1])::int BETWEEN 1 AND 12
                      AND (p.slash_m[2])::int BETWEEN 1 AND 31
                      AND (p.slash_m[3])::int BETWEEN 1900 AND 2100
                  THEN
                    CASE
                      WHEN to_date(p.slash_m[1] || '/' || p.slash_m[2] || '/' || p.slash_m[3], 'MM/DD/YYYY')
                          BETWEEN DATE '2000-01-01' AND DATE '2030-12-31'
                      THEN to_date(p.slash_m[1] || '/' || p.slash_m[2] || '/' || p.slash_m[3], 'MM/DD/YYYY')
                      ELSE NULL
                    END

                  -- Else try DD/MM/YYYY
                  WHEN (p.slash_m[1])::int BETWEEN 1 AND 31
                      AND (p.slash_m[2])::int BETWEEN 1 AND 12
                      AND (p.slash_m[3])::int BETWEEN 1900 AND 2100
                  THEN
                    CASE
                      WHEN to_date(p.slash_m[1] || '/' || p.slash_m[2] || '/' || p.slash_m[3], 'DD/MM/YYYY')
                          BETWEEN DATE '2000-01-01' AND DATE '2030-12-31'
                      THEN to_date(p.slash_m[1] || '/' || p.slash_m[2] || '/' || p.slash_m[3], 'DD/MM/YYYY')
                      ELSE NULL
                    END

                  ELSE NULL
                END
              ELSE NULL
            END AS decision_date_parsed
          FROM parsed p
        )
        """




        # Q1) Count Fall 2025 entries
        cur.execute(decision_cte + """
          SELECT COUNT(*) AS c
          FROM sp
          WHERE decision_date_parsed >= %s AND decision_date_parsed <= %s;
        """, (START, END))
        q1 = _one(cur)

        # Q2) % International (not "American" or "Other") among Fall 2025
        cur.execute(decision_cte + """
          SELECT
            ROUND(
              100.0 * SUM(CASE
                WHEN us_or_international IS NOT NULL
                     AND lower(us_or_international) NOT IN ('american','other')
                THEN 1 ELSE 0 END)
              / NULLIF(SUM(CASE WHEN us_or_international IS NOT NULL THEN 1 ELSE 0 END), 0)
            , 2) AS pct_international
          FROM sp
          WHERE decision_date_parsed >= %s AND decision_date_parsed <= %s;
        """, (START, END))
        q2 = _one(cur)

        # Q3) Avg GPA, GRE Q, GRE V, GRE AW (overall, not limited to Fall 2025)
        cur.execute(decision_cte + """
          SELECT
            ROUND(AVG(gpa)::numeric, 3)   AS avg_gpa,
            ROUND(AVG(gre)::numeric, 3)   AS avg_gre_q,
            ROUND(AVG(gre_v)::numeric, 3) AS avg_gre_v,
            ROUND(AVG(gre_aw)::numeric, 3) AS avg_gre_aw
          FROM sp;
        """)
        q3 = _row(cur)

        # Q4) Avg GPA of American students in Fall 2025
        cur.execute(decision_cte + """
          SELECT ROUND(AVG(gpa)::numeric, 3) AS avg_gpa_american_2025
          FROM sp
          WHERE decision_date_parsed >= %s AND decision_date_parsed <= %s
            AND lower(us_or_international) = 'american';
        """, (START, END))
        q4 = _one(cur)

        # Q5) % Acceptances in Fall 2025
        cur.execute(decision_cte + """
          SELECT
            ROUND(100.0 * SUM(CASE WHEN status_type_parsed = 'Accepted on' THEN 1 ELSE 0 END)
                  / NULLIF(COUNT(*), 0), 2) AS pct_accept_2025
          FROM sp
          WHERE decision_date_parsed >= %s AND decision_date_parsed <= %s;
        """, (START, END))
        q5 = _one(cur)

        # Q6) Avg GPA among Fall 2025 acceptances
        cur.execute(decision_cte + """
          SELECT ROUND(AVG(gpa)::numeric, 3) AS avg_gpa_accepted_2025
          FROM sp
          WHERE decision_date_parsed >= %s AND decision_date_parsed <= %s
            AND status_type_parsed = 'Accepted on';
        """, (START, END))
        q6 = _one(cur)

        # Q7) Count JHU Masters in CS (exact matches only, via variant lists)
        cur.execute(decision_cte + """
          SELECT COUNT(*) AS c
          FROM sp
          WHERE lower(llm_generated_university) = ANY(%(uni_variants)s)
            AND lower(llm_generated_program)    = ANY(%(prog_variants)s)
            AND (
                 lower(degree)                   = ANY(%(ms_variants)s)
                 OR lower(llm_generated_program) = ANY(%(ms_variants)s)
                );
        """, {
            "uni_variants":  JHU_UNI_VARIANTS,
            "prog_variants": CS_PROGRAM_VARIANTS,
            "ms_variants":   MS_DEGREE_VARIANTS,
        })
        q7 = _one(cur)

        # Q8) Count Georgetown PhD CS acceptances (Fall 2025; exact matches only)
        cur.execute(decision_cte + """
          SELECT COUNT(*) AS c
          FROM sp
          WHERE decision_date_parsed >= %(start)s AND decision_date_parsed <= %(end)s
            AND status_type_parsed = 'Accepted on'
            AND lower(llm_generated_university) = ANY(%(uni_variants)s)
            AND lower(llm_generated_program)    = ANY(%(prog_variants)s)
            AND (
                 lower(degree)                   = ANY(%(phd_variants)s)
                 OR lower(llm_generated_program) = ANY(%(phd_variants)s)
                );
        """, {
            "start": START, "end": END,
            "uni_variants":  GEORGETOWN_UNI_VARIANTS,
            "prog_variants": CS_PROGRAM_VARIANTS,
            "phd_variants":  PHD_DEGREE_VARIANTS,
        })
        q8 = _one(cur)

        # Q9) GPA difference (American vs International) for Fall 2025
        cur.execute(decision_cte + """
          SELECT
            ROUND(AVG(CASE WHEN lower(us_or_international) = 'american'
                           THEN gpa END)::numeric, 3) AS avg_american,
            ROUND(AVG(CASE WHEN us_or_international IS NOT NULL
                            AND lower(us_or_international) NOT IN ('american','other')
                           THEN gpa END)::numeric, 3) AS avg_international,
            ROUND( (AVG(CASE WHEN lower(us_or_international) = 'american' THEN gpa END)
                   - AVG(CASE WHEN us_or_international IS NOT NULL
                               AND lower(us_or_international) NOT IN ('american','other')
                              THEN gpa END)
                  )::numeric, 3) AS diff
          FROM sp
          WHERE decision_date_parsed >= %s AND decision_date_parsed <= %s;
        """, (START, END))
        q9 = _row(cur)  # dict: {avg_american, avg_international, diff}


        # Q10) Acceptance rate by university (Fall 2025), require at least 20 posts
        cur.execute(decision_cte + """
          SELECT
            uni AS university,
            COUNT(*)::int AS n,
            ROUND(
              100.0 * SUM(CASE WHEN status_type_parsed = 'Accepted on' THEN 1 ELSE 0 END)
              / NULLIF(COUNT(*), 0), 2
            ) AS acceptance_rate_pct
          FROM (
            SELECT
              trim(BOTH ' ' FROM COALESCE(
                NULLIF(lower(llm_generated_university), ''),
                NULLIF(split_part(program, ',', 2), '')
              )) AS uni,
              status_type_parsed,
              decision_date_parsed
            FROM sp
          ) base
          WHERE uni IS NOT NULL
            AND uni <> ''
            AND decision_date_parsed >= %s
            AND decision_date_parsed <= %s
          GROUP BY uni
          HAVING COUNT(*) >= 20
          ORDER BY acceptance_rate_pct DESC, n DESC
          LIMIT 10;
        """, (START, END))
        q10 = cur.fetchall()





    # Return all results as a dict
    return {
        "q1": q1,
        "q2": q2,
        "q3": q3,   
        "q4": q4,
        "q5": q5,
        "q6": q6,
        "q7": q7,
        "q8": q8,
        "q9": q9,   
        "q10": q10, 
    }

if __name__ == "__main__":
    import json
    print(json.dumps(compute_stats(), indent=2, default=str))
