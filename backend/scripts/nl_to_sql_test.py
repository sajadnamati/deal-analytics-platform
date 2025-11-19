import os
import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
import sys
from pathlib import Path

# Ensure project root is on sys.path (works even if Spyder changes CWD)
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
# Local imports
from backend.validator.validator import load_schema_registry, validate_sql
from backend.sql_executor.executor import execute_query
# --- Load environment (.env for local dev) ---
load_dotenv()













OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set. Put it in .env or Render env vars.")

client = OpenAI(api_key=OPENAI_API_KEY)

# --- Paths ---
ROOT_DIR = Path(__file__).resolve().parents[2]
SCHEMA_REGISTRY_PATH = ROOT_DIR / "metadata" / "schema_registry.json"


def build_schema_summary_for_prompt(registry: dict) -> str:
    """
    Build a compact, human-readable summary of the schema
    to include in the system prompt.
    """
    lines = []
    tables = registry.get("tables", {})

    for table_name, tdef in tables.items():
        lines.append(f"Table: {table_name}")
        cols = tdef.get("columns", {})
        col_desc = []
        for col_name, cdef in cols.items():
            sql_type = cdef.get("sql_type", "unknown")
            col_desc.append(f"{col_name} ({sql_type})")
        lines.append("  Columns: " + ", ".join(col_desc))
        lines.append("")  # blank line between tables

    return "\n".join(lines)


def build_system_prompt(registry: dict) -> str:
    """
    System prompt telling the model how to write SQL.
    """
    schema_txt = build_schema_summary_for_prompt(registry)

    prompt = f"""
You are an assistant that writes safe, read-only SQL queries for a Postgres database.

Rules:
- Use ONLY the tables and columns from the schema description below.
- The database schema is in schema 'public'.
- You must ONLY generate a single SELECT statement.
- Do NOT use INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, or any DDL/DML.
- Do NOT use subqueries, CTEs (WITH), UNION, INTERSECT, EXCEPT, or window functions.
- Prefer fully qualified columns with table aliases, e.g. d.volume, d.deal_date.
- Only join tables using the relationships implied by foreign keys.
- Keep the SQL as simple as possible while answering the question.
- VERY IMPORTANT: Output ONLY raw SQL.
- Do NOT wrap the SQL in code fences (no ```sql, no ```).
- Do NOT include any markdown, comments, or explanations.
- Do NOT add a trailing semicolon at the end of the query.
- Do NOT prefix tables with schema names. Use ONLY the bare table names exactly as defined in the schema (e.g. "deal_event", not "public.deal_event").

Database schema:
{schema_txt}
"""
    return prompt.strip()


def generate_sql_from_nl(question: str, registry: dict) -> str:
    """
    Call the OpenAI API to generate SQL for a natural-language question.
    """
    system_prompt = build_system_prompt(registry)

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # adjust if you want
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        temperature=0.1,
        max_tokens=400,
    )

    sql = response.choices[0].message.content.strip()
    # --- Cleanup: remove code fences / semicolons if the model ignored instructions ---
    # Remove any markdown code fences
    sql = sql.replace("```sql", "").replace("```", "").strip()
    # Sometimes models prepend "SQL:" or similar
    if sql.lower().startswith("sql:"):
        sql = sql[4:].strip()
    # Remove trailing semicolon
    if sql.endswith(";"):
        sql = sql[:-1].strip()
    return sql


# def main():
#     registry = load_schema_registry(SCHEMA_REGISTRY_PATH)

#     print("✅ Loaded schema registry from:", SCHEMA_REGISTRY_PATH)
#     print("Tables:", ", ".join(registry.get("tables", {}).keys()))
    
#     while True:
#         try:
#             question = input("\nEnter a question about your deals (or 'q' to quit):\n> ")
#         except EOFError:
#             break

#         if question.strip().lower() in ("q", "quit", "exit"):
#             break

#         # 1) AI generates SQL
#         sql = generate_sql_from_nl(question, registry)
#         print("\n🤖 Proposed SQL:\n", sql)

#         # 2) Validator checks SQL
#         result = validate_sql(sql, registry)
#         print("\n🛡 Validator result:\n", json.dumps(result, indent=2))

#         if result.get("status") != "ok":
#             print("\n❌ SQL rejected by validator. The AI would try to fix it in a full system.")
#             continue

#         print("\n✅ SQL approved by validator. Executing against Supabase...")

#         try:
#             rows = execute_query(sql)
#             print(f"\n📊 Rows returned: {len(rows)}")
#             for i, row in enumerate(rows[:5], start=1):
#                 print(f"Row {i}: {row}")
#         except Exception as e:
#             print("\n⚠️ Error querying Supabase:")
#             print(repr(e))

if __name__ == "__main__":
    main()
