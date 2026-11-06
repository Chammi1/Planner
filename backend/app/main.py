import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends
from pydantic import BaseModel, Field, ConfigDict
from .config import OWNER, BOT_TOKEN, TIMEZONE
from .db import connect, init_db, read_document, write_document, Conflict, make_session, rate_limit
from .security import digest, validate_init_data
from .validation import validate_state

@asynccontextmanager
async def lifespan(app):
    init_db()
    yield

app = FastAPI(title='Sota Planner API', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

class AuthTelegram(BaseModel):
    init_data: str = Field(min_length=1, max_length=16384)

class AuthCode(BaseModel):
    code: str = Field(min_length=10, max_length=100)

class UpdateState(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=0)
    state: dict

def throttle(request, name, limit=30, window=60):
    ip = request.client.host if request.client else 'unknown'
    if not rate_limit(f'{name}:{ip}', limit, window):
        raise HTTPException(429, 'Too many attempts. Try later.')

def owner(request: Request):
    auth = request.headers.get('authorization', '')
    if not auth.startswith('Bearer ') or len(auth) > 200:
        raise HTTPException(401, 'Sign in required')
    with connect() as conn:
        row = conn.execute('SELECT owner FROM sessions WHERE hash=%s AND expires>%s', (digest(auth[7:]), int(time.time()))).fetchone()
    if not row or row['owner'] != OWNER:
        raise HTTPException(401, 'Session expired. Sign in again.')
    return row['owner']

@app.middleware('http')
async def headers(request: Request, call_next):
    length = request.headers.get('content-length')
    if length and (not length.isdigit() or int(length) > 2000000):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':'Request too large'}, status_code=413)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    from fastapi.responses import JSONResponse
    logging.error('Request failed (%s)', type(exc).__name__)
    return JSONResponse({'detail':'Server error; changes were not confirmed.'}, status_code=500)

@app.get('/api/health')
def health():
    with connect() as conn:
        conn.execute('SELECT 1')
    return {'ok': True}

@app.post('/api/auth/telegram')
def telegram_login(body: AuthTelegram, request: Request):
    throttle(request, 'auth')
    try:
        uid = validate_init_data(body.init_data, BOT_TOKEN, OWNER)
    except PermissionError:
        raise HTTPException(403, 'Only the owner can access this application')
    except (ValueError, TypeError, KeyError):
        raise HTTPException(401, 'Telegram authentication invalid or expired. Reopen Mini App.')
    with connect() as conn:
        conn.execute('DELETE FROM sessions WHERE expires<%s', (int(time.time()),))
        token = make_session(conn, uid)
    return {'token': token}

@app.post('/api/auth/code')
def code_login(body: AuthCode, request: Request):
    throttle(request, 'auth')
    with connect() as conn:
        row = conn.execute('DELETE FROM login_codes WHERE hash=%s AND expires>%s RETURNING owner', (digest(body.code.strip()), int(time.time()))).fetchone()
        if not row or row['owner'] != OWNER:
            raise HTTPException(401, 'Code invalid, used or expired. Request /login again.')
        token = make_session(conn, row['owner'])
    return {'token': token}

@app.post('/api/auth/logout')
def logout(request: Request, uid=Depends(owner)):
    with connect() as conn:
        conn.execute('DELETE FROM sessions WHERE hash=%s', (digest(request.headers['authorization'][7:]),))
    return {'ok': True}

@app.get('/api/state')
def get_state(uid=Depends(owner)):
    row = read_document(uid)
    return {**row, 'timezone': TIMEZONE, 'owner': uid}

@app.put('/api/state')
def put_state(body: UpdateState, uid=Depends(owner)):
    try:
        state = validate_state(body.state)
    except (ValueError, TypeError, AttributeError, KeyError):
        raise HTTPException(422, 'Invalid planner data. Export a copy and check the import or settings.')
    try:
        revision = write_document(uid, state, body.revision)
    except Conflict:
        raise HTTPException(409, 'Data changed on another device or in the bot. Export your changes, then reload the server copy.')
    return {'revision': revision}
