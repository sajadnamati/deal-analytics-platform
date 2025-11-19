# backend/services/chat_handler.py

import os
import json
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

from backend.validator.validator import validate_sql  # adjust import if needed

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_REGISTRY_PATH = PROJECT_ROOT / "metadata" / "schema_registry.json"

load_dotenv(PROJECT_ROOT / ".env")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

with SCHEMA_REGISTRY_PATH.open("r", encoding="utf-8") as f:
    SCHEMA_REGISTRY = json.load(f)


def build_system_prompt() -> str:
    return (
        "You are a SQL generator for an energy-trading deals database.\n"
        "You will receive a natural-language question and must respond with ONLY a single PostgreSQL SELECT query.\n"
        "Use ONLY the tables and columns from this schema registry:\n\n"
        f"{json.dumps(SCHEMA_REGISTRY, indent=2)}\n\n"
        "STRICT SQL RULES:\n"
        "1. SELECT only. No INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, or TRUNCATE.\n"
        "2. No subqueries, no CTEs (WITH), no UNION, no window functions.\n"
        "3. DO NOT use schema prefixes (never write 'public.').\n"
        "4. DO NOT use table aliases (no 'de', 'rp', 't1', etc.).\n"
        "5. DO NOT prefix columns with table names. For example, write 'volume', not 'deal_event.volume'.\n"
        "6. All JOINs must use full table names and column names without prefixing. Example:\n"
        "       FROM deal_event\n"
        "       JOIN ref_product ON deal_event.product_id = ref_product.product_id\n"
        "7. Do not include comments or explanations; output ONLY the SQL.\n"
        "8. Never include trailing semicolons.\n"
    )




def handle_question(question: str) -> Dict[str, Any]:
    """
    Core NL -> SQL -> Validator pipeline used by both the CLI script and /chat endpoint.
    Returns a structured dict for nice JSON in the API.
    """

    system_prompt = build_system_prompt()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    try:
        completion = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            temperature=0,
        )
        raw_sql = completion.choices[0].message.content.strip()
    except Exception as e:
        return {
            "status": "error",
            "stage": "openai",
            "question": question,
            "error": str(e),
        }

    # Clean ```sql fences if present
    if raw_sql.startswith("```"):
        raw_sql = raw_sql.strip("`")
        if "\n" in raw_sql:
            raw_sql = raw_sql.split("\n", 1)[1]

    # Clean SQL:
    raw_sql = raw_sql.strip().rstrip(";")

    # 🚨 REMOVE schema prefixes like "public." — our validator forbids them
    raw_sql = raw_sql.replace("public.", "")

    # 🚨 OPTIONAL: block aliases by removing " de", " rp", etc.
    # We won't do this aggressively yet; system prompt should handle it.

    # Run validator
    validation_result = validate_sql(raw_sql, SCHEMA_REGISTRY)

    response: Dict[str, Any] = {
        "status": "ok" if validation_result.get("status") == "ok" else "invalid_sql",
        "stage": "validator",
        "question": question,
        "sql": raw_sql,
        "validator": validation_result,
    }

    # TODO (later): if status ok, execute SQL on Supabase and add "rows" to response

    return response

import asyncpg

async def execute_sql(sql: str, dsn: str):
    conn = await asyncpg.connect(dsn)
    rows = await conn.fetch(sql)
    await conn.close()
    return [dict(r) for r in rows]