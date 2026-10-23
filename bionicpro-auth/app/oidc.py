import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt


class InvalidGrant(Exception):
    pass


class ProviderError(Exception):
    pass


class OIDC:
    def __init__(self, settings, http):
        self.settings = settings
        self.http = http
        self.endpoint = settings.keycloak_internal + "/protocol/openid-connect"

    def authorization_url(self, state, nonce, verifier, provider=None):
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        params = {
            "client_id": self.settings.client_id, "redirect_uri": self.settings.callback,
            "response_type": "code", "scope": "openid profile", "state": state,
            "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256",
        }
        if provider:
            params["kc_idp_hint"] = provider
            params["prompt"] = "login"  # Do not silently reuse a local-user SSO session for the Yandex button.
        return self.settings.issuer + "/protocol/openid-connect/auth?" + urlencode(params)

    async def tokens(self, **data):
        response = await self.http.post(self.endpoint + "/token", data=data,
                                        auth=(self.settings.client_id, self.settings.client_secret))
        if response.status_code == 400 and response.json().get("error") == "invalid_grant":
            raise InvalidGrant()
        if response.status_code != 200:
            raise ProviderError()
        try:
            tokens = response.json()
            lifetime = int(tokens["expires_in"])
            if (not 0 < lifetime <= 120 or not tokens["access_token"] or not tokens["refresh_token"]
                    or tokens["token_type"].lower() != "bearer"):
                raise ValueError()
            tokens["expires_at"] = time.time() + lifetime - 5
            return tokens
        except (KeyError, TypeError, ValueError) as error:
            raise ProviderError() from error

    async def identity(self, tokens, nonce):
        try:
            encoded = tokens["id_token"]
            header = jwt.get_unverified_header(encoded)
            response = await self.http.get(self.endpoint + "/certs")
            response.raise_for_status()
            key = next(k for k in response.json()["keys"] if k["kid"] == header["kid"] and k.get("use") == "sig")
            claims = jwt.decode(encoded, jwt.PyJWK.from_dict(key).key, algorithms=["RS256"],
                                audience=self.settings.client_id, issuer=self.settings.issuer,
                                options={"require": ["exp", "iat", "sub", "nonce", "iss", "aud"]})
            if not secrets.compare_digest(claims["nonce"], nonce):
                raise ValueError()
            if claims.get("azp", self.settings.client_id) != self.settings.client_id:
                raise ValueError()
            if "at_hash" in claims:
                digest = hashlib.sha256(tokens["access_token"].encode()).digest()[:16]
                if not secrets.compare_digest(claims["at_hash"], base64.urlsafe_b64encode(digest).decode().rstrip("=")):
                    raise ValueError()
            identity = {"sub": claims["sub"], "iss": claims["iss"],
                        "username": claims.get("preferred_username", claims["sub"])}
            if claims.get("identity_provider") == "yandex":
                if not isinstance(claims.get("yandex_id"), str) or not claims["yandex_id"].isdigit():
                    raise ValueError()
                identity.update(provider="yandex", yandex_id=claims["yandex_id"])
            return identity
        except (jwt.PyJWTError, KeyError, TypeError, ValueError, StopIteration, httpx.HTTPStatusError) as error:
            raise ProviderError() from error

    async def revoke(self, refresh_token):
        response = await self.http.post(self.endpoint + "/revoke",
                                        data={"token": refresh_token, "token_type_hint": "refresh_token"},
                                        auth=(self.settings.client_id, self.settings.client_secret))
        if response.status_code != 200:
            raise ProviderError()

    async def yandex_profile(self, record):
        response = await self.http.get(self.settings.keycloak_internal + "/broker/yandex/token",
                                       headers={"Authorization": "Bearer " + record["access_token"]})
        if response.status_code != 200:
            raise ProviderError()
        try:
            token = response.json()["access_token"]
            if not isinstance(token, str) or not token:
                raise ValueError()
            response = await self.http.get("https://login.yandex.ru/info", params={"format": "json"},
                                           headers={"Authorization": "OAuth " + token})
            if response.status_code != 200:
                raise ProviderError()
            profile = response.json()
            if profile.get("id") != record["identity"]["yandex_id"]:
                raise ValueError()
            fields = ("id", "login", "first_name", "last_name", "display_name", "default_email")
            return {key: value for key in fields if isinstance(value := profile.get(key), str)}
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise ProviderError() from error
