import os
import psycopg
from psycopg.rows import dict_row

def get_conn():
    url = os.getenv("DATABASE_URL")
    if url:
        return psycopg.connect(url, row_factory=dict_row)
    return psycopg.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", 5432),
        dbname=os.getenv("PGDATABASE", "gradcafe"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),    #<--- Not really needed as password is defined in environment variable for security
        row_factory=dict_row,
    )
if __name__ == "__main__":
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT version();")
        print(cur.fetchone()["version"])
    print("DB connection OK")
