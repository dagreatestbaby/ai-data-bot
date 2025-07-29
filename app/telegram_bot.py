from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from app.handlers import (
    handle_start, handle_file, handle_columns, handle_stat, handle_expert
)
from app.config import TELEGRAM_BOT_TOKEN

def main():
    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", handle_start))
    dp.add_handler(CommandHandler("columns", handle_columns))
    dp.add_handler(CommandHandler("stat", handle_stat))
    dp.add_handler(CommandHandler("expert", handle_expert))
    dp.add_handler(MessageHandler(Filters.document, handle_file))
    # Anything else as expert mode (fallback)
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_expert))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()

