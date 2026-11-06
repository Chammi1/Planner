import json
import logging
import secrets
import time
from datetime import datetime
import httpx
from .config import BOT_TOKEN, OWNER, PUBLIC_URL, TZ
from .db import connect, init_db, read_document, mark_done, new_code

class TelegramError(Exception):
    def __init__(self, code, description):
        self.code = code
        super().__init__(description)

client = httpx.Client(timeout=45)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

def call(method, **payload):
    response = client.post(f'https://api.telegram.org/bot{BOT_TOKEN}/{method}', json=payload)
    data = response.json()
    if not data.get('ok'):
        raise TelegramError(data.get('error_code', 0), data.get('description', 'Telegram request failed'))
    return data['result']

def send(chat, text, buttons=None):
    payload = {'chat_id': chat, 'text': text}
    if buttons:
        payload['reply_markup'] = {'inline_keyboard': buttons}
    return call('sendMessage', **payload)

def app_button():
    return [{'text': 'Открыть планировщик', 'web_app': {'url': PUBLIC_URL}}]

def today(chat):
    date = datetime.now(TZ).date().isoformat()
    state = read_document(OWNER)['state']
    planned = [t for t in state['tasks'] if state['entries'].get(t['id'], {}).get(date) in ('planned', 'done')]
    done = sum(state['entries'][t['id']][date] == 'done' for t in planned)
    send(chat, f'{date} · закрыто {done} из {len(planned)}. Для полной статистики открой приложение.', [app_button()])
    for task in planned[:80]:
        status = state['entries'][task['id']][date]
        text = ('Выполнено: ' if status == 'done' else 'План: ') + task['title']
        buttons = None
        if status != 'done':
            # Random token stored in DB avoids the 64-byte callback_data task-id limit.
            token = secrets.token_urlsafe(12)
            with connect() as conn:
                conn.execute('CREATE TABLE IF NOT EXISTS bot_actions (token TEXT PRIMARY KEY, task_id TEXT NOT NULL, date TEXT NOT NULL, expires BIGINT NOT NULL)')
                conn.execute('DELETE FROM bot_actions WHERE expires<%s', (int(time.time()),))
                conn.execute('INSERT INTO bot_actions VALUES (%s,%s,%s,%s)', (token, task['id'], date, int(time.time())+86400*2))
            buttons = [[{'text':'Отметить выполненным','callback_data':'done:'+token}]]
        send(chat, text, buttons)
        time.sleep(0.15)
    if len(planned) > 80:
        send(chat, 'Остальные дела доступны в приложении.')

def handle(update):
    callback = update.get('callback_query')
    if callback:
        if callback.get('from', {}).get('id') != OWNER:
            call('answerCallbackQuery', callback_query_id=callback['id'], text='Нет доступа')
            return
        data = callback.get('data', '')
        if not data.startswith('done:'):
            return
        with connect() as conn:
            exists = conn.execute("SELECT to_regclass('public.bot_actions') AS name").fetchone()['name']
            row = conn.execute('SELECT task_id,date FROM bot_actions WHERE token=%s AND expires>%s', (data[5:], int(time.time()))).fetchone() if exists else None
        ok = bool(row and mark_done(OWNER, row['task_id'], row['date']))
        call('answerCallbackQuery', callback_query_id=callback['id'], text='Выполнено' if ok else 'Кнопка устарела. Обнови /today')
        message = callback.get('message', {})
        if ok and message.get('chat', {}).get('type') == 'private':
            call('editMessageReplyMarkup', chat_id=message['chat']['id'], message_id=message['message_id'], reply_markup={'inline_keyboard':[]})
        return
    message = update.get('message', {})
    if message.get('from', {}).get('id') != OWNER or message.get('chat', {}).get('type') != 'private':
        return
    chat = message['chat']['id']
    text = message.get('text', '').split(maxsplit=1)[0].split('@')[0] if message.get('text') else ''
    if text in ('/start', '/help'):
        send(chat, 'Планировщик подключён. /today — дела на сегодня, /login — одноразовый код для входа в браузере.', [app_button()])
    elif text == '/today':
        today(chat)
    elif text == '/login':
        code = new_code(OWNER)
        send(chat, f'Код входа в {PUBLIC_URL}:\n{code}\nДействует 5 минут, используется один раз. Не передавай его другим.')

def main():
    init_db()
    info = call('getWebhookInfo')
    if info.get('url'):
        raise SystemExit('STOP: webhook already configured. No changes made. Integrate with the existing bot or stop its handler explicitly.')
    call('getMe')
    with connect() as lock:
        acquired = lock.execute('SELECT pg_try_advisory_lock(794261) AS ok').fetchone()['ok']
        if not acquired:
            raise SystemExit('Another planner bot worker is running')
        while True:
            with connect() as conn:
                row = conn.execute("SELECT value FROM bot_meta WHERE key='offset'").fetchone()
            offset = row['value'] if row else 0
            try:
                updates = call('getUpdates', offset=offset, timeout=30, allowed_updates=['message','callback_query'])
                for update in updates:
                    try:
                        handle(update)
                    except (httpx.HTTPError, TelegramError) as exc:
                        logging.error('Update response failed (%s). Check /today again if needed.', type(exc).__name__)
                    with connect() as conn:
                        conn.execute("INSERT INTO bot_meta(key,value) VALUES ('offset',%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (update['update_id']+1,))
            except TelegramError as exc:
                if exc.code == 409:
                    raise SystemExit('STOP: Telegram polling conflict. Another handler may be running. It was not stopped.')
                logging.error('Telegram error code %s; retrying', exc.code)
                time.sleep(5)
            except httpx.HTTPError:
                logging.error('Telegram network error; retrying')
                time.sleep(5)

if __name__ == '__main__':
    try:
        main()
    except TelegramError as exc:
        raise SystemExit(f'Telegram startup failed, code {exc.code}. Check token locally; do not paste it into chats.')
    except httpx.HTTPError:
        raise SystemExit('Telegram startup network failure. Check outbound connectivity; token is not logged.')
