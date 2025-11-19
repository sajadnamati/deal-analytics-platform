"""
test_db_connection.py
Put this file in: backend/scripts/
Run it from Spyder to verify Supabase connectivity.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg2


def main():
    # 1. Locate project root and .env
    project_root = Path(__file__).resolve().parents[2]
    env_path = project_root / ".env"

    print("===============================================")
    print("PROJECT ROOT:", project_root)
    print("ENV PATH:", env_path)
    print("===============================================")

    if not env_path.exists():
        print("❌ .env NOT FOUND at:", env_path)
        return

    # 2. Load env vars (override anything previously set)
    print("Loading .env ...")
    load_dotenv(env_path, override=True)

    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")

    print("DB_HOST:", db_host)
    print("DB_PORT:", db_port)
    print("DB_NAME:", db_name)
    print("DB_USER:", db_user)
    print("DB_PASSWORD:", "******** (hidden)")
    print("===============================================")

    # 3. Attempt connection
    try:
        print("Attempting connection ...")

        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_password,
            sslmode="require",  # recommended for Supabase
        )

        print("✅ CONNECTED SUCCESSFULLY!")

        # 4. Run a simple test query
        with conn.cursor() as cur:
            cur.execute("SELECT now();")
            result = cur.fetchone()
            print("Server time:", result[0])

        conn.close()
        print("Connection closed cleanly.")

    except Exception as e:
        print("❌ CONNECTION FAILED:")
        print(repr(e))


if __name__ == "__main__":
    main()
