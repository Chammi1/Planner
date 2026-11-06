import argparse
from .config import OWNER
from .db import init_db, connect, new_code

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['login-code','revoke-sessions','check-bot'])
    args = parser.parse_args()
    if args.command == 'check-bot':
        from .bot import call
        me = call('getMe')
        info = call('getWebhookInfo')
        print('Bot:', '@'+me.get('username','unknown'))
        print('Webhook configured:', bool(info.get('url')))
        print('This does not detect an external polling worker. Do not start a second worker.')
        return
    init_db()
    if args.command == 'login-code':
        print(new_code(OWNER))
        print('Single-use login code. Expires in 5 minutes. Keep private.')
    else:
        with connect() as conn:
            conn.execute('DELETE FROM sessions WHERE owner=%s', (OWNER,))
            conn.execute('DELETE FROM login_codes WHERE owner=%s', (OWNER,))
        print('All sessions and codes revoked.')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit(f'Administrative command failed ({type(exc).__name__}). Check settings locally; secrets are not logged.')
