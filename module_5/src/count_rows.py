# module_3/count_rows.py
''' Count total rows in the applicants table '''

from psycopg import sql

from db import get_conn

TABLE_APPLICANTS = sql.Identifier("applicants")

def main():
    ''' Count total rows in the applicants table '''
    with get_conn() as conn, conn.cursor() as cur:
        stmt = sql.SQL("SELECT COUNT(*) AS total FROM {table}").format(
            table=TABLE_APPLICANTS,
        )

        cur.execute(stmt)
        row = cur.fetchone()
        # row is a dict (not a tuple), so use the key
        total = row["total"]
        print(f"Total rows in applicants: {total}")

if __name__ == "__main__":
    main()
