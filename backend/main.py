import os
from typing import Optional

import jwt
import psycopg2
import psycopg2.extras
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

app = FastAPI(title="BionicPRO Reports API")
security = HTTPBearer()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLAP_DSN = os.environ.get(
    "OLAP_DSN", "postgresql://olap:olap@localhost:5434/olap"
)
KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8080")
REALM = os.environ.get("KEYCLOAK_REALM", "reports-realm")

_jwks_client: Optional[PyJWKClient] = None


def get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        url = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/certs"
        _jwks_client = PyJWKClient(url)
    return _jwks_client


def current_username(
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    token = creds.credentials
    try:
        signing_key = get_jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        ) from exc

    username = payload.get("preferred_username") or payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="No username in token")
    return username


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/reports")
def get_my_report(username: str = Depends(current_username)):
    """Отчёт только для текущего пользователя (user_id из JWT)."""
    conn = psycopg2.connect(OLAP_DSN)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT user_id, full_name, email, prosthesis_model,
                       total_steps, total_distance_m, avg_load_kg,
                       sessions_count, last_activity_at, updated_at
                FROM report_mart
                WHERE user_id = %s
                """,
                (username,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    if row["user_id"] != username:
        raise HTTPException(status_code=403, detail="Forbidden")

    report = dict(row)
    for key in ("last_activity_at", "updated_at"):
        if report.get(key) is not None:
            report[key] = report[key].isoformat()
    return report
