import secrets
import time
from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from .config import DATABASE_URL, OWNER
from .security import digest

DEFAULT_STATE = {'tasks': [], 'entries': {}, 'times': {}, 'settings': {'wake': '07:00', 'sleep': '23:00'}}

@contextmanager
def connect():
    with psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=5) as conn:
        yield conn

def init_db():
    with connect() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS documents (owner BIGINT PRIMARY KEY, state JSONB NOT NULL, revision BIGINT NOT NULL DEFAULT 0, updated_at TIMESTAMPTZ NOT NULL DEFAULT now())')
        conn.execute('CREATE TABLE IF NOT EXISTS snapshots (owner BIGINT NOT NULL, revision BIGINT NOT NULL, state JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(owner, revision))')
        conn.execute('CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, owner BIGINT NOT NULL, expires BIGINT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS login_codes (hash TEXT PRIMARY KEY, owner BIGINT NOT NULL, expires BIGINT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS rate_limits (key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires BIGINT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS bot_meta (key TEXT PRIMARY KEY, value BIGINT NOT NULL)')
        conn.execute('INSERT INTO documents (owner, state) VALUES (%s, %s) ON CONFLICT DO NOTHING', (OWNER, Jsonb(DEFAULT_STATE)))

def read_document(owner):
    with connect() as conn:
        return conn.execute('SELECT state, revision, updated_at FROM documents WHERE owner=%s', (owner,)).fetchone()

def archive(conn, row, owner):
    conn.execute('INSERT INTO snapshots (owner, revision, state) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING', (owner, row['revision'], Jsonb(row['state'])))
    conn.execute('DELETE FROM snapshots WHERE owner=%s AND revision NOT IN (SELECT revision FROM snapshots WHERE owner=%s ORDER BY revision DESC LIMIT 50)', (owner, owner))

class Conflict(Exception):
    pass

def write_document(owner, state, revision):
    with connect() as conn:
        row = conn.execute('SELECT state, revision FROM documents WHERE owner=%s FOR UPDATE', (owner,)).fetchone()
        if not row or row['revision'] != revision:
            raise Conflict()
        archive(conn, row, owner)
        result = conn.execute('UPDATE documents SET state=%s, revision=revision+1, updated_at=now() WHERE owner=%s RETURNING revision', (Jsonb(state), owner)).fetchone()
        return result['revision']

def mark_done(owner, task_id, date):
    with connect() as conn:
        row = conn.execute('SELECT state, revision FROM documents WHERE owner=%s FOR UPDATE', (owner,)).fetchone()
        state = row['state']
        if not any(t['id'] == task_id for t in state['tasks']) or date not in state['entries'].get(task_id, {}):
            return False
        if state['entries'][task_id][date] == 'done':
            return True
        archive(conn, row, owner)
        state['entries'][task_id][date] = 'done'
        conn.execute('UPDATE documents SET state=%s, revision=revision+1, updated_at=now() WHERE owner=%s', (Jsonb(state), owner))
        return True

def make_session(conn, owner):
    token = secrets.token_urlsafe(32)
    conn.execute('INSERT INTO sessions (hash,owner,expires) VALUES (%s,%s,%s)', (digest(token), owner, int(time.time())+7*86400))
    return token

def new_code(owner):
    code = secrets.token_urlsafe(18)
    with connect() as conn:
        conn.execute('DELETE FROM login_codes WHERE owner=%s OR expires<%s', (owner, int(time.time())))
        conn.execute('INSERT INTO login_codes (hash,owner,expires) VALUES (%s,%s,%s)', (digest(code), owner, int(time.time())+300))
    return code

def rate_limit(key, limit, window):
    now = int(time.time())
    bucket = now // window
    key = digest(f'{key}:{bucket}')
    with connect() as conn:
        conn.execute('DELETE FROM rate_limits WHERE expires<%s', (now,))
        count = conn.execute('INSERT INTO rate_limits (key,count,expires) VALUES (%s,1,%s) ON CONFLICT(key) DO UPDATE SET count=rate_limits.count+1 RETURNING count', (key, now+window*2)).fetchone()['count']
    return count <= limit
