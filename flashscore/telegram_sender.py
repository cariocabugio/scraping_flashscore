import os
from telegram import Bot
from dotenv import load_dotenv

load_dotenv('.env.local')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

async def send_telegram(text: str):
    if not TELEGRAM_CHAT_ID:
        return
    bot = Bot(token=TELEGRAM_TOKEN)
    ids = [c.strip() for c in TELEGRAM_CHAT_ID.split(',') if c.strip()]
    for cid in ids:
        try:
            await bot.send_message(chat_id=cid, text=text, parse_mode='Markdown')
        except Exception as e:
            print(f"⚠️ Telegram {cid}: {e}")