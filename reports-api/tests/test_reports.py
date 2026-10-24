import time
from types import SimpleNamespace
from contextlib import nullcontext
from datetime import date, datetime

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.main import Reports, Settings, create_app


@pytest.fixture
def env():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = Settings()
    calls = []

    class Reports:
        def get(self, issuer, subject):
            calls.append((issuer, subject))
            return {"customer_id": {"alice": 1, "bob": 2}[subject], "daily": []} if subject in ("alice", "bob") else None

    keys = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private.public_key()))
    client = TestClient(create_app(settings, Reports(), keys))

    def token(**overrides):
        claims = {"iss": settings.issuer, "aud": settings.audience, "sub": "alice", "typ": "Bearer",
                  "azp": settings.authorized_party, "iat": int(time.time()), "exp": int(time.time()) + 120}
        claims.update(overrides)
        return {"Authorization": "Bearer " + jwt.encode(claims, private, algorithm="RS256")}

    return SimpleNamespace(client=client, token=token, calls=calls)


def test_each_user_sees_only_own_report_including_administrator(env):
    for subject, customer in (("alice", 1), ("bob", 2)):
        response = env.client.get("/reports", headers=env.token(sub=subject, realm_access={"roles": ["administrator"]}))
        assert response.status_code == 200 and response.json()["customer_id"] == customer
        assert response.headers["cache-control"] == "no-store"
    assert [subject for issuer, subject in env.calls] == ["alice", "bob"]


@pytest.mark.parametrize("claims", [
    {"exp": 1}, {"iss": "https://foreign-sso"}, {"aud": "other-api"},
    {"typ": "ID"}, {"azp": "other-client"}, {"sub": ""},
])
def test_invalid_tokens_are_rejected_before_storage(env, claims):
    assert env.client.get("/reports", headers=env.token(**claims)).status_code == 401
    assert not env.calls


def test_missing_and_tampered_token(env):
    assert env.client.get("/reports").status_code == 401
    token = env.token()["Authorization"]
    parts = token.split('.')
    parts[1] = parts[1][::-1]
    assert env.client.get("/reports", headers={"Authorization": '.'.join(parts)}).status_code == 401
    assert not env.calls


@pytest.mark.parametrize("query", ["user_id=bob", "subject=bob", "customer_id=2"])
def test_owner_cannot_be_overridden(env, query):
    assert env.client.get("/reports?" + query, headers=env.token()).status_code == 400
    assert not env.calls


def test_unknown_customer_has_no_report(env):
    assert env.client.get("/reports", headers=env.token(sub="unknown")).status_code == 404


def test_storage_uses_bound_identity_and_preserves_named_metrics(monkeypatch):
    daily = [{"day": date(2026, 10, 23), "prosthesis_id": "BP-001", "samples": 10, "avg_response_ms": 65.5}]

    def query(sql, parameters):
        assert "issuer={issuer:String} AND subject={subject:String}" in sql
        assert parameters == {"issuer": "trusted-issuer", "subject": "alice' OR 1=1"}
        return SimpleNamespace(result_rows=[(1, date(2026, 9, 23), datetime(2026, 10, 23), datetime(2026, 10, 23), daily, "snapshot")])

    monkeypatch.setenv("CLICKHOUSE_READER_PASSWORD", "test-password")
    monkeypatch.setattr("app.main.clickhouse_connect.get_client", lambda **kwargs: nullcontext(SimpleNamespace(query=query)))
    report = Reports().get("trusted-issuer", "alice' OR 1=1")
    assert report["daily"] == daily
    assert report["period_end"].utcoffset().total_seconds() == 0
