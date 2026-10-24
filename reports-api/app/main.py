import os
from dataclasses import dataclass
from datetime import timezone

import clickhouse_connect
import jwt
from clickhouse_connect.driver.exceptions import ClickHouseError
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, PyJWKClientConnectionError


@dataclass
class Settings:
    issuer: str = "http://localhost:8080/realms/reports-realm"
    jwks_url: str = "http://keycloak:8080/realms/reports-realm/protocol/openid-connect/certs"
    audience: str = "reports-api"
    authorized_party: str = "bionicpro-auth"

    @classmethod
    def from_env(cls):
        return cls(**{name: os.environ[name.upper()] for name in cls.__dataclass_fields__ if name.upper() in os.environ})


class Reports:
    def get(self, issuer, subject):
        with clickhouse_connect.get_client(
            host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            secure=os.getenv("CLICKHOUSE_SECURE", "false").lower() == "true",
            username="reports_reader", password=os.environ["CLICKHOUSE_READER_PASSWORD"],
            database="reports", connect_timeout=3, send_receive_timeout=5,
        ) as client:
            rows = client.query(
                "SELECT customer_id, period_start, period_end, prepared_at, daily "
                "FROM user_reports WHERE issuer={issuer:String} AND subject={subject:String} LIMIT 1",
                parameters={"issuer": issuer, "subject": subject},
            ).result_rows
        if not rows:
            return None
        customer, start, end, prepared, daily = rows[0]
        # clickhouse-connect decodes named Tuple elements as dictionaries.
        return {"customer_id": customer, "period_start": start, "period_end": end.replace(tzinfo=timezone.utc),
                "prepared_at": prepared.replace(tzinfo=timezone.utc), "daily": daily}


def create_app(settings=None, reports=None, keys=None):
    settings = settings or Settings.from_env()
    reports = reports or Reports()
    keys = keys or PyJWKClient(settings.jwks_url, lifespan=300, timeout=3)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    bearer = HTTPBearer(auto_error=False)

    @app.middleware("http")
    async def no_cache(request, call_next):
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "Pragma": "no-cache",
                                 "X-Content-Type-Options": "nosniff"})
        return response

    def identity(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
        if not credentials:
            raise HTTPException(401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"})
        try:
            key = keys.get_signing_key_from_jwt(credentials.credentials).key
            claims = jwt.decode(credentials.credentials, key, algorithms=["RS256"],
                                audience=settings.audience, issuer=settings.issuer,
                                options={"require": ["exp", "iat", "iss", "aud", "sub", "azp", "typ"]})
            if (claims["typ"] != "Bearer" or claims["azp"] != settings.authorized_party
                    or not isinstance(claims["sub"], str) or not claims["sub"]):
                raise jwt.InvalidTokenError()
            return claims
        except PyJWKClientConnectionError:
            raise HTTPException(503, "Identity provider unavailable")
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            raise HTTPException(401, "Invalid access token", headers={"WWW-Authenticate": "Bearer"})

    @app.get("/reports")
    def get_report(request: Request, claims=Depends(identity)):
        # There is no endpoint accepting somebody else's customer ID, including for administrators.
        if request.query_params:
            raise HTTPException(400, "Report owner is determined by the access token")
        try:
            report = reports.get(claims["iss"], claims["sub"])
        except (ClickHouseError, OSError):
            raise HTTPException(503, "Report storage unavailable")
        if report is None:
            raise HTTPException(404, "Report not prepared or customer not linked in CRM")
        return report

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
