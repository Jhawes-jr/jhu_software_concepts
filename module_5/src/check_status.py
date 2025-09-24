# module_3/check_status.py
''' Check distinct prefixes in the status column and GPA/GRE ranges '''

import re
from collections import Counter

from psycopg import sql

from db import get_conn


STATUS_LIMIT = 1000
TABLE_APPLICANTS = sql.Identifier("applicants")



def main():
    ''' Check distinct prefixes in the status column and GPA/GRE ranges '''
    with get_conn() as conn, conn.cursor() as cur:
        status_stmt = sql.SQL(
        "SELECT DISTINCT status "
        "FROM {table} "
        "WHERE status IS NOT NULL "
        "ORDER BY status "
        "LIMIT {limit}"
    ).format(
            table=TABLE_APPLICANTS,
            limit=sql.Literal(STATUS_LIMIT),
        )

        cur.execute(status_stmt)
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
        ranges_stmt = sql.SQL(
            """
            SELECT
              MIN({gpa})    AS min_gpa,    MAX({gpa})    AS max_gpa,
              MIN({gre})    AS min_gre_q,  MAX({gre})    AS max_gre_q,
              MIN({gre_v})  AS min_gre_v,  MAX({gre_v})  AS max_gre_v,
              MIN({gre_aw}) AS min_gre_aw, MAX({gre_aw}) AS max_gre_aw
            FROM {table}
            """
        ).format(
            gpa=sql.Identifier("gpa"),
            gre=sql.Identifier("gre"),
            gre_v=sql.Identifier("gre_v"),
            gre_aw=sql.Identifier("gre_aw"),
            table=TABLE_APPLICANTS,
        )

        cur.execute(ranges_stmt)
        row = cur.fetchone()

    print("\nGPA / GRE ranges:")
    print(f"  GPA:   {row['min_gpa']} – {row['max_gpa']}")
    print(f"  GRE Q: {row['min_gre_q']} – {row['max_gre_q']}")
    print(f"  GRE V: {row['min_gre_v']} – {row['max_gre_v']}")
    print(f"  GRE AW:{row['min_gre_aw']} – {row['max_gre_aw']}")

if __name__ == "__main__":
    main()
