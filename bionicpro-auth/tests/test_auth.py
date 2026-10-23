import base64
import hashlib
import json
import os
import secrets
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from app.config import Settings
from app.main import COOKIE, LOGIN_COOKIE, create_app
from app.sessions import digest


@pytest.fixture
def env():
    url = os.getenv("TEST_REDIS_URL")
    if not url:
        pytest.skip("Set TEST_REDIS_URL to an isolated Redis instance")
    prefix = "test-bionicpro:" + secrets.token_hex(8) + ":"
    settings = Settings(client_secret="test-secret", encryption_key=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
                        origin="https://app.test", issuer="https://sso.test/realms/reports-realm",
                        keycloak_internal="http://provider/realms/reports-realm", redis_url=url,
                        redis_prefix=prefix, api_url="http://reports")
    db = Redis.from_url(url, decode_responses=True)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    jwk.update(kid="test", use="sig", alg="RS256")
    fake = SimpleNamespace(nonce="", challenge="", refreshes=0, code_exchanges=0, revoke=0,
                           reject_refresh=False, invalid_nonce=False)

    async def provider(request):
        if request.url.host == "reports":
            assert request.headers["authorization"].startswith("Bearer access-")
            assert "cookie" not in request.headers
            return httpx.Response(200, content=b"%PDF-test", headers={"Content-Type": "application/pdf"})
        if request.url.path.endswith("/certs"):
            return httpx.Response(200, json={"keys": [jwk]})
        assert request.headers["authorization"] == "Basic " + base64.b64encode(b"bionicpro-auth:test-secret").decode()
        if request.url.path.endswith("/revoke"):
            fake.revoke += 1
            return httpx.Response(200)
        data = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        if data["grant_type"] == "refresh_token":
            fake.refreshes += 1
            if fake.reject_refresh:
                return httpx.Response(400, json={"error": "invalid_grant"})
            assert data["refresh_token"] == "refresh-initial"
            return httpx.Response(200, json={"access_token": "access-refreshed", "refresh_token": "refresh-rotated",
                                            "expires_in": 120, "token_type": "Bearer"})
        fake.code_exchanges += 1
        assert data["grant_type"] == "authorization_code"
        assert data["redirect_uri"] == settings.callback
        challenge = base64.urlsafe_b64encode(hashlib.sha256(data["code_verifier"].encode()).digest()).decode().rstrip("=")
        assert challenge == fake.challenge
        claims = {"iss": settings.issuer, "aud": settings.client_id, "sub": "user-id", "iat": int(time.time()),
                  "exp": int(time.time()) + 120, "nonce": "wrong" if fake.invalid_nonce else fake.nonce,
                  "preferred_username": "user1"}
        return httpx.Response(200, json={"access_token": "access-initial", "refresh_token": "refresh-initial",
                                        "expires_in": 120, "token_type": "Bearer",
                                        "id_token": jwt.encode(claims, private, algorithm="RS256", headers={"kid": "test"})})

    http = httpx.AsyncClient(transport=httpx.MockTransport(provider))
    app = create_app(settings, AsyncRedis.from_url(url, decode_responses=True), http)
    with TestClient(app, base_url=settings.origin) as client:
        def begin():
            response = client.get("/auth/login", follow_redirects=False)
            query = parse_qs(urlsplit(response.headers["location"]).query)
            assert query["code_challenge_method"] == ["S256"]
            fake.nonce, fake.challenge = query["nonce"][0], query["code_challenge"][0]
            return query["state"][0]

        def login():
            state = begin()
            response = client.get("/auth/callback", params={"state": state, "code": "good"}, follow_redirects=False)
            assert response.status_code == 302, response.text
            return client.cookies.get(COOKIE)

        def record(sid):
            record_id = db.get(prefix + "sid:" + digest(sid))
            key = prefix + "session:" + record_id
            return key, json.loads(db.get(key))

        def expire_access(sid):
            key, data = record(sid)
            data["expires_at"] = time.time() - 1
            db.set(key, json.dumps(data), ex=1800)

        yield SimpleNamespace(client=client, db=db, settings=settings, fake=fake, begin=begin,
                              login=login, record=record, expire_access=expire_access)
    keys = list(db.scan_iter(prefix + "*"))
    if keys:
        db.delete(*keys)
    db.close()


def test_tokens_stay_server_side_and_cookies_are_secure(env):
    sid = env.login()
    response = env.client.get("/api/session")
    assert response.status_code == 200
    assert set(response.json()) == {"user", "csrf_token"}
    assert "access-initial" not in response.text and "refresh-initial" not in response.text
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie and "Domain=" not in cookie
    assert response.headers["cache-control"] == "no-store"
    assert env.client.cookies.get(COOKIE) != sid
    key, record = env.record(env.client.cookies.get(COOKIE))
    assert record["access_token"] == "access-initial"
    assert record["refresh_token"] != "refresh-initial"
    assert 120 < env.db.ttl(key) <= 1800
    assert sid not in " ".join(env.db.scan_iter(env.settings.redis_prefix + "*"))


def test_rotation_while_access_token_valid_and_stale_request_does_not_clear_cookie(env):
    old = env.login()
    _, before = env.record(old)
    response = env.client.get("/api/session")
    new = env.client.cookies.get(COOKIE)
    _, after = env.record(new)
    assert response.status_code == 200 and new != old and env.fake.refreshes == 0
    assert before["created_at"] == after["created_at"]
    assert before["access_token"] == after["access_token"]
    stale = env.client.get("/api/session", headers={"Cookie": COOKIE + "=" + old})
    assert stale.status_code == 401 and "set-cookie" not in stale.headers
    assert env.client.get("/api/session").status_code == 200


def test_refresh_stores_both_new_tokens_and_rotates_sid(env):
    old = env.login()
    env.expire_access(old)
    response = env.client.get("/api/reports")
    assert response.status_code == 200 and response.content == b"%PDF-test"
    new = env.client.cookies.get(COOKIE)
    assert new != old and env.fake.refreshes == 1
    _, record = env.record(new)
    assert record["access_token"] == "access-refreshed"
    from app.sessions import Sessions
    store = Sessions(env.settings, None)
    assert store.unseal(record["refresh_token"], record["id"]) == "refresh-rotated"


def test_revoked_refresh_token_ends_session(env):
    old = env.login()
    env.expire_access(old)
    env.fake.reject_refresh = True
    response = env.client.get("/api/session")
    assert response.status_code == 401 and "Max-Age=0" in response.headers["set-cookie"]
    assert env.db.get(env.settings.redis_prefix + "sid:" + digest(old)) is None
    assert not list(env.db.scan_iter(env.settings.redis_prefix + "session:*"))


def test_state_browser_binding_and_callback_replay(env):
    state = env.begin()
    browser = env.client.cookies.get(LOGIN_COOKIE)
    params = {"state": state, "code": "good"}
    assert env.client.get("/auth/callback", params={**params, "state": "wrong"}).status_code == 400
    assert env.client.get("/auth/callback", params=params, headers={"Cookie": LOGIN_COOKIE + "=other"}).status_code == 400
    response = env.client.get("/auth/callback", params=params, headers={"Cookie": LOGIN_COOKIE + "=" + browser}, follow_redirects=False)
    assert response.status_code == 302
    assert env.client.get("/auth/callback", params=params).status_code == 400
    assert env.fake.code_exchanges == 1


def test_wrong_nonce_does_not_create_session(env):
    state = env.begin()
    env.fake.invalid_nonce = True
    response = env.client.get("/auth/callback", params={"state": state, "code": "good"})
    assert response.status_code == 400 and not env.client.cookies.get(COOKIE)


def test_logout_requires_csrf_and_invalidates_session(env):
    env.login()
    response = env.client.get("/api/session")
    sid = env.client.cookies.get(COOKIE)
    assert env.client.post("/auth/logout").status_code == 403
    headers = {"Origin": env.settings.origin, "X-CSRF-Token": response.json()["csrf_token"]}
    assert env.client.post("/auth/logout", headers={**headers, "Origin": "https://evil.test"}).status_code == 403
    assert env.client.post("/auth/logout", headers=headers).status_code == 204
    assert env.fake.revoke == 1
    assert env.client.get("/api/session", headers={"Cookie": COOKIE + "=" + sid}).status_code == 401


def test_realm_configuration():
    from pathlib import Path
    realm = json.loads((Path(__file__).parents[2] / "keycloak/realm-export.json").read_text())
    client = next(c for c in realm["clients"] if c["clientId"] == "bionicpro-auth")
    assert realm["accessTokenLifespan"] <= 120
    assert realm["revokeRefreshToken"] and realm["refreshTokenMaxReuse"] == 0
    assert realm["ssoSessionIdleTimeout"] > realm["accessTokenLifespan"]
    assert not client["publicClient"] and not client["directAccessGrantsEnabled"]
    assert client["attributes"]["pkce.code.challenge.method"] == "S256"
    assert client["redirectUris"] == ["http://localhost:3000/auth/callback"]
    assert realm["otpPolicyType"] == "totp" and realm["otpPolicyDigits"] == 6
    assert realm["otpPolicyPeriod"] == 30
    assert realm["otpPolicyAlgorithm"] == "HmacSHA1" and not realm["otpPolicyCodeReusable"]
    flows = {flow["alias"]: flow for flow in realm["authenticationFlows"]}
    browser = flows[realm["browserFlow"]]
    forms = flows[next(e["flowAlias"] for e in browser["authenticationExecutions"] if e["authenticatorFlow"])]
    otp = next(e for e in forms["authenticationExecutions"] if e["authenticator"] == "auth-otp-form")
    assert otp["requirement"] == "REQUIRED"
    configure = next(a for a in realm["requiredActions"] if a["alias"] == "CONFIGURE_TOTP")
    assert configure["enabled"] and configure["defaultAction"]
