import os
import json
import time
import uuid
from datetime import datetime

import boto3
import psycopg2
import structlog
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger()

app = FastAPI(title="URL Shortener")

DB_SECRET_ARN      = os.getenv("DB_SECRET_ARN", "")
DB_HOST            = os.getenv("DB_HOST", "")
DB_NAME            = os.getenv("DB_NAME", "opslab")
AWS_REGION         = os.getenv("AWS_REGION", "ap-southeast-2")
PARAM_FAILURE_MODE = os.getenv("PARAM_FAILURE_MODE", "")

# SSM failure-mode cache — re-reads at most once per interval so the
# break-fix gameday scenario reacts quickly without hammering SSM.
_failure_cache: dict = {"value": "none", "ts": 0.0}
_FAILURE_TTL = 5  # seconds


def _failure_mode() -> str:
    if not PARAM_FAILURE_MODE:
        return "none"
    now = time.monotonic()
    if now - _failure_cache["ts"] > _FAILURE_TTL:
        try:
            val = boto3.client("ssm", region_name=AWS_REGION).get_parameter(
                Name=PARAM_FAILURE_MODE
            )["Parameter"]["Value"]
            _failure_cache["value"] = val
            _failure_cache["ts"] = now
        except Exception:
            pass
    return _failure_cache["value"]


@app.middleware("http")
async def break_fix_middleware(request: Request, call_next):
    if _failure_mode() == "return_500":
        return Response(
            content='{"detail":"injected failure"}',
            status_code=500,
            media_type="application/json",
        )
    return await call_next(request)


def _db_creds():
    client = boto3.client("secretsmanager", region_name=AWS_REGION)
    return json.loads(client.get_secret_value(SecretId=DB_SECRET_ARN)["SecretString"])


def get_conn():
    creds = _db_creds()
    return psycopg2.connect(
        host=DB_HOST,
        port=5432,
        dbname=DB_NAME,
        user=creds["username"],
        password=creds["password"],
        connect_timeout=5,
    )


@app.on_event("startup")
def startup():
    if not DB_SECRET_ARN:
        logger.warning("DB_SECRET_ARN not set — database endpoints unavailable")
        return
    try:
        conn = get_conn()
        with conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS urls (
                    code       VARCHAR(8)   PRIMARY KEY,
                    url        TEXT         NOT NULL,
                    created_at TIMESTAMPTZ  DEFAULT NOW()
                )
            """)
        conn.close()
        logger.info("Database ready")
    except Exception as exc:
        logger.error("Database init failed", error=str(exc))


class ShortenRequest(BaseModel):
    url: HttpUrl


@app.get("/")
def root():
    return {"service": "url-shortener", "platform": "fargate", "version": "1.0.0"}


@app.get("/healthz")
def healthz():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.post("/shorten", status_code=201)
def shorten(req: ShortenRequest):
    code = uuid.uuid4().hex[:8]
    try:
        conn = get_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO urls (code, url) VALUES (%s, %s)",
                (code, str(req.url)),
            )
        conn.close()
    except Exception as exc:
        logger.error("Shorten failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Database error")
    logger.info("URL shortened", code=code)
    return {"code": code, "short_url": f"/{code}"}


@app.get("/{code}")
def redirect(code: str):
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT url FROM urls WHERE code = %s", (code,))
            row = cur.fetchone()
        conn.close()
    except Exception as exc:
        logger.error("Redirect lookup failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Database error")
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    logger.info("Redirect", code=code)
    return RedirectResponse(url=row[0], status_code=301)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)
