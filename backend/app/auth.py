"""OIDC identity plus database-backed, opaque application sessions.

No provider tokens or OAuth state are placed in browser-readable storage.
UTC datetimes are stored without tzinfo for consistent SQL Server handling.
"""
from typing import cast
from sqlalchemy.engine import CursorResult
import hashlib
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import case, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import session, settings
from .models import AuthEvent, AuthSession, LoginFlow, RateBucket, User

router = APIRouter()
oauth = OAuth()
oauth.register(name='keycloak', client_id=settings.oidc_client_id, client_secret=settings.oidc_client_secret,
    server_metadata_url=settings.oidc_issuer.rstrip('/') + '/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid profile', 'code_challenge_method': 'S256', 'timeout': 10})
SESSION_COOKIE = '__Host-pesopilot'
FLOW_COOKIE = '__Host-pesopilot-login'

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def event(db, kind, user_id=None):
    db.add(AuthEvent(event=kind, user_id=user_id, occurred_at=now()))
    db.commit()

def rate_limit(db, key, limit):
    window = int(time.time()) // settings.rate_window_seconds
    key = digest(key)
    # An atomic UPDATE avoids lost increments across threads/processes.
    for attempt in range(3):
        result = db.execute(update(RateBucket).where(RateBucket.key == key, RateBucket.window == window).values(count=RateBucket.count + 1))
        if cast(CursorResult, result).rowcount:
            db.commit()
            break
        db.add(RateBucket(key=key, window=window, count=1))
        try:
            db.commit()
            break
        except IntegrityError:
            db.rollback()
    else:
        raise HTTPException(503, 'Rate limiter unavailable')
    count = db.scalar(select(RateBucket.count).where(RateBucket.key == key, RateBucket.window == window))
    db.execute(delete(RateBucket).where(RateBucket.window < window - 2))
    db.commit()
    if count > limit:
        event(db, 'rate_limited')
        raise HTTPException(429, 'Too many requests; try again shortly', headers={'Retry-After': str(settings.rate_window_seconds)})

def auth_rate(request, db):
    # Forwarded IP headers are deliberately ignored unless a trusted proxy is configured.
    address = request.client.host if request.client else 'unknown'
    rate_limit(db, 'auth:' + address, settings.auth_limit)

def set_cookie(response, name, value, max_age):
    response.set_cookie(name, value, max_age=max_age, secure=True,
        httponly=True, samesite='lax', path='/')

def clear_cookie(response, name):
    response.delete_cookie(name, secure=True, httponly=True, samesite='lax', path='/')

def authenticated(request: Request, db: Session = Depends(session)):
    token = request.cookies.get(SESSION_COOKIE, '')
    row = db.get(AuthSession, digest(token)) if token else None
    if row is None:
        auth_rate(request, db)
        event(db, 'unauthenticated')
        raise HTTPException(401, 'Sign in to continue')
    timestamp = now()
    if row.expires_at <= timestamp or row.last_seen_at + timedelta(seconds=settings.session_idle_seconds) <= timestamp:
        user_id = row.user_id
        db.execute(delete(AuthSession).where(AuthSession.token_hash == row.token_hash))
        db.commit()
        event(db, 'session_expired', user_id)
        raise HTTPException(401, 'Session expired; sign in again')
    # Keep a read-only identity snapshot across rate-limit commits. A concurrent
    # revocation must produce 401 at the conditional touch, not an ORM reload error.
    db.expunge(row)
    rate_limit(db, 'user:' + row.user_id, settings.api_limit)
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        csrf = request.headers.get('X-CSRF-Token', '')
        if request.headers.get('origin') != settings.frontend_url.rstrip('/') or not secrets.compare_digest(csrf, row.csrf_token):
            event(db, 'csrf_rejected', row.user_id)
            raise HTTPException(403, 'Invalid request origin or CSRF token')
    # Conditional update handles a logout/revocation between reading and touching
    # this session. It cannot recreate a deleted row or move last_seen backwards.
    result = db.execute(update(AuthSession).where(
        AuthSession.token_hash == row.token_hash,
        AuthSession.expires_at > timestamp,
        AuthSession.last_seen_at > timestamp - timedelta(seconds=settings.session_idle_seconds),
    ).values(last_seen_at=case((AuthSession.last_seen_at < timestamp, timestamp), else_=AuthSession.last_seen_at)), execution_options={'synchronize_session': False})
    db.commit()
    if cast(CursorResult, result).rowcount != 1:
        raise HTTPException(401, 'Session expired or revoked; sign in again')
    return row

def owner(row: AuthSession = Depends(authenticated)):
    return row.user_id

def issue_session(db, user_id, response, previous_token=None):
    db.execute(delete(AuthSession).where(AuthSession.expires_at < now()))
    if previous_token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == digest(previous_token)))
    token = secrets.token_urlsafe(32)
    timestamp = now()
    db.add(AuthSession(token_hash=digest(token), user_id=user_id, csrf_token=secrets.token_urlsafe(32),
        created_at=timestamp, last_seen_at=timestamp, expires_at=timestamp + timedelta(seconds=settings.session_seconds)))
    db.commit()
    set_cookie(response, SESSION_COOKIE, token, settings.session_seconds)

@router.get('/login')
async def login(request: Request, db: Session = Depends(session), configure_mfa: bool = False):
    auth_rate(request, db)
    if not settings.oidc_client_secret:
        event(db, 'login_unconfigured')
        raise HTTPException(503, 'Configure Keycloak client credentials to enable login')
    request.scope['session'] = {}
    try:
        options = {'prompt': 'login'}
        if configure_mfa:
            options['kc_action'] = 'CONFIGURE_TOTP'
        response = await oauth.keycloak.authorize_redirect(request, settings.frontend_url.rstrip('/') + '/api/v1/auth/callback', **options)
    except Exception:
        event(db, 'provider_unavailable')
        raise HTTPException(503, 'Login provider unavailable')
    token = secrets.token_urlsafe(32)
    db.execute(delete(LoginFlow).where(LoginFlow.expires_at < now()))
    db.add(LoginFlow(token_hash=digest(token), payload=json.dumps(request.session), expires_at=now() + timedelta(minutes=5)))
    db.commit()
    set_cookie(response, FLOW_COOKIE, token, 300)
    response.headers['Cache-Control'] = 'no-store'
    event(db, 'login_started')
    return response

@router.get('/callback')
async def callback(request: Request, db: Session = Depends(session)):
    response: Response
    auth_rate(request, db)
    token = request.cookies.get(FLOW_COOKIE, '')
    flow = db.get(LoginFlow, digest(token)) if token else None
    if flow is None or flow.expires_at <= now():
        event(db, 'login_rejected')
        raise HTTPException(400, 'Login request expired or invalid; start again')
    payload = flow.payload
    result = db.execute(delete(LoginFlow).where(LoginFlow.token_hash == flow.token_hash))
    db.commit()
    if cast(CursorResult, result).rowcount != 1:
        raise HTTPException(400, 'Login request already consumed')
    request.scope['session'] = json.loads(payload)
    try:
        # Authlib verifies state, signature, issuer, audience, expiry and nonce.
        state_data = await oauth.keycloak.framework.get_state_data(request.session, request.query_params.get('state'))
        expected_nonce = state_data['nonce']
        token_response = await oauth.keycloak.authorize_access_token(request, claims_options={'iss': {'essential': True, 'value': settings.oidc_issuer}}, leeway=0)
        claims = token_response['userinfo']
        if claims['iss'] != settings.oidc_issuer or not claims.get('sub') or not secrets.compare_digest(str(claims.get('nonce', '')), expected_nonce):
            raise ValueError('Invalid issuer or subject')
        subject = str(claims['sub'])
        name = str(claims.get('name') or claims.get('preferred_username') or 'PesoPilot user')[:160]
        if len(subject) > 255:
            raise ValueError('Invalid subject')
    except Exception:
        event(db, 'login_rejected')
        response = JSONResponse({'detail': 'Login verification failed; start again'}, status_code=400)
        clear_cookie(response, FLOW_COOKIE)
        return response
    user = db.scalar(select(User).where(User.issuer == settings.oidc_issuer, User.subject == subject))
    if user is None:
        user = User(issuer=settings.oidc_issuer, subject=subject, display_name=name, created_at=now())
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            user = db.scalar(select(User).where(User.issuer == settings.oidc_issuer, User.subject == subject))
    else:
        user.display_name = name
        db.commit()
    if user is None:
        raise HTTPException(503, 'Identity changed concurrently; sign in again')
    response = RedirectResponse(settings.frontend_url, status_code=303)
    issue_session(db, user.id, response, request.cookies.get(SESSION_COOKIE, ''))
    clear_cookie(response, FLOW_COOKIE)
    response.headers['Cache-Control'] = 'no-store'
    event(db, 'login_success', user.id)
    return response

@router.get('/me')
def me(row: AuthSession = Depends(authenticated), db: Session = Depends(session)):
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(401, 'Identity no longer exists; sign in again')
    return JSONResponse({'id': user.id, 'name': user.display_name, 'csrf_token': row.csrf_token}, headers={'Cache-Control': 'no-store'})

@router.get('/sessions')
def sessions(row: AuthSession = Depends(authenticated), db: Session = Depends(session)):
    timestamp = now()
    rows = db.scalars(select(AuthSession).where(AuthSession.user_id == row.user_id,
        AuthSession.expires_at > timestamp,
        AuthSession.last_seen_at > timestamp - timedelta(seconds=settings.session_idle_seconds)).order_by(AuthSession.created_at.desc())).all()
    # IDs are non-authenticating one-way hashes, never cookie or CSRF values.
    return [{'id': item.token_hash, 'current': item.token_hash == row.token_hash,
        'created_at': item.created_at.isoformat() + 'Z', 'expires_at': item.expires_at.isoformat() + 'Z',
        'last_seen_at': item.last_seen_at.isoformat() + 'Z'} for item in rows]

@router.delete('/sessions/{session_id}', status_code=204)
def revoke_session(session_id: str, row: AuthSession = Depends(authenticated), db: Session = Depends(session)):
    result = db.execute(delete(AuthSession).where(AuthSession.token_hash == session_id, AuthSession.user_id == row.user_id))
    if cast(CursorResult, result).rowcount != 1:
        db.rollback()
        event(db, 'authorization_denied', row.user_id)
        raise HTTPException(404, 'Session not found')
    db.add(AuthEvent(event='session_revoked', user_id=row.user_id, occurred_at=now()))
    db.commit()
    response = Response(status_code=204)
    if session_id == row.token_hash:
        clear_cookie(response, SESSION_COOKIE)
    return response

@router.post('/logout')
async def logout(row: AuthSession = Depends(authenticated), db: Session = Depends(session)):
    user_id = row.user_id
    db.execute(delete(AuthSession).where(AuthSession.token_hash == row.token_hash, AuthSession.user_id == user_id))
    db.commit()
    event(db, 'logout', user_id)
    # Application logout always revokes locally, even if the provider is offline.
    logout_url = None
    try:
        metadata = await oauth.keycloak.load_server_metadata()
        endpoint = metadata.get('end_session_endpoint')
        if endpoint:
            logout_url = endpoint + '?' + urlencode({'client_id': settings.oidc_client_id, 'post_logout_redirect_uri': settings.frontend_url})
    except Exception:
        event(db, 'provider_logout_unavailable', user_id)
    response = JSONResponse({'logout_url': logout_url}, headers={'Cache-Control': 'no-store'})
    clear_cookie(response, SESSION_COOKIE)
    clear_cookie(response, FLOW_COOKIE)
    return response
