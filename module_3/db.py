import os
import psycopg2
from psycopg2.extras import RealDictCursor

def get_conn():
    url = os.getenv("DATABASE_URL")
    if url:
        return psycopg2.connect(url, cursor_factory=RealDictCursor)
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", 5432),
        dbname=os.getenv("PGDATABASE", "gradcafe"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),
        cursor_factory=RealDictCursor,
    )
if __name__ == "__main__":
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT version();")
        print(cur.fetchone()["version"])
    print("DB connection OK")
