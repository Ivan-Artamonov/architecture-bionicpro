"""Backend-for-frontend OAuth code + PKCE flow. No IdP token reaches the browser."""
import base64
import hashlib
import os
import secrets
import time
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from fastapi import Cookie, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

app = FastAPI(title="bionicpro-auth")
PUBLIC = os.getenv("PUBLIC_ORIGIN", "http://localhost:3000").rstrip("/")
KC_PUBLIC = os.getenv("KEYCLOAK_PUBLIC_URL", "http://localhost:8080").rstrip("/")
KC_INTERNAL = os.getenv("KEYCLOAK_INTERNAL_URL", "http://keycloak:8080").rstrip("/")
REALM = os.getenv("KEYCLOAK_REALM", "reports-realm")
CLIENT = os.getenv("KEYCLOAK_CLIENT_ID", "bionicpro-auth")
SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "")
INTERNAL_SECRET = os.getenv("INTERNAL_API_SECRET", "")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
SESSION_SECONDS = 3600
FERNET_KEY = os.getenv("SESSION_ENCRYPTION_KEY", "")
if not FERNET_KEY or not INTERNAL_SECRET or not SECRET:
    raise RuntimeError("Set SESSION_ENCRYPTION_KEY, INTERNAL_API_SECRET and KEYCLOAK_CLIENT_SECRET")
crypt = Fernet(FERNET_KEY.encode())
pending = {}  # state -> (verifier, created); use shared storage when scaling out
sessions = {}  # opaque session id -> encrypted tokens and identity, expiry


def oidc(path: str, internal: bool = False) -> str:
    return f"{KC_INTERNAL if internal else KC_PUBLIC}/realms/{REALM}/protocol/openid-connect/{path}"


def set_cookie(response: Response, sid: str):
    response.set_cookie("bionicpro_session", sid, max_age=SESSION_SECONDS,
                        httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/")


@app.get("/auth/login")
async def login(idp: str = ""):
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(32)
    pending[state] = (verifier, time.time())
    args = {"client_id": CLIENT, "response_type": "code", "scope": "openid profile email",
            "redirect_uri": PUBLIC + "/auth/callback", "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256"}
    if idp == "yandex":
        args["kc_idp_hint"] = "yandex"
    response = RedirectResponse(oidc("auth") + "?" + urlencode(args))
    response.set_cookie("bionicpro_login_state", state, max_age=300,
                        httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/auth/callback")
    return response


@app.get("/auth/callback")
async def callback(code: str, state: str, bionicpro_login_state: str | None = Cookie(None)):
    if not bionicpro_login_state or not secrets.compare_digest(state, bionicpro_login_state):
        raise HTTPException(400, "Login state mismatch")
    entry = pending.pop(state, None)
    if not entry or time.time() - entry[1] > 300:
        raise HTTPException(400, "Invalid or expired login state")
    async with httpx.AsyncClient(timeout=10) as client:
        token_response = await client.post(oidc("token", True), data={
            "grant_type": "authorization_code", "client_id": CLIENT,
            "client_secret": SECRET, "code": code, "code_verifier": entry[0],
            "redirect_uri": PUBLIC + "/auth/callback"})
        token_response.raise_for_status()
        tokens = token_response.json()
        user_response = await client.get(oidc("userinfo", True),
                                         headers={"Authorization": "Bearer " + tokens["access_token"]})
        user_response.raise_for_status()
        user = user_response.json()
    sid = secrets.token_urlsafe(32)
    sessions[sid] = (crypt.encrypt(tokens["refresh_token"].encode()),
                     crypt.encrypt(tokens["access_token"].encode()),
                     time.time() + tokens["expires_in"], time.time() + SESSION_SECONDS,
                     user["sub"], user.get("preferred_username", ""))
    response = RedirectResponse(PUBLIC + "/")
    response.delete_cookie("bionicpro_login_state", path="/auth/callback")
    set_cookie(response, sid)
    return response


async def validated(sid: str):
    record = sessions.get(sid)
    if not record or time.time() > record[3]:
        sessions.pop(sid, None)
        raise HTTPException(401, "Session expired")
    if time.time() + 10 >= record[2]:
        async with httpx.AsyncClient(timeout=10) as client:
            result = await client.post(oidc("token", True), data={
                "grant_type": "refresh_token", "client_id": CLIENT,
                "client_secret": SECRET, "refresh_token": crypt.decrypt(record[0]).decode()})
            if result.status_code != 200:
                sessions.pop(sid, None)
                raise HTTPException(401, "Refresh failed")
            tokens = result.json()
        record = (crypt.encrypt(tokens.get("refresh_token", crypt.decrypt(record[0]).decode()).encode()),
                  crypt.encrypt(tokens["access_token"].encode()),
                  time.time() + tokens["expires_in"], record[3], record[4], record[5])
    new_sid = secrets.token_urlsafe(32)
    sessions.pop(sid, None)
    sessions[new_sid] = record
    return new_sid, record


@app.get("/auth/session")
async def session(response: Response, bionicpro_session: str | None = Cookie(None)):
    if not bionicpro_session:
        raise HTTPException(401)
    sid, record = await validated(bionicpro_session)
    set_cookie(response, sid)
    return {"subject": record[4], "username": record[5]}


@app.post("/auth/logout")
async def logout(request: Request, response: Response, bionicpro_session: str | None = Cookie(None)):
    if request.headers.get("origin") != PUBLIC:
        raise HTTPException(403)
    if bionicpro_session:
        sessions.pop(bionicpro_session, None)
    response.delete_cookie("bionicpro_session", path="/")
    return {"ok": True}


@app.post("/internal/validate")
async def internal_validate(request: Request, x_internal_secret: str | None = Header(None)):
    if not secrets.compare_digest(x_internal_secret or "", INTERNAL_SECRET):
        raise HTTPException(403)
    sid = request.cookies.get("bionicpro_session")
    if not sid:
        raise HTTPException(401)
    new_sid, record = await validated(sid)
    return {"session_id": new_sid, "subject": record[4], "username": record[5]}
