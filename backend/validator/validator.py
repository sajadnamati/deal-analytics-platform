"""
Simple SQL Validator v1 for AKAM (M1, read-only).

- Enforces: SELECT-only
- Enforces: no dangerous keywords / comments
- Enforces: tables and columns must exist in schema_registry.json
- Enforces: joins must follow declared foreign-key-style references
- Enforces: basic complexity limits (no UNION, CTEs, etc.)

This is intentionally conservative and supports "simple" SQL:
SELECT ... FROM ... [JOIN ...] [WHERE ...] [GROUP BY ...] [ORDER BY ...] [LIMIT ...].

It is NOT a full SQL parser. It’s good enough for M1.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Adjust this path if needed
SCHEMA_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "metadata" / "schema_registry.json"


# -----------------------------
# Registry loading and helpers
# -----------------------------

def load_schema_registry(path: Optional[Path] = None) -> Dict:
    """
    Load the schema registry JSON from disk.
    """
    registry_path = path or SCHEMA_REGISTRY_PATH
    with open(registry_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_registry_index(registry: Dict) -> Dict:
    """
    Build some quick lookup structures from the registry.

    Returns a dict with:
      - tables: set of table names
      - columns: {table: set(columns)}
      - fk_pairs: set of allowed join pairs ( (table1, col1, table2, col2) )
    """
    tables = set()
    columns = {}
    fk_pairs = set()

    tables_def = registry.get("tables", {})

    for table_name, tdef in tables_def.items():
        tables.add(table_name)
        cols_def = tdef.get("columns", {})
        columns[table_name] = set(cols_def.keys())

        for col_name, cdef in cols_def.items():
            ref = cdef.get("references")
            if ref:
                ref_table = ref.get("table")
                ref_col = ref.get("column")
                if ref_table and ref_col:
                    # Allow joining in both directions
                    fk_pairs.add((table_name, col_name, ref_table, ref_col))
                    fk_pairs.add((ref_table, ref_col, table_name, col_name))

    return {
        "tables": tables,
        "columns": columns,
        "fk_pairs": fk_pairs,
    }


# -----------------------------
# Core validation entry point
# -----------------------------

def validate_sql(sql: str, registry: Dict) -> Dict:
    """
    Validate an SQL query according to Validator v1 rules.

    Returns:
        {
          "status": "ok"
        }
      or
        {
          "status": "error",
          "errors": [ ... ]
        }
    """
    errors: List[str] = []

    # Normalize & pre-clean SQL
    normalized_sql = sql.strip()

    # FIX 1: prevent EXTRACT(YEAR FROM deal_date) from being mis-parsed
    # as "FROM deal_date" (a table) by the table-extraction regex.
    # We rewrite "EXTRACT(YEAR FROM col)" → "col_year" purely for validation.
    normalized_sql = re.sub(
        r"extract\s*\(\s*year\s+from\s+([a-zA-Z_][\w]*)\s*\)",
        r"\1_year",
        normalized_sql,
        flags=re.IGNORECASE,
    )

    lowered = normalized_sql.lower()

    # 1) Safety checks
    errors.extend(_check_single_statement(normalized_sql))
    errors.extend(_check_read_only(lowered))
    errors.extend(_check_disallowed_keywords(lowered))
    errors.extend(_check_comments(lowered))

    # Short-circuit if already obviously unsafe
    if errors:
        return {"status": "error", "errors": errors}

    # 2) Complexity checks
    errors.extend(_check_complexity(lowered))

    if errors:
        return {"status": "error", "errors": errors}

    # 3) Schema-related checks
    idx = build_registry_index(registry)
    tables, alias_map = _extract_tables_and_aliases(lowered)
    errors.extend(_check_tables_exist(tables, idx))

    if errors:
        return {"status": "error", "errors": errors}

    # 4) Column and join checks
    errors.extend(_check_columns_and_joins(lowered, tables, alias_map, idx))

    if errors:
        return {"status": "error", "errors": errors}

    return {"status": "ok"}


# -----------------------------
# Safety checks
# -----------------------------

def _check_single_statement(sql: str) -> List[str]:
    """
    Ensure there is only a single statement.
    We reject semicolons to prevent statement stacking.
    """
    errors = []
    if ";" in sql:
        errors.append("Multiple statements or semicolons are not allowed.")
    return errors


def _check_read_only(lowered_sql: str) -> List[str]:
    """
    Ensure the query is SELECT-only.
    """
    errors = []

    # Must start with SELECT
    # (Allow whitespace or parentheses at the very start in case of formatting)
    if not lowered_sql.lstrip().startswith("select"):
        errors.append("Only SELECT statements are allowed in read-only mode.")

    return errors


def _check_disallowed_keywords(lowered_sql: str) -> List[str]:
    """
    Block obviously dangerous commands.
    """
    errors = []
    forbidden = [
        " insert ",
        " update ",
        " delete ",
        " drop ",
        " alter ",
        " truncate ",
        " create ",
        " grant ",
        " revoke ",
        " comment ",
        " execute ",
        " call ",
        " do ",
    ]

    for kw in forbidden:
        if kw in lowered_sql:
            errors.append(f"Keyword '{kw.strip()}' is not allowed in read-only mode.")

    return errors


def _check_comments(lowered_sql: str) -> List[str]:
    """
    Block SQL comments to avoid hiding content.
    """
    errors = []
    if "--" in lowered_sql or "/*" in lowered_sql:
        errors.append("SQL comments are not allowed.")
    return errors


# -----------------------------
# Complexity checks
# -----------------------------

def _check_complexity(lowered_sql: str) -> List[str]:
    """
    Enforce simple query patterns only, per Validator v1.
    """
    errors = []
    forbidden = [
        " union ",
        " intersect ",
        " except ",
        " with ",
        " over(",
        " returning ",
    ]

    for kw in forbidden:
        if kw in lowered_sql:
            errors.append(f"Query pattern too complex for M1: found '{kw.strip()}'.")

    # Very naive subquery detection: "select" inside parentheses
    # beyond the first occurrence.
    first_select_pos = lowered_sql.find("select")
    if first_select_pos != -1:
        second_select_pos = lowered_sql.find("select", first_select_pos + 1)
        if second_select_pos != -1 and "(" in lowered_sql[first_select_pos:second_select_pos]:
            errors.append("Subqueries are not allowed in M1.")

    return errors


# -----------------------------
# Schema checks: tables
# -----------------------------

def _extract_tables_and_aliases(lowered_sql: str) -> Tuple[List[str], Dict[str, str]]:
    """
    Extract table names from FROM and JOIN clauses.

    For M1, we **do not support custom aliases**.
    We simply map each table name to itself in alias_map so that
    'deal_event.volume' and 'ref_product.product_id' are valid.
    """
    tables: List[str] = []
    alias_map: Dict[str, str] = {}

    # Simpler pattern: capture the table name after FROM/JOIN.
    pattern = re.compile(
        r"\b(from|join)\s+([a-zA-Z_][\w]*)",
        re.IGNORECASE,
    )

    for match in pattern.finditer(lowered_sql):
        table_name = match.group(2)
        if table_name not in tables:
            tables.append(table_name)
        # In M1, the "alias" is always just the table name itself
        alias_map[table_name] = table_name

    return tables, alias_map


def _check_tables_exist(tables: List[str], idx: Dict) -> List[str]:
    """
    Ensure all referenced tables exist in the registry.
    """
    errors = []
    known_tables = idx["tables"]

    for t in tables:
        if t not in known_tables:
            errors.append(f"Unknown table '{t}' (not in schema registry).")

    return errors


# -----------------------------
# Schema checks: columns & joins
# -----------------------------

def _check_columns_and_joins(
    lowered_sql: str,
    tables: List[str],
    alias_map: Dict[str, str],
    idx: Dict,
) -> List[str]:
    errors: List[str] = []

    # a) Check alias usage: any alias in column references must be known
    # b) Check that columns exist for each table
    # c) Check joins follow allowed fk_pairs

    # Find alias.column patterns throughout the query
    col_pattern = re.compile(r"\b([a-zA-Z_][\w]*)\.([a-zA-Z_][\w]*)\b")
    col_refs = col_pattern.findall(lowered_sql)

    for alias, col in col_refs:
        if alias not in alias_map:
            errors.append(f"Unknown table alias '{alias}' in column reference '{alias}.{col}'.")
            continue

        table_name = alias_map[alias]
        known_cols = idx["columns"].get(table_name, set())
        if col not in known_cols:
            errors.append(
                f"Unknown column '{col}' on table '{table_name}' (alias '{alias}')."
            )

    # Join checks: look specifically in ON clauses for alias.col = alias2.col
    join_pattern = re.compile(
        r"\b([a-zA-Z_][\w]*)\.([a-zA-Z_][\w]*)\s*=\s*([a-zA-Z_][\w]*)\.([a-zA-Z_][\w]*)"
    )
    fk_pairs = idx["fk_pairs"]

    for m in join_pattern.finditer(lowered_sql):
        alias1, col1, alias2, col2 = m.groups()
        if alias1 not in alias_map or alias2 not in alias_map:
            # alias problem already covered above; skip
            continue

        table1 = alias_map[alias1]
        table2 = alias_map[alias2]
        pair = (table1, col1, table2, col2)

        if pair not in fk_pairs:
            errors.append(
                f"Join between '{table1}.{col1}' and '{table2}.{col2}' "
                f"is not declared as a relationship in the schema registry."
            )

    # Note: this v1 implementation does NOT robustly check unqualified columns
    # (columns without table/alias prefix). For M1, you should prefer queries
    # that qualify join columns, e.g., deal_event.product_id, ref_product.product_id.

    return errors


# -----------------------------
# Simple CLI test (optional)
# -----------------------------

if __name__ == "__main__":
    registry = load_schema_registry()
    print("Loaded tables:", list(registry.get("tables", {}).keys()))

    while True:
        try:
            user_sql = input("\nEnter SQL to validate (or 'q' to quit):\n> ")
        except EOFError:
            break

        if user_sql.strip().lower() in ("q", "quit", "exit"):
            break

        result = validate_sql(user_sql, registry)
        print("Result:", json.dumps(result, indent=2))
