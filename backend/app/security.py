import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def validate_init_data(raw, token, owner, now=None):
    now = int(time.time()) if now is None else now
    if not raw or len(raw) > 16384:
        raise ValueError('Invalid Telegram authentication')
    pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    data = dict(pairs)
    if len(data) != len(pairs):
        raise ValueError('Duplicate fields')
    received = data.pop('hash', '')
    check = '\n'.join(f'{key}={value}' for key, value in sorted(data.items()))
    secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received, expected):
        raise ValueError('Invalid signature')
    auth_date = int(data.get('auth_date', '0'))
    if now - auth_date > 3600 or auth_date > now + 30:
        raise ValueError('Telegram authentication expired; reopen Mini App')
    user = json.loads(data.get('user', '{}'))
    if user.get('id') != owner:
        raise PermissionError('Access restricted to owner')
    return owner
