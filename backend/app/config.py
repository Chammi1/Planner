import os
from zoneinfo import ZoneInfo
DATABASE_URL = os.environ['DATABASE_URL']
BOT_TOKEN = os.environ['BOT_TOKEN']
OWNER = int(os.environ['OWNER_TELEGRAM_ID'])
PUBLIC_URL = os.environ.get('PUBLIC_URL', 'https://bot.sotaholder.ru:8443').rstrip('/')
TIMEZONE = os.environ.get('APP_TIMEZONE', 'Asia/Yekaterinburg')
TZ = ZoneInfo(TIMEZONE)
if OWNER <= 0 or ':' not in BOT_TOKEN or 'PASTE_' in BOT_TOKEN:
    raise RuntimeError('Set valid OWNER_TELEGRAM_ID and BOT_TOKEN in .env')
