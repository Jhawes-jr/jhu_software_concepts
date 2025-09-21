''' Database connection utility '''

import os
import psycopg
from psycopg.rows import dict_row

def get_conn():
    ''' Get a new database connection using environment variables '''
    url = os.getenv("DATABASE_URL")
    if url:
        return psycopg.connect(url, row_factory=dict_row)

    host = os.getenv("PGHOST", "localhost")
    port = int(os.getenv("PGPORT", "5432"))
    dbname = os.getenv("PGDATABASE", "gradcafe")
    user = os.getenv("PGUSER", "postgres")
    password = os.getenv("PGPASSWORD", "")

    return psycopg.connect(host=host, port=port, dbname=dbname,
                           user=user, password=password, row_factory=dict_row)
if __name__ == "__main__":
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT version();")
        print(cur.fetchone()["version"])
    print("DB connection OK")
