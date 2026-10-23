import base64
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    client_secret: str
    encryption_key: str
    origin: str = "http://localhost:3000"
    issuer: str = "http://localhost:8080/realms/reports-realm"
    keycloak_internal: str = "http://keycloak:8080/realms/reports-realm"
    client_id: str = "bionicpro-auth"
    redis_url: str = "redis://auth-redis:6379/0"
    redis_prefix: str = "bionicpro:"
    api_url: str = ""
    profiles_database_url: str = ""
    cookie_secure: bool = True
    idle_seconds: int = 1800
    absolute_seconds: int = 28800

    def __post_init__(self):
        if not self.client_secret or len(base64.urlsafe_b64decode(self.encryption_key)) != 32:
            raise ValueError("Client secret and a base64-encoded 256-bit encryption key are required")
        if not 120 < self.idle_seconds <= self.absolute_seconds <= 28800:
            raise ValueError("Session limits must be longer than 120 seconds and at most 8 hours")

    @property
    def callback(self):
        return self.origin + "/auth/callback"

    @classmethod
    def from_env(cls):
        secure = os.getenv("COOKIE_SECURE", "true").lower()
        if secure not in ("true", "false"):
            raise ValueError("COOKIE_SECURE must be true or false")
        return cls(
            client_secret=os.environ["BIONICPRO_AUTH_CLIENT_SECRET"],
            encryption_key=os.environ["TOKEN_ENCRYPTION_KEY"],
            origin=os.getenv("APP_ORIGIN", "http://localhost:3000").rstrip("/"),
            issuer=os.getenv("OIDC_ISSUER", "http://localhost:8080/realms/reports-realm").rstrip("/"),
            keycloak_internal=os.getenv("KEYCLOAK_INTERNAL_URL", "http://keycloak:8080/realms/reports-realm").rstrip("/"),
            redis_url=os.getenv("REDIS_URL", "redis://auth-redis:6379/0"),
            api_url=os.getenv("REPORTS_API_URL", "").rstrip("/"),
            profiles_database_url=os.environ["PROFILES_DATABASE_URL"],
            cookie_secure=secure == "true",
        )
