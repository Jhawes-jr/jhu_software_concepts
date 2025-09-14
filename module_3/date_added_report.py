from db import get_conn
from pathlib import Path
import csv

def main():
    with get_conn() as conn, conn.cursor() as cur:
        # Totals
        cur.execute("""
            SELECT
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE date_added IS NOT NULL) AS with_date,
              COUNT(*) FILTER (WHERE date_added IS NULL)     AS null_date
            FROM applicants;
        """)
        t = cur.fetchone()
        print(f"Total: {t['total']}  with_date: {t['with_date']}  null_date: {t['null_date']}")

        # Min / Max among non-NULL
        cur.execute("""
            SELECT MIN(date_added) AS min_date, MAX(date_added) AS max_date
            FROM applicants
            WHERE date_added IS NOT NULL;
        """)
        mm = cur.fetchone()
        print(f"Min date_added: {mm['min_date']}  Max date_added: {mm['max_date']}")

        # Per-day counts
        cur.execute("""
            SELECT date_added, COUNT(*) AS n
            FROM applicants
            WHERE date_added IS NOT NULL
            GROUP BY date_added
            ORDER BY date_added;
        """)
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
        cur.execute("""
            SELECT date_added, COUNT(*) AS n
            FROM applicants
            WHERE date_added IS NOT NULL
              AND (date_added < DATE '2000-01-01' OR date_added > DATE '2030-12-31')
            GROUP BY date_added
            ORDER BY date_added;
        """)
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
