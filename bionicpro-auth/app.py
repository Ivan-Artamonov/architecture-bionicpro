import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt
import psycopg
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

app = FastAPI()
ORIGIN = os.getenv('PUBLIC_URL', 'https://localhost:8443')
ISSUER = f'{ORIGIN}/id/realms/reports-realm'
KC = os.getenv('KEYCLOAK_INTERNAL', 'http://keycloak:8080/id/realms/reports-realm')
CLIENT = 'bionicpro-auth'
SECRET = os.getenv('AUTH_CLIENT_SECRET', 'local-auth-secret')
INTERNAL_KEY = os.getenv('INTERNAL_KEY', 'local-internal-key')
API = os.getenv('REPORTS_API', 'http://reports-api:8000')
COOKIE = '__Host-bionic-session'
LOGIN_COOKIE = '__Host-bionic-login'
SESSION_TTL = 1800
http = httpx.Client(timeout=10)
# Один процесс для учебного стенда. Перезапуск завершает все сессии.
cipher = Fernet(Fernet.generate_key())
lock = threading.RLock()
sessions = {}
logins = {}


@dataclass
class Session:
    subject: str
    name: str
    access: str
    refresh: bytes
    access_until: float
    until: float
    yandex: bool


def cookie(response, name, value, ttl):
    response.set_cookie(name, value, max_age=ttl, secure=True, httponly=True,
                        samesite='lax', path='/')


def clean_expired():
    now = time.time()
    for sid in list(sessions):
        if sessions[sid].until <= now:
            del sessions[sid]
    for state in list(logins):
        if logins[state]['until'] <= now:
            del logins[state]


def exchange(data):
    try:
        response = http.post(f'{KC}/protocol/openid-connect/token', data={
            **data, 'client_id': CLIENT, 'client_secret': SECRET})
        if response.status_code != 200:
            raise HTTPException(401, 'Войдите заново')
        return response.json()
    except httpx.RequestError:
        raise HTTPException(503, 'Keycloak временно недоступен')


def verify_id_token(token, nonce):
    try:
        response = http.get(f'{KC}/protocol/openid-connect/certs')
        response.raise_for_status()
        kid = jwt.get_unverified_header(token)['kid']
        jwk = next(k for k in response.json()['keys'] if k['kid'] == kid)
        claims = jwt.decode(token, jwt.PyJWK.from_dict(jwk).key,
                            algorithms=['RS256'], audience=CLIENT, issuer=ISSUER,
                            options={'require': ['exp', 'iat', 'sub', 'nonce']})
        if not secrets.compare_digest(claims['nonce'], nonce):
            raise ValueError('nonce')
        return claims
    except (jwt.PyJWTError, ValueError, KeyError, StopIteration, httpx.HTTPError):
        raise HTTPException(401, 'Не удалось проверить вход')


def authenticated(request):
    with lock:
        clean_expired()
        sid = request.cookies.get(COOKIE, '')
        session = sessions.get(sid)
        if not session:
            raise HTTPException(401, 'Войдите в систему')
        if session.access_until <= time.time() + 5:
            try:
                tokens = exchange({'grant_type': 'refresh_token',
                                   'refresh_token': cipher.decrypt(session.refresh).decode()})
            except HTTPException as error:
                if error.status_code == 401:
                    sessions.pop(sid, None)
                raise
            session.access = tokens['access_token']
            session.refresh = cipher.encrypt(tokens['refresh_token'].encode())
            session.access_until = time.time() + tokens['expires_in']
        new_sid = secrets.token_urlsafe(32)
        sessions[new_sid] = sessions.pop(sid)
        request.state.new_sid = new_sid
        request.state.session = session
        return session


@app.middleware('http')
async def response_cookie(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    if hasattr(request.state, 'new_sid'):
        cookie(response, COOKIE, request.state.new_sid,
               max(1, int(request.state.session.until - time.time())))
    return response


def check_origin(request):
    if request.headers.get('origin') != ORIGIN:
        raise HTTPException(403, 'Недопустимый источник запроса')


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/auth/login')
def login(provider: str = ''):
    if provider not in ('', 'yandex'):
        raise HTTPException(400, 'Неизвестный способ входа')
    state, browser_secret = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    verifier, nonce = secrets.token_urlsafe(64), secrets.token_urlsafe(32)
    with lock:
        clean_expired()
        logins[state] = {'browser': browser_secret, 'verifier': verifier,
                         'nonce': nonce, 'until': time.time() + 300}
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    params = {'client_id': CLIENT, 'redirect_uri': f'{ORIGIN}/auth/callback',
              'response_type': 'code', 'scope': 'openid profile', 'state': state,
              'nonce': nonce, 'code_challenge': challenge, 'code_challenge_method': 'S256'}
    if provider:
        params['kc_idp_hint'] = provider
    response = RedirectResponse(f'{ISSUER}/protocol/openid-connect/auth?{urlencode(params)}')
    cookie(response, LOGIN_COOKIE, browser_secret, 300)
    return response


@app.get('/auth/callback')
def callback(request: Request, code: str = '', state: str = ''):
    with lock:
        clean_expired()
        pending = logins.pop(state, None)
    if not pending or not secrets.compare_digest(
            pending['browser'], request.cookies.get(LOGIN_COOKIE, '')) or not code:
        raise HTTPException(400, 'Вход устарел или state не совпал. Начните заново')
    tokens = exchange({'grant_type': 'authorization_code', 'code': code,
                       'code_verifier': pending['verifier'],
                       'redirect_uri': f'{ORIGIN}/auth/callback'})
    claims = verify_id_token(tokens['id_token'], pending['nonce'])
    session = Session(claims['sub'], claims.get('preferred_username', ''),
                      tokens['access_token'], cipher.encrypt(tokens['refresh_token'].encode()),
                      time.time() + tokens['expires_in'], time.time() + SESSION_TTL,
                      claims.get('identity_provider') == 'yandex')
    sid = secrets.token_urlsafe(32)
    with lock:
        sessions.pop(request.cookies.get(COOKIE, ''), None)
        sessions[sid] = session
    response = RedirectResponse('/', status_code=303)
    cookie(response, COOKIE, sid, SESSION_TTL)
    response.delete_cookie(LOGIN_COOKIE, path='/', secure=True, httponly=True, samesite='lax')
    return response


@app.get('/auth/me')
def me(request: Request):
    session = authenticated(request)
    with psycopg.connect(os.environ['PROFILE_DSN']) as db:
        row = db.execute('SELECT consent FROM profiles WHERE subject = %s',
                         (session.subject,)).fetchone()
    return {'id': session.subject, 'name': session.name, 'yandex': session.yandex,
            'consent': row[0] if row else None}


class Consent(BaseModel):
    allowed: bool


@app.post('/auth/consent')
def consent(request: Request, body: Consent):
    check_origin(request)
    session = authenticated(request)
    if not session.yandex:
        raise HTTPException(400, 'Профиль Яндекса не подключён')
    profile = None
    if body.allowed:
        try:
            token_response = http.get(f'{KC}/broker/yandex/token',
                                      headers={'Authorization': f'Bearer {session.access}'})
            token_response.raise_for_status()
            token = token_response.json()['access_token']
            result = http.get('https://login.yandex.ru/info', params={'format': 'json'},
                              headers={'Authorization': f'OAuth {token}'})
            result.raise_for_status()
            raw = result.json()
            profile = {k: raw[k] for k in ('id', 'login', 'display_name', 'default_email') if k in raw}
        except (httpx.HTTPError, KeyError, ValueError):
            raise HTTPException(502, 'Не удалось получить профиль Яндекса')
    with psycopg.connect(os.environ['PROFILE_DSN']) as db:
        db.execute('''INSERT INTO profiles(subject, consent, profile, updated_at)
                      VALUES (%s, %s, %s::jsonb, now()) ON CONFLICT(subject)
                      DO UPDATE SET consent=excluded.consent, profile=excluded.profile,
                                    updated_at=excluded.updated_at''',
                   (session.subject, body.allowed, json.dumps(profile) if profile else None))
    return {'consent': body.allowed}


@app.post('/auth/logout')
def logout(request: Request):
    check_origin(request)
    with lock:
        session = sessions.pop(request.cookies.get(COOKIE, ''), None)
    if session:
        try:
            http.post(f'{KC}/protocol/openid-connect/logout', data={
                'client_id': CLIENT, 'client_secret': SECRET,
                'refresh_token': cipher.decrypt(session.refresh).decode()}).raise_for_status()
        except httpx.HTTPError:
            pass  # Локальная сессия уже закрыта; токен недоступен браузеру.
    response = JSONResponse({'status': 'ok'})
    response.delete_cookie(COOKIE, path='/', secure=True, httponly=True, samesite='lax')
    return response


@app.get('/reports')
def reports(request: Request):
    session = authenticated(request)
    if set(request.query_params) - {'start', 'end'}:
        raise HTTPException(400, 'Можно указать только start и end')
    try:
        result = http.get(f'{API}/reports', params=request.query_params,
                          headers={'X-Internal-Key': INTERNAL_KEY, 'X-User-ID': session.subject})
        return Response(result.content, status_code=result.status_code,
                        media_type='application/json')
    except httpx.RequestError:
        raise HTTPException(503, 'Сервис отчётов временно недоступен')


@app.get('/internal/check-report')
def check_report(request: Request):
    if request.headers.get('x-internal-key') != INTERNAL_KEY:
        raise HTTPException(403)
    session = authenticated(request)
    uri = request.headers.get('x-original-uri', '').split('?', 1)[0]
    match = re.fullmatch(r'/cdn/reports/(etl|cdc)/([0-9]+)/([^/]+)/([0-9-]+)_([0-9-]+)\.json', uri)
    if not match or match[3] != session.subject:
        raise HTTPException(403, 'Чужой отчёт')
    return Response(status_code=204)
