# module_3/check_status.py

from db import get_conn
import re
from collections import Counter

def main():
    with get_conn() as conn, conn.cursor() as cur:
        # existing logic: pull distinct statuses
        cur.execute("SELECT DISTINCT status FROM applicants WHERE status IS NOT NULL;")
        rows = [r["status"] for r in cur.fetchall()]

    prefixes = []
    for s in rows:
        s = s.strip()
        # take everything up to the first digit (date starts with a number)
        m = re.match(r"^([^\d]+)", s)
        if m:
            prefixes.append(m.group(1).strip())

    counts = Counter(prefixes)

    print("Distinct prefixes in status column:")
    for p, c in counts.items():
        print(f"  {p} — {c} records")

    # --- NEW: GPA + GRE min/max checks ---
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT
              MIN(gpa)     AS min_gpa,     MAX(gpa)     AS max_gpa,
              MIN(gre)     AS min_gre_q,   MAX(gre)     AS max_gre_q,
              MIN(gre_v)   AS min_gre_v,   MAX(gre_v)   AS max_gre_v,
              MIN(gre_aw)  AS min_gre_aw,  MAX(gre_aw)  AS max_gre_aw
            FROM applicants;
        """)
        row = cur.fetchone()

    print("\nGPA / GRE ranges:")
    print(f"  GPA:   {row['min_gpa']} – {row['max_gpa']}")
    print(f"  GRE Q: {row['min_gre_q']} – {row['max_gre_q']}")
    print(f"  GRE V: {row['min_gre_v']} – {row['max_gre_v']}")
    print(f"  GRE AW:{row['min_gre_aw']} – {row['max_gre_aw']}")

if __name__ == "__main__":
    main()
