import os
import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler
)
import pandas as pd
from io import BytesIO
from dotenv import load_dotenv
from difflib import get_close_matches
import openai
import traceback

# === Load secrets ===
load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_KEY = os.getenv('OPENAI_API_KEY')
openai.api_key = OPENAI_KEY

# === Logging ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("AI_DATA_BOT")

user_files = {}
LANGS = ['ru', 'en']

MESSAGES = {
    'start': {
        'ru': "👋 Привет! Я бот для анализа Excel/CSV. Загрузите файл и выберите действие.",
        'en': "👋 Hello! I'm a bot for Excel/CSV analytics. Upload your file and choose an action.",
    },
    'file_received': {
        'ru': "Файл получен! Выберите действие:",
        'en': "File received! Choose an action:",
    },
    'no_file': {
        'ru': "Пожалуйста, сначала загрузите файл Excel/CSV.",
        'en': "Please upload your Excel/CSV file first.",
    },
    'columns': {
        'ru': "Столбцы файла:",
        'en': "File columns:",
    },
    'count_gender': {
        'ru': "Количество по полу:",
        'en': "Count by gender:",
    },
    'unique_managers': {
        'ru': "Уникальные менеджеры:",
        'en': "Unique managers:",
    },
    'count_city': {
        'ru': "Количество по городам:",
        'en': "Count by city:",
    },
    'expert_warning': {
        'ru': "Экспертный режим: опишите свой запрос, используя названия столбцов из файла.",
        'en': "Expert mode: describe your request using the column names.",
    },
    'error': {
        'ru': "❗ Произошла ошибка:",
        'en': "❗ An error occurred:",
    },
    'expert_processing': {
        'ru': "Обрабатываю экспертный запрос...",
        'en': "Processing expert request...",
    },
    'columns_btn': {
        'ru': "Показать столбцы",
        'en': "Show columns",
    },
    'expert_btn': {
        'ru': "💡 Экспертный режим",
        'en': "💡 Expert mode",
    },
}

def get_lang(update):
    lang = getattr(update.effective_user, "language_code", "ru")[:2]
    return lang if lang in LANGS else 'en'

def main_menu(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(MESSAGES['columns_btn'][lang], callback_data='show_columns')],
        [InlineKeyboardButton(MESSAGES['count_gender'][lang], callback_data='count_gender')],
        [InlineKeyboardButton(MESSAGES['unique_managers'][lang], callback_data='unique_managers')],
        [InlineKeyboardButton(MESSAGES['count_city'][lang], callback_data='count_city')],
        [InlineKeyboardButton(MESSAGES['expert_btn'][lang], callback_data='expert')]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update)
    await update.message.reply_text(MESSAGES['start'][lang])

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update)
    file = update.message.document
    file_id = file.file_id
    new_file = await context.bot.get_file(file_id)
    file_bytes = await new_file.download_as_bytearray()
    user_files[update.effective_user.id] = file_bytes
    await update.message.reply_text(MESSAGES['file_received'][lang], reply_markup=main_menu(lang))

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update)
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    await context.bot.send_chat_action(chat_id=query.message.chat.id, action='typing')
    file_bytes = user_files.get(user_id)
    if not file_bytes:
        await query.edit_message_text(MESSAGES['no_file'][lang])
        return

    # Read file robustly
    try:
        df = None
        try:
            df = pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
        except Exception:
            try:
                df = pd.read_csv(BytesIO(file_bytes), encoding='utf-8')
            except Exception:
                df = pd.read_csv(BytesIO(file_bytes), encoding='latin1')
        if df is None or len(df.columns) == 0:
            raise Exception("File loaded but no columns detected.")
    except Exception as e:
        await query.edit_message_text(f"{MESSAGES['error'][lang]} {e}")
        logger.exception("Failed to load file")
        return

    # Handle buttons
    if query.data == 'show_columns':
        cols = "\n".join(str(c) for c in df.columns)
        # Telegram edit_message_text max is 4096 chars, chunk if needed
        for i in range(0, len(cols), 4000):
            await query.edit_message_text(f"{MESSAGES['columns'][lang]}\n\n{cols[i:i+4000]}", reply_markup=main_menu(lang) if i == 0 else None)
    elif query.data == 'count_gender':
        gender_col = None
        for col in df.columns:
            if 'gender' in col.lower() or 'пол' in col.lower():
                gender_col = col
                break
        if not gender_col:
            await query.edit_message_text(f"{MESSAGES['error'][lang]} Не найден столбец для пола.", reply_markup=main_menu(lang))
            return
        try:
            counts = df[gender_col].value_counts(dropna=False)
            result = "\n".join(f"{str(k)}: {v}" for k, v in counts.items())
        except Exception as e:
            result = f"{MESSAGES['error'][lang]} {e}"
        await query.edit_message_text(f"{MESSAGES['count_gender'][lang]}\n{result}", reply_markup=main_menu(lang))
    elif query.data == 'unique_managers':
        man_col = None
        for col in df.columns:
            if 'manager' in col.lower() or 'менеджер' in col.lower():
                man_col = col
                break
        if not man_col:
            await query.edit_message_text(f"{MESSAGES['error'][lang]} Не найден столбец для менеджера.", reply_markup=main_menu(lang))
            return
        try:
            uniques = df[man_col].dropna().unique()
            result = "\n".join(str(m) for m in uniques)
        except Exception as e:
            result = f"{MESSAGES['error'][lang]} {e}"
        await query.edit_message_text(f"{MESSAGES['unique_managers'][lang]}\n{result}", reply_markup=main_menu(lang))
    elif query.data == 'count_city':
        city_col = None
        for col in df.columns:
            if 'city' in col.lower() or 'город' in col.lower():
                city_col = col
                break
        if not city_col:
            await query.edit_message_text(f"{MESSAGES['error'][lang]} Не найден столбец для города.", reply_markup=main_menu(lang))
            return
        try:
            counts = df[city_col].value_counts(dropna=False)
            result = "\n".join(f"{str(k)}: {v}" for k, v in counts.items())
        except Exception as e:
            result = f"{MESSAGES['error'][lang]} {e}"
        await query.edit_message_text(f"{MESSAGES['count_city'][lang]}\n{result}", reply_markup=main_menu(lang))
    elif query.data == 'expert':
        await query.edit_message_text(MESSAGES['expert_warning'][lang], reply_markup=None)
        context.user_data['expert'] = True

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update)
    user_id = update.effective_user.id
    if context.user_data.get('expert'):
        await update.message.chat.send_action(action='typing')
        file_bytes = user_files.get(user_id)
        if not file_bytes:
            await update.message.reply_text(MESSAGES['no_file'][lang], reply_markup=main_menu(lang))
            context.user_data['expert'] = False
            return
        try:
            df = None
            try:
                df = pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
            except Exception:
                try:
                    df = pd.read_csv(BytesIO(file_bytes), encoding='utf-8')
                except Exception:
                    df = pd.read_csv(BytesIO(file_bytes), encoding='latin1')
            if df is None or len(df.columns) == 0:
                raise Exception("File loaded but no columns detected.")
        except Exception as e:
            await update.message.reply_text(f"{MESSAGES['error'][lang]} {e}", reply_markup=main_menu(lang))
            context.user_data['expert'] = False
            logger.exception("Failed to load file in expert mode")
            return
        # Prepare the LLM prompt
        system_prompt = (
            "You are a Python code generator for a Telegram data analytics bot. "
            "The user gives you a DataFrame 'df' and a task. "
            "ALWAYS output ONLY valid Python code, using only the columns provided below. "
            "ALWAYS create a string variable named 'result' with the answer (do NOT use print()). "
            "Handle missing columns gracefully. "
            "Never import or run dangerous code. "
            "File columns: " + ', '.join(str(c) for c in df.columns)
        )
        user_prompt = update.message.text
        # Call OpenAI
        try:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0,
                max_tokens=2048
            )
            code = response.choices[0].message.content
            # Remove markdown if present
            if code.startswith("```"):
                code = code.split('```')[1]
                code = code.replace('python', '', 1).strip()
            # Run code safely
            local_vars = {'df': df, 'pd': pd, 'result': None}
            try:
                exec(code, {}, local_vars)
                output = local_vars.get('result', None)
                if output is None:
                    output = "No 'result' variable was created by the code."
            except KeyError as e:
                missing = str(e).replace("'", "")
                matches = get_close_matches(missing, list(df.columns), n=3)
                output = f"{MESSAGES['error'][lang]} '{missing}'. Похожие столбцы: {', '.join(matches)}"
            except Exception as e:
                tb = traceback.format_exc()
                output = f"{MESSAGES['error'][lang]} {e}\n{tb[:500]}"
            # Show output (handle Telegram text limits)
            max_length = 3500
            if isinstance(output, str):
                for i in range(0, len(output), max_length):
                    await update.message.reply_text(output[i:i+max_length])
            else:
                await update.message.reply_text(str(output))
        except Exception as e:
            await update.message.reply_text(f"{MESSAGES['error'][lang]} {e}", reply_markup=main_menu(lang))
            logger.exception("Expert mode LLM error")
        context.user_data['expert'] = False
        await update.message.reply_text(MESSAGES['file_received'][lang], reply_markup=main_menu(lang))
    else:
        await update.message.reply_text(MESSAGES['file_received'][lang], reply_markup=main_menu(lang))

if __name__ == '__main__':
    print("\n🚀 AI_DATA_BOT: RUNNING ULTRA-ROBUST VERSION\n")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(CallbackQueryHandler(menu_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

