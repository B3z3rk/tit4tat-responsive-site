import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .database import Base, SessionLocal, engine, run_lightweight_migrations
from .routers import activities, admin, announcements, auth, dashboard, directory, emergency, messages, reports
from .seed import seed_if_empty

# Without this, INFO-level messages (e.g. email_utils' "SMTP not configured,
# logging this email instead" fallback) are silently dropped - Python's
# logging module has no output handler at all until something configures one.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

Base.metadata.create_all(bind=engine)
run_lightweight_migrations()

with SessionLocal() as db:
    seed_if_empty(db)

# The interactive docs (/docs, /redoc) and raw schema (/openapi.json) hand
# anyone who can reach the server a full map of every endpoint and payload
# shape — disabled unless explicitly opted into for local development via
# `set ENABLE_API_DOCS=true` (PowerShell) before starting uvicorn.
DOCS_ENABLED = os.getenv("ENABLE_API_DOCS", "false").lower() == "true"

app = FastAPI(
    title="Tit4Tat API",
    docs_url="/docs" if DOCS_ENABLED else None,
    redoc_url="/redoc" if DOCS_ENABLED else None,
    openapi_url="/openapi.json" if DOCS_ENABLED else None,
)

app.include_router(auth.router, prefix="/api/auth")
app.include_router(admin.router, prefix="/api/admin")
app.include_router(activities.router, prefix="/api/activities")
app.include_router(reports.router, prefix="/api")
app.include_router(directory.router, prefix="/api/members")
app.include_router(messages.router, prefix="/api/messages")
app.include_router(emergency.router, prefix="/api/emergency")
app.include_router(announcements.router, prefix="/api/announcements")
app.include_router(dashboard.router, prefix="/api/dashboard")

# The static mount below serves the whole repo root (frontend HTML/CSS/JS live
# flat at the root alongside backend/), so without this guard it would also
# serve backend/ (source code + the live sqlite db, complete with password
# hashes and TOTP secrets), .git/ (full history), and uploads/verification/
# (Super-Admin-only documents) to anyone who requests the path directly.
# Verification documents must ONLY be reachable through the authenticated,
# role-gated /api endpoint — never as a static file.
BLOCKED_STATIC_PREFIXES = ("/backend", "/.git", "/uploads/verification")


@app.middleware("http")
async def block_sensitive_static_paths(request: Request, call_next):
    if any(request.url.path.startswith(p) for p in BLOCKED_STATIC_PREFIXES):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    return await call_next(request)


# Static frontend mount MUST come after all /api routers above, or this
# catch-all would 404 every API request before the routers ever see it.
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
