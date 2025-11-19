# render_service/app/main.py

import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras

from backend.services.chat_handler import handle_question


# Load environment variables (.env locally, Render env in deployment)
load_dotenv()

app = FastAPI(
    title="Deal Analytics API",
    version="0.1.0",
    description="NLP → SQL → Validator → Supabase execution",
)
# ----------------------------------------------------
# Environment Debug Endpoint
# ----------------------------------------------------
@app.get("/env-debug")
def env_debug():
    """
    Debug endpoint to see what SUPABASE_DSN looks like in the running app.
    We only expose partial info (no full secrets).
    """
    dsn = os.getenv("SUPABASE_DSN", "")

    parsed_user = None
    parsed_host = None

    # key=value DSN parsing
    if "user=" in dsn:
        try:
            parsed_user = dsn.split("user=", 1)[1].split()[0]
        except:
            parsed_user = None

    if "host=" in dsn:
        try:
            parsed_host = dsn.split("host=", 1)[1].split()[0]
        except:
            parsed_host = None

    # URI-style parsing (postgresql://user:pass@host:port/db)
    if dsn.startswith("postgresql://"):
        try:
            after_scheme = dsn[len("postgresql://"):]
            user_pass, after_user = after_scheme.split("@", 1)
            parsed_user = user_pass.split(":")[0]
            parsed_host = after_user.split("/")[0].split(":")[0]
        except:
            pass

    return {
        "dsn_prefix": dsn[:140],  # first chars; avoids leaking password
        "parsed_user": parsed_user,
        "parsed_host": parsed_host,
    }

# Jinja2 templates setup (adjust path if you change folder structure)
templates = Jinja2Templates(directory="render_service/app/templates")


# =========================
# Pydantic models
# =========================

class EchoRequest(BaseModel):
    message: str


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    status: str
    stage: str
    question: str
    sql: str | None = None
    validator: dict | None = None
    rows: list | None = None
    error: str | None = None


# =========================
# Health & demo endpoints
# =========================

@app.get("/health")
def health():
    """
    Simple health check endpoint to confirm the service is running.
    """
    return {
        "status": "ok",
        "service": "deal-analytics-api",
    }


@app.post("/echo")
def echo(payload: EchoRequest):
    """
    Simple echo endpoint to validate JSON request/response flow.
    """
    return {
        "status": "ok",
        "echo": payload.message,
        "length": len(payload.message),
    }


@app.get("/sample/summary")
def sample_summary():
    """
    Pretend summary endpoint that returns static data.
    Later we can replace this with real analytics.
    """
    return {
        "status": "ok",
        "summary": {
            "total_deals": 42,
            "total_volume_mt": 123456.78,
            "period": "2024-01-01 to 2024-12-31",
        },
    }


# =========================
# DB execution helper
# =========================

def execute_sql_sync(sql: str):
    """
    Executes a SQL query synchronously on Supabase using psycopg2.
    Returns list of dicts, or {"error": "..."} on failure.
    """
    dsn = os.getenv("SUPABASE_DSN")
    if not dsn:
        raise RuntimeError("SUPABASE_DSN not set in environment variables.")

    try:
        conn = psycopg2.connect(dsn)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        # Return error as dict so caller can attach it to response
        return {"error": str(e)}

@app.get("/db-test")
def db_test():
    """
    Simple DB connectivity test.
    Runs: SELECT 1 AS test_col;
    """
    try:
        result = execute_sql_sync("SELECT 1 AS test_col;")
        return {"status": "ok", "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}
# =========================
# Main /chat endpoint (JSON)
# =========================

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    Main AI → SQL → Validator → optional Supabase execution.

    This is the "engine" endpoint used both by:
      - the front-end chat page (/)
      - any debug tools (e.g. /docs, curl, Postman)
    """

    # 1. Run NL → SQL → Validator
    result = handle_question(req.question)

    # If validator failed, return immediately
    if result.get("validator", {}).get("status") != "ok":
        # result is already shaped correctly for ChatResponse
        return ChatResponse(**result)

    # 2. Local mode: skip DB execution
    if os.getenv("LOCAL_MODE", "false").lower() == "true":
        result["rows"] = None
        result["stage"] = "validator (local mode, DB skip)"
        return ChatResponse(**result)

    # 3. Execute on Supabase (Render mode)
    sql = result["sql"]
    db_result = execute_sql_sync(sql)

    if isinstance(db_result, dict) and "error" in db_result:
        result["error"] = db_result["error"]
        # Keep stage as whatever handle_question set, or override if you prefer
        return ChatResponse(**result)

    result["rows"] = db_result
    result["stage"] = "db_execution"

    return ChatResponse(**result)


# =========================
# User-facing Chat Page (HTML)
# =========================

@app.get("/", response_class=HTMLResponse)
def main_chat_page(request: Request):
    """
    Main user-facing ChatGPT-style page.

    - Uses templates/news_chat.html
    - Talks to the /chat JSON endpoint under the hood
    - Navbar includes link to /docs as a "Debug" view
    """
    return templates.TemplateResponse("news_chat.html", {"request": request})

