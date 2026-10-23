import base64
import hashlib
import json
import secrets
import time
from contextlib import asynccontextmanager

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from redis.exceptions import LockNotOwnedError


class InvalidSession(Exception):
    def __init__(self, clear=False):
        self.clear = clear


class SessionBusy(Exception):
    pass


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


# A lease alone is insufficient: an expired/paused worker must not overwrite a newer generation.
COMMIT = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] or redis.call('GET', KEYS[2]) ~= ARGV[2] then return 0 end
redis.call('DEL', KEYS[2])
if ARGV[3] == '' then
  redis.call('DEL', KEYS[3])
else
  redis.call('SET', KEYS[3], ARGV[3], 'EX', ARGV[4])
  redis.call('SET', KEYS[4], ARGV[2], 'EX', ARGV[4])
end
return 1
"""
CONSUME_LOGIN = """
local value = redis.call('GET', KEYS[1])
if not value or cjson.decode(value).browser ~= ARGV[1] then return false end
redis.call('DEL', KEYS[1])
return value
"""


class Sessions:
    def __init__(self, settings, redis):
        self.settings = settings
        self.redis = redis
        self.cipher = AESGCM(base64.urlsafe_b64decode(settings.encryption_key))

    def key(self, kind, value):
        return self.settings.redis_prefix + kind + ":" + value

    def seal(self, value, record_id):
        nonce = secrets.token_bytes(12)
        return base64.urlsafe_b64encode(nonce + self.cipher.encrypt(nonce, value.encode(), record_id.encode())).decode()

    def unseal(self, value, record_id):
        raw = base64.urlsafe_b64decode(value)
        return self.cipher.decrypt(raw[:12], raw[12:], record_id.encode()).decode()

    def bind_tokens(self, record, tokens):
        record.update(access_token=tokens["access_token"], expires_at=tokens["expires_at"],
                      refresh_token=self.seal(tokens["refresh_token"], record["id"]))

    def ttl(self, record):
        return min(self.settings.idle_seconds, int(record["created_at"] + self.settings.absolute_seconds - time.time()))

    async def create(self, identity, tokens):
        sid, record_id = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        record = {"id": record_id, "sid_hash": digest(sid), "created_at": time.time(),
                  "identity": identity, "csrf": secrets.token_urlsafe(32)}
        self.bind_tokens(record, tokens)
        ttl = self.ttl(record)
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.set(self.key("session", record_id), json.dumps(record), ex=ttl)
            pipe.set(self.key("sid", digest(sid)), record_id, ex=ttl)
            await pipe.execute()
        return sid, ttl

    @asynccontextmanager
    async def locked(self, sid):
        if not sid or len(sid) > 128:
            raise InvalidSession()
        sid_hash = digest(sid)
        record_id = await self.redis.get(self.key("sid", sid_hash))
        if not record_id:
            raise InvalidSession()  # Never clear a cookie for a stale request.
        lock = self.redis.lock(self.key("lock", record_id), timeout=30, blocking_timeout=3, thread_local=False)
        if not await lock.acquire():
            raise SessionBusy()
        try:
            raw = await self.redis.get(self.key("session", record_id))
            if not raw or await self.redis.get(self.key("sid", sid_hash)) != record_id:
                raise InvalidSession()
            record = json.loads(raw)
            if record["sid_hash"] != sid_hash:
                raise InvalidSession()
            if self.ttl(record) <= 0:
                await self.commit(record, lock, delete=True)
                raise InvalidSession(clear=True)
            yield record, lock
        finally:
            try:
                await lock.release()
            except LockNotOwnedError:
                pass  # COMMIT checks the fencing token before making any changes.

    async def commit(self, record, lock, delete=False):
        sid = secrets.token_urlsafe(32)
        old_hash = record["sid_hash"]
        record["sid_hash"] = digest(sid)
        ttl = self.ttl(record)
        expired = not delete and ttl <= 0
        delete = delete or ttl <= 0
        result = await self.redis.eval(COMMIT, 4, lock.name, self.key("sid", old_hash),
                                       self.key("session", record["id"]), self.key("sid", digest(sid)),
                                       lock.local.token, record["id"], "" if delete else json.dumps(record), max(1, ttl))
        if not result:
            raise SessionBusy()
        if expired:
            raise InvalidSession(clear=True)
        if not delete:
            return sid, ttl

    async def start_login(self):
        state, browser = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        context = {"browser": digest(browser), "nonce": secrets.token_urlsafe(32), "verifier": secrets.token_urlsafe(64)}
        await self.redis.set(self.key("login", digest(state)), json.dumps(context), ex=300)
        return state, browser, context

    async def consume_login(self, state, browser):
        if not state or not browser or len(state) > 128 or len(browser) > 128:
            return None
        raw = await self.redis.eval(CONSUME_LOGIN, 1, self.key("login", digest(state)), digest(browser))
        return json.loads(raw) if raw else None
