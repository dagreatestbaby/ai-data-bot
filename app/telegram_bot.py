from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters
)
from app.handlers import (
    start_command, file_upload_handler, menu_callback_handler, text_handler
)
from app.config import TELEGRAM_BOT_TOKEN

application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start_command))
application.add_handler(MessageHandler(filters.Document.ALL, file_upload_handler))
application.add_handler(CallbackQueryHandler(menu_callback_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

def process_telegram_update(update_data):
    from telegram import Update, Bot
    bot = application.bot
    update = Update.de_json(update_data, bot)
    application.process_update(update)

