"""Reports are addressed only by the authenticated Keycloak subject."""
import hashlib
import hmac
import json
import os
import time
from datetime import date, datetime, timezone
from urllib.parse import quote

import boto3
import httpx
from botocore.exceptions import ClientError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

app = FastAPI(title="BionicPRO reports")
AUTH = os.getenv("AUTH_INTERNAL_URL", "http://auth:8001")
SECRET = os.environ["INTERNAL_API_SECRET"]
SIGNING_KEY = os.environ["REPORT_LINK_SECRET"].encode()
CH = os.getenv("CLICKHOUSE_URL", "http://clickhouse:8123")
BUCKET = os.getenv("S3_BUCKET", "reports")
s3 = boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT", "http://minio:9000"),
                  aws_access_key_id=os.environ["MINIO_ROOT_USER"],
                  aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"])
watermark_cache: tuple[float, dict] | None = None


@app.middleware("http")
async def propagate_session_cookie(request: Request, call_next):
    response = await call_next(request)
    sid = getattr(request.state, "rotated_sid", None)
    if sid:
        response.set_cookie("bionicpro_session", sid, max_age=3600,
                            httponly=True, secure=os.getenv("COOKIE_SECURE", "true") == "true",
                            samesite="lax", path="/")
    return response


async def identity(request: Request) -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        result = await client.post(AUTH + "/internal/validate", cookies=request.cookies,
                                   headers={"X-Internal-Secret": SECRET})
    if result.status_code != 200:
        raise HTTPException(401, "Authentication required")
    data = result.json()
    request.state.rotated_sid = data["session_id"]
    return data["subject"]


def sign(key: str, expires: int) -> str:
    return hmac.new(SIGNING_KEY, f"{key}:{expires}".encode(), hashlib.sha256).hexdigest()


async def ch_query(query: str, params: dict) -> list[dict]:
    async with httpx.AsyncClient(timeout=20) as client:
        result = await client.post(CH, params=params, content=query + " FORMAT JSONEachRow")
        result.raise_for_status()
    return [json.loads(line) for line in result.text.splitlines() if line]


async def current_watermark() -> dict:
    global watermark_cache
    if watermark_cache and time.time() < watermark_cache[0]:
        return watermark_cache[1]
    rows = await ch_query("""SELECT max(processed_through) AS watermark,
        max(completed_at) AS version FROM etl_watermark""", {})
    value = rows[0] if rows else {}
    watermark_cache = (time.time() + 60, value)
    return value


@app.get("/reports")
async def report(request: Request, through: date):
    subject = await identity(request)
    if through >= datetime.now(timezone.utc).date():
        raise HTTPException(400, "Choose an already processed date")
    # The watermark comes from completed ETL runs, never from the requested date.
    watermark = await current_watermark()
    latest = watermark.get("watermark")
    if not latest or latest == "1970-01-01" or through.isoformat() > latest:
        raise HTTPException(409, "Requested period has not been processed")
    # Immutable versioned key: a new ETL watermark creates a new object and CDN URL.
    digest = hashlib.sha256(subject.encode()).hexdigest()
    version = hashlib.sha256(str(watermark["version"]).encode()).hexdigest()[:16]
    key = f"{digest}/{through.isoformat()}/{version}/report.json"
    try:
        s3.head_object(Bucket=BUCKET, Key=key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("404", "NoSuchKey", "NotFound"):
            raise
        rows = await ch_query("""SELECT customer_subject, prosthesis_id, period_end, signal_count,
            movement_count FROM report_mart FINAL
            WHERE customer_subject = {subject:String} AND period_end <= {through:Date}
            ORDER BY period_end, prosthesis_id""", {"param_subject": subject, "param_through": through.isoformat()})
        if not rows:
            raise HTTPException(404, "No report for this account")
        data = {"through": through.isoformat(), "processed_through": latest,
                "subject": subject, "rows": rows}
        s3.put_object(Bucket=BUCKET, Key=key,
                      Body=json.dumps(data, ensure_ascii=False).encode(),
                      ContentType="application/json", CacheControl="private, max-age=60")
    expires = int(time.time()) + 300
    return {"url": f"/cdn/{quote(key)}?expires={expires}&signature={sign(key, expires)}"}


@app.get("/files/{key:path}")
async def file(key: str, expires: int, signature: str):
    if expires < time.time() or expires > time.time() + 300:
        raise HTTPException(403)
    if not hmac.compare_digest(signature, sign(key, expires)):
        raise HTTPException(403)
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=key)
    except ClientError:
        raise HTTPException(404)
    return StreamingResponse(obj["Body"].iter_chunks(), media_type="application/json",
                             headers={"Cache-Control": "public, max-age=60"})
