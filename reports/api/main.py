from __future__ import annotations

import os
from datetime import date
from typing import Any

import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from pydantic import BaseModel

import clickhouse_connect


CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DATABASE = os.getenv("CLICKHOUSE_DATABASE", "reports")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
KEYCLOAK_ISSUER = os.getenv(
    "KEYCLOAK_ISSUER",
    "http://localhost:8080/realms/reports-realm",
)
KEYCLOAK_JWKS_URL = os.getenv(
    "KEYCLOAK_JWKS_URL",
    "http://localhost:8080/realms/reports-realm/protocol/openid-connect/certs",
)


class ReportItem(BaseModel):
    prosthesis_id: str
    day: date
    product_model: str
    events_count: int
    avg_reaction_time_ms: float
    p95_reaction_time_ms: float
    avg_battery_level: float
    avg_signal_quality: float


class ReportResponse(BaseModel):
    period_from: date | None
    period_to: date | None
    processed_until: date
    items: list[ReportItem]


class AvailableReport(BaseModel):
    day: date
    prostheses_count: int
    events_count: int
    avg_reaction_time_ms: float
    avg_battery_level: float
    avg_signal_quality: float


security = HTTPBearer(auto_error=False)
jwks_client = PyJWKClient(KEYCLOAK_JWKS_URL)
app = FastAPI(title="BionicPRO Reports API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Authorization", "Content-Type"],
)


def current_user_sub(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256"],
            issuer=KEYCLOAK_ISSUER,
            options={"verify_aud": False},
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token") from exc

    if not claims.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has no subject")
    return str(claims["sub"])


def clickhouse_client():
    return clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        database=CLICKHOUSE_DATABASE,
        username=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
    )


def processed_until(client) -> date:
    result = client.query(
        """
        SELECT processed_until
        FROM etl_processing_state
        WHERE pipeline_name = {pipeline:String}
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        parameters={"pipeline": "reports_etl"},
    ).result_rows
    if not result:
        raise HTTPException(status_code=503, detail="Report data is not ready")
    value = result[0][0]
    return value if isinstance(value, date) else date.fromisoformat(str(value))

@app.get("/reports/available", response_model=list[AvailableReport])
def available_reports(user_id: str = Depends(current_user_sub)) -> list[AvailableReport]:
    client = clickhouse_client()
    rows = client.query(
        """
        SELECT
            day,
            uniqExact(prosthesis_id) AS prostheses_count,
            sum(events_count) AS events_count,
            avg(avg_reaction_time_ms) AS avg_reaction_time_ms,
            avg(avg_battery_level) AS avg_battery_level,
            avg(avg_signal_quality) AS avg_signal_quality
        FROM prosthesis_report_mart
        WHERE user_id = {user_id:String}
        GROUP BY day
        ORDER BY day DESC
        LIMIT 10
        """,
        parameters={"user_id": user_id},
    ).result_rows
    return [
        AvailableReport(
            day=row[0],
            prostheses_count=row[1],
            events_count=row[2],
            avg_reaction_time_ms=row[3],
            avg_battery_level=row[4],
            avg_signal_quality=row[5],
        )
        for row in rows
    ]


@app.get("/reports", response_model=ReportResponse)
def reports(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    user_id: str = Depends(current_user_sub),
) -> ReportResponse:
    if from_ and to and from_ > to:
        raise HTTPException(status_code=422, detail="from must not be after to")

    client = clickhouse_client()
    available_until = processed_until(client)
    if to and to > available_until:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Requested period has not been processed",
                "processed_until": available_until.isoformat(),
            },
        )

    filters = ["user_id = {user_id:String}"]
    parameters: dict[str, Any] = {"user_id": user_id}
    if from_:
        filters.append("day >= {from_date:Date}")
        parameters["from_date"] = from_.isoformat()
    if to:
        filters.append("day <= {to_date:Date}")
        parameters["to_date"] = to.isoformat()

    rows = client.query(
        f"""
        SELECT prosthesis_id, day, product_model, events_count,
               avg_reaction_time_ms, p95_reaction_time_ms,
               avg_battery_level, avg_signal_quality
        FROM prosthesis_report_mart
        WHERE {' AND '.join(filters)}
        ORDER BY day, prosthesis_id
        """,
        parameters=parameters,
    ).result_rows

    items = [
        ReportItem(
            prosthesis_id=row[0],
            day=row[1],
            product_model=row[2],
            events_count=row[3],
            avg_reaction_time_ms=row[4],
            p95_reaction_time_ms=row[5],
            avg_battery_level=row[6],
            avg_signal_quality=row[7],
        )
        for row in rows
    ]
    return ReportResponse(
        period_from=from_,
        period_to=to or available_until,
        processed_until=available_until,
        items=items,
    )
