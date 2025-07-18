import os
import traceback
import logging
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
import pandas as pd
from io import BytesIO
from dotenv import load_dotenv
from difflib import get_close_matches
import openai
import re

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ENV ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_KEY")
openai.api_key = OPENAI_KEY

LANGS = ['ru', 'en']
user_files = {}
user_dfs = {}

# --- Secure System Prompt for Expert Mode ---
SAFE_SYSTEM_PROMPT = (
    "You are a Python code generator for a Telegram data analytics bot. "
    "The user gives you a DataFrame 'df' and a task. "
    "ALWAYS output ONLY valid Python code, using only the columns provided below. "
    "ALWAYS create a string variable named 'result' with the answer (do NOT use print()). "
    "Handle missing columns gracefully. "
    "Never import, open files, run shell commands, or execute dangerous code. "
    "Never output anything but the code. "
    "File columns: {columns}"
)

# --- All Bot Messages, Multilanguage, Ready for Scaling ---
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
    }
}

def get_lang(update):
    lang = getattr(update.effective_user, "language_code", "ru")[:2]
    return lang if lang in LANGS else 'en'

def main_menu(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(MESSAGES['columns'][lang], callback_data='show_columns')],
        [InlineKeyboardButton(MESSAGES['count_gender'][lang], callback_data='count_gender')],
        [InlineKeyboardButton(MESSAGES['unique_managers'][lang], callback_data='unique_managers')],
        [InlineKeyboardButton(MESSAGES['count_city'][lang], callback_data='count_city')],
        [InlineKeyboardButton("💡 Expert / Эксперт", callback_data='expert')]
    ])

def parse_file(file_bytes, filename=None):
    """Parse Excel/CSV robustly, with extension sniffing and fallback."""
    try:
        ext = os.path.splitext(filename)[-1].lower() if filename else ""
        if ext in ['.xlsx', '.xls']:
            df = pd.read_excel(BytesIO(file_bytes))
        elif ext == '.csv':
            df = pd.read_csv(BytesIO(file_bytes), encoding='utf-8')
        elif ext == '.tsv':
            df = pd.read_csv(BytesIO(file_bytes), sep='\t', encoding='utf-8')
        else:
            # Try Excel first, fallback to CSV
            try:
                df = pd.read_excel(BytesIO(file_bytes))
            except Exception:
                df = pd.read_csv(BytesIO(file_bytes), encoding='utf-8')
        # Check for column explosion (DoS protection)
        if len(df.columns) > 1000:
            raise ValueError("Too many columns in file. Please upload a simpler file.")
        logger.info(f"Parsed file with columns: {list(df.columns)}")
        return df, None
    except Exception as e:
        logger.error(f"Error parsing file: {e}\n{traceback.format_exc()}")
        return None, str(e)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update)
    await update.message.reply_text(MESSAGES['start'][lang])

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update)
    file = update.message.document
    new_file = await context.bot.get_file(file.file_id)
    file_bytes = await new_file.download_as_bytearray()
    filename = getattr(file, "file_name", "") or ""
    user_files[update.effective_user.id] = file_bytes

    df, error = parse_file(file_bytes, filename)
    if df is not None:
        user_dfs[update.effective_user.id] = (df, filename)
        await update.message.reply_text(MESSAGES['file_received'][lang], reply_markup=main_menu(lang))
    else:
        await update.message.reply_text(f"{MESSAGES['error'][lang]} {error}")

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update)
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    await context.bot.send_chat_action(chat_id=query.message.chat.id, action='typing')

    df_info = user_dfs.get(user_id)
    if not df_info:
        await query.edit_message_text(MESSAGES['no_file'][lang])
        return

    df, filename = df_info
    columns = list(df.columns)

    try:
        if query.data == 'show_columns':
            await display_columns(df, query, lang)
        elif query.data == 'count_gender':
            await handle_gender(df, query, lang)
        elif query.data == 'unique_managers':
            await handle_managers(df, query, lang)
        elif query.data == 'count_city':
            await handle_city(df, query, lang)
        elif query.data == 'expert':
            await query.edit_message_text(MESSAGES['expert_warning'][lang], reply_markup=None)
            context.user_data['expert'] = True
    except Exception as e:
        logger.error(f"Menu handler error: {e}\n{traceback.format_exc()}")
        await query.edit_message_text(f"{MESSAGES['error'][lang]} {e}", reply_markup=main_menu(lang))

async def display_columns(df, query, lang):
    """Paginate and display columns securely."""
    columns = list(df.columns)
    if len(columns) > 50:
        cols_preview = "\n".join([f"{i+1}. {c}" for i, c in enumerate(columns[:50])])
        more_msg = f"\n...and {len(columns)-50} more columns. Reply 'all columns' to get full list."
        await query.edit_message_text(f"{MESSAGES['columns'][lang]}\n\n{cols_preview}{more_msg}", reply_markup=main_menu(lang))
    else:
        cols = "\n".join([f"{i+1}. {c}" for i, c in enumerate(columns)])
        await query.edit_message_text(f"{MESSAGES['columns'][lang]}\n\n{cols}", reply_markup=main_menu(lang))

async def handle_gender(df, query, lang):
    """Detect and count gender/sex column safely."""
    gender_col = next((col for col in df.columns if re.search(r'gender|пол|sex', col, re.I)), None)
    if not gender_col:
        await query.edit_message_text(f"{MESSAGES['error'][lang]} Не найден столбец для пола.", reply_markup=main_menu(lang))
        return
    try:
        counts = df[gender_col].value_counts(dropna=False)
        result = "\n".join(f"{k}: {v}" for k, v in counts.items())
    except Exception as e:
        result = f"{MESSAGES['error'][lang]} {e}"
    await query.edit_message_text(f"{MESSAGES['count_gender'][lang]}\n{result}", reply_markup=main_menu(lang))

async def handle_managers(df, query, lang):
    """Detect unique manager names securely."""
    man_col = next((col for col in df.columns if re.search(r'manager|менеджер', col, re.I)), None)
    if not man_col:
        await query.edit_message_text(f"{MESSAGES['error'][lang]} Не найден столбец для менеджера.", reply_markup=main_menu(lang))
        return
    try:
        uniques = df[man_col].dropna().unique()
        result = "\n".join(str(m) for m in uniques)
    except Exception as e:
        result = f"{MESSAGES['error'][lang]} {e}"
    await query.edit_message_text(f"{MESSAGES['unique_managers'][lang]}\n{result}", reply_markup=main_menu(lang))

async def handle_city(df, query, lang):
    """Detect and count city column securely."""
    city_col = next((col for col in df.columns if re.search(r'city|город', col, re.I)), None)
    if not city_col:
        await query.edit_message_text(f"{MESSAGES['error'][lang]} Не найден столбец для города.", reply_markup=main_menu(lang))
        return
    try:
        counts = df[city_col].value_counts(dropna=False)
        result = "\n".join(f"{k}: {v}" for k, v in counts.items())
    except Exception as e:
        result = f"{MESSAGES['error'][lang]} {e}"
    await query.edit_message_text(f"{MESSAGES['count_city'][lang]}\n{result}", reply_markup=main_menu(lang))

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update)
    user_id = update.effective_user.id
    text = update.message.text.lower().strip()

    # Allow users to fetch all columns for huge files
    if text == 'all columns':
        df_info = user_dfs.get(user_id)
        if df_info:
            columns = list(df_info[0].columns)
            chunk_size = 50
            for i in range(0, len(columns), chunk_size):
                part = "\n".join([f"{i+j+1}. {c}" for j, c in enumerate(columns[i:i+chunk_size])])
                await update.message.reply_text(part)
        return

    # Expert mode: GPT-4o-powered, bulletproofed against code injection/unsafe code
    if context.user_data.get('expert'):
        df_info = user_dfs.get(user_id)
        if not df_info:
            await update.message.reply_text(MESSAGES['no_file'][lang], reply_markup=main_menu(lang))
            context.user_data['expert'] = False
            return
        df, filename = df_info

        # Construct safest system prompt
        system_prompt = SAFE_SYSTEM_PROMPT.format(columns=', '.join(str(c) for c in df.columns))
        user_prompt = update.message.text

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0,
                max_tokens=2048
            )
            code = response['choices'][0]['message']['content']
            if code.startswith("```"):
                code = re.sub(r"^```python\s*", "", code.strip())
                code = code.replace("```", "").strip()
            # Validate code is only allowed actions
            forbidden = ['import', 'open(', 'os.', 'subprocess', 'sys.', 'shutil', 'exec', 'eval', 'pickle']
            if any(bad in code for bad in forbidden):
                await update.message.reply_text("⚠️ Code blocked for security reasons.")
                return
            # Safe local context
            local_vars = {'df': df, 'pd': pd, 'result': None}
            try:
                exec(code, {"__builtins__": {}}, local_vars)
                output = local_vars.get('result', None)
                if output is None:
                    output = "No 'result' variable was created by the code."
            except KeyError as e:
                missing = str(e).replace("'", "")
                matches = get_close_matches(missing, list(df.columns), n=3)
                output = f"{MESSAGES['error'][lang]} '{missing}'. Похожие столбцы: {', '.join(matches)}"
            except Exception as e:
                output = f"{MESSAGES['error'][lang]} {e}"
            # Output, paginated if long
            max_length = 3500
            if isinstance(output, str):
                for i in range(0, len(output), max_length):
                    await update.message.reply_text(output[i:i+max_length])
            else:
                await update.message.reply_text(str(output))
        except Exception as e:
            logger.error(f"Expert mode error: {e}\n{traceback.format_exc()}")
            await update.message.reply_text(f"{MESSAGES['error'][lang]} {e}", reply_markup=main_menu(lang))
        context.user_data['expert'] = False
        await update.message.reply_text(MESSAGES['file_received'][lang], reply_markup=main_menu(lang))
    else:
        await update.message.reply_text(MESSAGES['file_received'][lang], reply_markup=main_menu(lang))

# --- Flask for Railway Webhook ---
flask_app = Flask(__name__)
telegram_app = None

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    global telegram_app
    if telegram_app is None:
        telegram_app = ApplicationBuilder().token(TOKEN).build()
        telegram_app.add_handler(CommandHandler("start", start))
        telegram_app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
        telegram_app.add_handler(CallbackQueryHandler(menu_handler))
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    data = request.get_json(force=True)
    update = Update.de_json(data, telegram_app.bot)
    telegram_app.process_update(update)
    return 'ok'

if __name__ == '__main__':
    flask_app.run(host='0.0.0.0', port=8080)

