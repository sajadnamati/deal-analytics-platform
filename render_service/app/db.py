# render_service/app/main.py

from fastapi import FastAPI
from .db import get_db_time

app = FastAPI(
    title="Deal Analytics API",
    version="0.1.0",
    description="Render-hosted API gateway for Deal Analytics (Supabase / local DB).",
)


@app.get("/health")
def health():
    """
    Simple health check to verify the service is up.
    """
    return {"status": "ok", "message": "Deal Analytics API is running."}


@app.get("/db/time")
def db_time():
    """
    Test endpoint that checks if the DB connection works and returns server time.
    """
    try:
        ts = get_db_time()
        return {
            "status": "ok",
            "db_time": str(ts),
        }
    except Exception as e:
        # For debugging; in production you might want to avoid returning raw error messages
        return {
            "status": "error",
            "error": str(e),
        }


# You can later add your real endpoints here, for example:
#
# @app.get("/deals/summary")
# def deals_summary():
#     ...
#
# For now we focus on wiring the full circuit end-to-end.
