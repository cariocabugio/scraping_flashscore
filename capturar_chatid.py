import os
from dotenv import load_dotenv
from telegram.ext import Application, MessageHandler, filters

load_dotenv('.env.local')
TOKEN = os.getenv('TELEGRAM_TOKEN')

async def handler(update, context):
    chat_id = update.effective_chat.id
    print(f"\n🎯 Chat ID: {chat_id}")
    with open('.env.local', 'a') as f:
        f.write(f'\nTELEGRAM_CHAT_ID={chat_id}')
    await update.message.reply_text('✅ Chat ID salvo! O bot está pronto.')
    await context.application.stop()

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handler))
    print("⏳ Envie qualquer mensagem para o bot no Telegram...")
    app.run_polling()

if __name__ == '__main__':
    main()