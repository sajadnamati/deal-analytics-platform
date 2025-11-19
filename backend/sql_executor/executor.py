import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Load env vars from .env (for local dev)
load_dotenv()

SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
if not SUPABASE_DB_URL:
    raise RuntimeError("SUPABASE_DB_URL is not set. Add it to .env or your environment.")

def execute_query(sql: str):
    """
    Execute a read-only SQL query against Supabase and return rows as a list of dicts.
    Assumes the query is safe and read-only (already validated).
    """
    conn = psycopg2.connect(SUPABASE_DB_URL)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    finally:
        conn.close()
