from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

CONSENT_VERSION = "yandex-profile-v1"


class Profiles:
    def __init__(self, url):
        self.url = url

    async def initialize(self):
        async with await AsyncConnection.connect(self.url, connect_timeout=5) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS yandex_profiles (
                issuer text NOT NULL, subject text NOT NULL,
                consent_version text NOT NULL, accepted boolean NOT NULL,
                decided_at timestamptz NOT NULL DEFAULT now(), profile jsonb,
                PRIMARY KEY (issuer, subject))""")

    async def status(self, identity):
        async with await AsyncConnection.connect(self.url, connect_timeout=5) as db:
            cursor = await db.execute(
                "SELECT accepted, profile FROM yandex_profiles WHERE issuer=%s AND subject=%s AND consent_version=%s",
                (identity["iss"], identity["sub"], CONSENT_VERSION))
            row = await cursor.fetchone()
        return {"consent": "pending" if row is None else "accepted" if row[0] else "declined",
                "profile": row[1] if row else None}

    async def decide(self, identity, accepted, load_profile):
        async with await AsyncConnection.connect(self.url, connect_timeout=5) as db:
            # Serialize decisions for this user; failed imports roll back without recording consent.
            await db.execute("""INSERT INTO yandex_profiles (issuer, subject, consent_version, accepted)
                VALUES (%s, %s, %s, false) ON CONFLICT DO NOTHING""",
                (identity["iss"], identity["sub"], CONSENT_VERSION))
            await db.execute("SELECT subject FROM yandex_profiles WHERE issuer=%s AND subject=%s FOR UPDATE",
                             (identity["iss"], identity["sub"]))
            profile = await load_profile() if accepted else None
            await db.execute("""UPDATE yandex_profiles SET consent_version=%s, accepted=%s,
                decided_at=clock_timestamp(), profile=%s WHERE issuer=%s AND subject=%s""",
                (CONSENT_VERSION, accepted, Jsonb(profile) if profile is not None else None,
                 identity["iss"], identity["sub"]))
        return {"consent": "accepted" if accepted else "declined", "profile": profile}
