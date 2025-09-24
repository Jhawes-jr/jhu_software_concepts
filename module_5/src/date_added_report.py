''' Report on date_added field in applicants table '''

from pathlib import Path
import csv

from psycopg import sql

from db import get_conn


TABLE_APPLICANTS = sql.Identifier("applicants")
DATE_COL = sql.Identifier("date_added")
PER_DAY_LIMIT = 10000
WEIRD_LIMIT = 1000

def main():
    ''' Report on date_added field in applicants table '''
    with get_conn() as conn, conn.cursor() as cur:
        # Totals
        totals_stmt = sql.SQL(
            """
            SELECT
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE {date_col} IS NOT NULL) AS with_date,
              COUNT(*) FILTER (WHERE {date_col} IS NULL)     AS null_date
            FROM {table}
            """
        ).format(date_col=DATE_COL, table=TABLE_APPLICANTS)

        cur.execute(totals_stmt)
        t = cur.fetchone()
        print(f"Total: {t['total']}  with_date: {t['with_date']}  null_date: {t['null_date']}")

        # Min / Max among non-NULL
        min_max_stmt = sql.SQL(
            """
            SELECT MIN({date_col}) AS min_date, MAX({date_col}) AS max_date
            FROM {table}
            WHERE {date_col} IS NOT NULL
            """
        ).format(date_col=DATE_COL, table=TABLE_APPLICANTS)

        cur.execute(min_max_stmt)
        mm = cur.fetchone()
        print(f"Min date_added: {mm['min_date']}  Max date_added: {mm['max_date']}")

        # Per-day counts
        per_day_stmt = sql.SQL(
            """
            SELECT {date_col}, COUNT(*) AS n
            FROM {table}
            WHERE {date_col} IS NOT NULL
            GROUP BY {date_col}
            ORDER BY {date_col}
            LIMIT {limit}
            """
        ).format(date_col=DATE_COL, table=TABLE_APPLICANTS, limit=sql.Literal(PER_DAY_LIMIT))

        cur.execute(per_day_stmt)
        rows = cur.fetchall()
        print(f"Distinct non-NULL dates: {len(rows)}")
        if rows:
            print("First 5:")
            for r in rows[:5]:
                print(f"  {r['date_added']}: {r['n']}")
            print("Last 5:")
            for r in rows[-5:]:
                print(f"  {r['date_added']}: {r['n']}")

        # Flag obviously out-of-range dates (just in case)
        weird_stmt = sql.SQL(
            """
            SELECT {date_col}, COUNT(*) AS n
            FROM {table}
            WHERE {date_col} IS NOT NULL
              AND ({date_col} < DATE '2000-01-01' OR {date_col} > DATE '2030-12-31')
            GROUP BY {date_col}
            ORDER BY {date_col}
            LIMIT {limit}
            """
        ).format(date_col=DATE_COL, table=TABLE_APPLICANTS, limit=sql.Literal(WEIRD_LIMIT))

        cur.execute(weird_stmt)
        weird = cur.fetchall()
        if weird:
            print("\nOut-of-range date_added values:")
            for r in weird:
                print(f"  {r['date_added']}: {r['n']}")

        # Write CSV with per-date counts
        out = Path(__file__).with_name("date_added_counts.csv")
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date_added", "count"])
            for r in rows:
                w.writerow([r["date_added"], r["n"]])
        print(f"\nWrote per-date counts to {out}")

if __name__ == "__main__":
    main()
