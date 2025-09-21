# module_3/count_rows.py
''' Count total rows in the applicants table '''

from db import get_conn

def main():
    ''' Count total rows in the applicants table '''
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM applicants;")
        row = cur.fetchone()
        # row is a dict (not a tuple), so use the key
        total = row["total"]
        print(f"Total rows in applicants: {total}")

if __name__ == "__main__":
    main()
