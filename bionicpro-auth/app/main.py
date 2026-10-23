import secrets
import time
from contextlib import asynccontextmanager

import httpx
from cryptography.exceptions import InvalidTag
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from redis.asyncio import Redis
from redis.exceptions import RedisError

from .config import Settings
from .oidc import InvalidGrant, OIDC, ProviderError
from .sessions import InvalidSession, SessionBusy, Sessions

COOKIE = "bionicpro_session"
LOGIN_COOKIE = "bionicpro_login"


def create_app(settings=None, redis_client=None, http_client=None):
    settings = settings or Settings.from_env()
    redis = redis_client or Redis.from_url(settings.redis_url, decode_responses=True,
                                           socket_timeout=5, socket_connect_timeout=5)
    http = http_client or httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False)
    sessions = Sessions(settings, redis)
    oidc = OIDC(settings, http)

    @asynccontextmanager
    async def lifespan(app):
        await redis.ping()
        yield
        await http.aclose()
        await redis.aclose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def cookie(response, name, value, ttl):
        response.set_cookie(name, value, max_age=ttl, httponly=True, secure=settings.cookie_secure,
                            samesite="lax", path="/")

    def clear_cookie(response, name):
        response.delete_cookie(name, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")

    @app.middleware("http")
    async def security_headers(request, call_next):
        try:
            response = await call_next(request)
        except (httpx.RequestError, RedisError, ProviderError, SessionBusy):
            response = JSONResponse({"detail": "Authentication service temporarily unavailable"}, status_code=503)
        response.headers.update({"Cache-Control": "no-store", "Pragma": "no-cache",
                                 "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"})
        return response

    @app.exception_handler(InvalidSession)
    async def invalid_session(request, error):
        response = JSONResponse({"detail": "Authentication required"}, status_code=401)
        if error.clear:
            clear_cookie(response, COOKIE)
        return response

    def check_csrf(request, record):
        if (request.headers.get("origin") != settings.origin or
                not secrets.compare_digest(request.headers.get("x-csrf-token", "").encode(), record["csrf"].encode())):
            raise HTTPException(403, "CSRF check failed")

    async def authenticate(request):
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Cross-site request denied")
        async with sessions.locked(request.cookies.get(COOKIE)) as (record, lock):
            if record["expires_at"] <= time.time():
                try:
                    refresh_token = sessions.unseal(record["refresh_token"], record["id"])
                    tokens = await oidc.tokens(grant_type="refresh_token", refresh_token=refresh_token)
                except (InvalidGrant, InvalidTag, ValueError):
                    await sessions.commit(record, lock, delete=True)
                    raise InvalidSession(clear=True)
                sessions.bind_tokens(record, tokens)
            sid, ttl = await sessions.commit(record, lock)
        return record, sid, ttl

    @app.get("/auth/login")
    async def login():
        state, browser, context = await sessions.start_login()
        response = RedirectResponse(oidc.authorization_url(state, context["nonce"], context["verifier"]), status_code=302)
        cookie(response, LOGIN_COOKIE, browser, 300)
        return response

    @app.get("/auth/callback")
    async def callback(request: Request):
        context = await sessions.consume_login(request.query_params.get("state"), request.cookies.get(LOGIN_COOKIE))
        if not context:
            raise HTTPException(400, "Invalid or expired login context")
        code = request.query_params.get("code")
        if request.query_params.get("error") or not code:
            raise HTTPException(400, "Login failed")
        try:
            tokens = await oidc.tokens(grant_type="authorization_code", code=code,
                                       code_verifier=context["verifier"], redirect_uri=settings.callback)
            identity = await oidc.identity(tokens, context["nonce"])
        except (InvalidGrant, ProviderError):
            raise HTTPException(400, "Login validation failed")
        # A new login never adopts a pre-login SID. Retire the previous application's session too.
        if request.cookies.get(COOKIE):
            try:
                async with sessions.locked(request.cookies[COOKIE]) as (old, lock):
                    await sessions.commit(old, lock, delete=True)
            except InvalidSession:
                pass
        sid, ttl = await sessions.create(identity, tokens)
        response = RedirectResponse(settings.origin + "/", status_code=302)
        cookie(response, COOKIE, sid, ttl)
        clear_cookie(response, LOGIN_COOKIE)
        return response

    @app.get("/api/session")
    async def current_session(request: Request):
        record, sid, ttl = await authenticate(request)
        response = JSONResponse({"user": record["identity"], "csrf_token": record["csrf"]})
        cookie(response, COOKIE, sid, ttl)
        return response

    @app.get("/api/reports")
    async def reports(request: Request):
        record, sid, ttl = await authenticate(request)
        response = JSONResponse({"detail": "Reports API is not configured"}, status_code=503)
        if settings.api_url:
            try:
                upstream = await http.get(settings.api_url + "/reports",
                                          headers={"Authorization": "Bearer " + record["access_token"]})
                if upstream.status_code == 200:
                    response = Response(upstream.content, media_type=upstream.headers.get("content-type", "application/octet-stream"),
                                        headers={"Content-Disposition": 'attachment; filename="report.pdf"'})
                else:
                    status = upstream.status_code if upstream.status_code in (401, 403, 404) else 502
                    response = JSONResponse({"detail": "Report unavailable"}, status_code=status)
            except httpx.RequestError:
                response = JSONResponse({"detail": "Reports API unavailable"}, status_code=503)
        cookie(response, COOKIE, sid, ttl)  # Also deliver the new SID on upstream errors.
        return response

    @app.post("/auth/logout")
    async def logout(request: Request):
        async with sessions.locked(request.cookies.get(COOKIE)) as (record, lock):
            check_csrf(request, record)
            refresh_token = sessions.unseal(record["refresh_token"], record["id"])
            await sessions.commit(record, lock, delete=True)
        response = Response(status_code=204)
        try:
            await oidc.revoke(refresh_token)
        except (httpx.RequestError, ProviderError):
            response = JSONResponse({"detail": "Local logout completed; token revocation unavailable"}, status_code=503)
        clear_cookie(response, COOKIE)
        return response

    @app.get("/health")
    async def health():
        await redis.ping()
        return {"status": "ok"}

    return app
