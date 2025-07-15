import os
import logging
import re
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler
)
import pandas as pd
from io import BytesIO
from dotenv import load_dotenv
from difflib import get_close_matches
import tempfile
import traceback

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

try:
    import openai
    openai_version = openai.__version__
except Exception:
    openai = None
    openai_version = None

# === ENV, API, LOGGING ===
load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_KEY = os.getenv('OPENAI_API_KEY')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

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
        'ru': "Количество по городам (сырые данные):",
        'en': "Count by city (raw):",
    },
    'count_city_smart': {
        'ru': "Количество по главным городам (умно):",
        'en': "Count by main city (smart):",
    },
    'expert_warning': {
        'ru': "Экспертный режим: опишите свой запрос, используя названия столбцов из файла. Для графиков напишите 'сделай график ...'.",
        'en': "Expert mode: describe your request using the column names. For charts, say 'make a plot of ...'.",
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
    'count_city_smart_btn': {
        'ru': "Количество по главным городам (умно)",
        'en': "Count by main city (smart)",
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
        [InlineKeyboardButton(MESSAGES['count_city_smart_btn'][lang], callback_data='count_city_smart')],
        [InlineKeyboardButton(MESSAGES['expert_btn'][lang], callback_data='expert')]
    ])

async def send_long_message(bot_func, text, reply_markup=None):
    max_length = 3500
    first = True
    for i in range(0, len(text), max_length):
        chunk = text[i:i+max_length]
        if first:
            await bot_func(chunk, reply_markup=reply_markup)
            first = False
            reply_markup = None
        else:
            await bot_func(chunk)

def smart_city_extractor(val):
    """
    Extracts the main city name from a messy entry:
    - Takes only the first city before a comma
    - Removes anything in brackets ()
    - Strips whitespace
    - Keeps only the city name (e.g., 'Москва', 'Омск')
    """
    if not isinstance(val, str):
        return ''
    # Remove content in brackets
    val = re.sub(r'\(.*?\)', '', val)
    # Take only up to first comma
    val = val.split(',')[0]
    # Now strip, and remove extra punctuation
    val = val.replace('.', '').replace(':', '')
    val = val.strip()
    # If still multiple words, take first "capitalized" word (very basic)
    city = val.split(' ')[0] if val else ''
    return city

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update)
    await update.message.reply_text(MESSAGES['start'][lang])

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update)
    file = update.message.document
    file_id = file.file_id
    try:
        new_file = await context.bot.get_file(file_id)
        file_bytes = await new_file.download_as_bytearray()
        user_files[update.effective_user.id] = file_bytes
        await update.message.reply_text(MESSAGES['file_received'][lang], reply_markup=main_menu(lang))
    except Exception as e:
        await update.message.reply_text(f"{MESSAGES['error'][lang]} {e}")

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update)
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    await context.bot.send_chat_action(chat_id=query.message.chat.id, action=ChatAction.TYPING)
    file_bytes = user_files.get(user_id)
    if not file_bytes:
        await query.edit_message_text(MESSAGES['no_file'][lang])
        return
    try:
        try:
            df = pd.read_excel(BytesIO(file_bytes))
        except Exception:
            try:
                df = pd.read_csv(BytesIO(file_bytes), encoding='utf-8')
            except Exception:
                df = pd.read_csv(BytesIO(file_bytes), encoding='cp1251')
        for col in df.columns:
            df[col] = df[col].astype(str).fillna('')
    except Exception as e:
        await query.edit_message_text(f"{MESSAGES['error'][lang]} {e}")
        return

    if query.data == 'show_columns':
        cols = "\n".join(str(c) for c in df.columns)
        text = f"{MESSAGES['columns'][lang]}\n\n{cols}"
        await send_long_message(lambda t, reply_markup=None: query.edit_message_text(t, reply_markup=reply_markup), text, reply_markup=main_menu(lang))

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
            result = "\n".join(f"{k}: {v}" for k, v in counts.items())
        except Exception as e:
            result = f"{MESSAGES['error'][lang]} {e}"
        text = f"{MESSAGES['count_gender'][lang]}\n{result}"
        await send_long_message(lambda t, reply_markup=None: query.edit_message_text(t, reply_markup=reply_markup), text, reply_markup=main_menu(lang))

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
        text = f"{MESSAGES['unique_managers'][lang]}\n{result}"
        await send_long_message(lambda t, reply_markup=None: query.edit_message_text(t, reply_markup=reply_markup), text, reply_markup=main_menu(lang))

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
            result = "\n".join(f"{k}: {v}" for k, v in counts.items())
        except Exception as e:
            result = f"{MESSAGES['error'][lang]} {e}"
        text = f"{MESSAGES['count_city'][lang]}\n{result}"
        await send_long_message(lambda t, reply_markup=None: query.edit_message_text(t, reply_markup=reply_markup), text, reply_markup=main_menu(lang))

    elif query.data == 'count_city_smart':
        city_col = None
        for col in df.columns:
            if 'city' in col.lower() or 'город' in col.lower():
                city_col = col
                break
        if not city_col:
            await query.edit_message_text(f"{MESSAGES['error'][lang]} Не найден столбец для города.", reply_markup=main_menu(lang))
            return
        # SMART GROUPING:
        try:
            df['__city_smart__'] = df[city_col].apply(smart_city_extractor)
            counts = df['__city_smart__'].value_counts()
            result = "\n".join(f"{k}: {v}" for k, v in counts.items() if k and k.lower() != 'nan')
        except Exception as e:
            result = f"{MESSAGES['error'][lang]} {e}"
        text = f"{MESSAGES['count_city_smart'][lang]}\n{result}"
        await send_long_message(lambda t, reply_markup=None: query.edit_message_text(t, reply_markup=reply_markup), text, reply_markup=main_menu(lang))

    elif query.data == 'expert':
        await query.edit_message_text(MESSAGES['expert_warning'][lang], reply_markup=None)
        context.user_data['expert'] = True

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update)
    user_id = update.effective_user.id
    if context.user_data.get('expert'):
        await update.message.chat.send_action(action=ChatAction.TYPING)
        file_bytes = user_files.get(user_id)
        if not file_bytes:
            await update.message.reply_text(MESSAGES['no_file'][lang], reply_markup=main_menu(lang))
            context.user_data['expert'] = False
            return
        try:
            try:
                df = pd.read_excel(BytesIO(file_bytes))
            except Exception:
                try:
                    df = pd.read_csv(BytesIO(file_bytes), encoding='utf-8')
                except Exception:
                    df = pd.read_csv(BytesIO(file_bytes), encoding='cp1251')
            for col in df.columns:
                df[col] = df[col].astype(str).fillna('')
        except Exception as e:
            await update.message.reply_text(f"{MESSAGES['error'][lang]} {e}", reply_markup=main_menu(lang))
            context.user_data['expert'] = False
            return

        system_prompt = (
            "You are a Python code generator for a Telegram data analytics bot. "
            "The user gives you a DataFrame 'df' and a task. "
            "ALWAYS output ONLY valid Python code, using only the columns provided below. "
            "ALWAYS create a string variable named 'result' with the answer (do NOT use print()). "
            "If user requests a chart or plot, save the chart as 'plot.png' and say RESULT_IS_PLOT. "
            "Handle missing columns gracefully. Never import or run dangerous code. "
            "File columns: " + ', '.join(str(c) for c in df.columns)
        )
        user_prompt = update.message.text
        try:
            code = None
            if openai_version and openai_version.startswith('0.'):
                openai.api_key = OPENAI_KEY
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.0,
                    max_tokens=2048
                )
                code = response['choices'][0]['message']['content']
            else:
                client = openai.OpenAI(api_key=OPENAI_KEY)
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.0,
                    max_tokens=2048
                )
                code = response.choices[0].message.content

            if code and code.startswith("```"):
                code = code.split('```')[1]
                code = code.replace('python', '', 1).strip()

            with tempfile.TemporaryDirectory() as tmpdir:
                local_vars = {'df': df, 'pd': pd, 'plt': plt, 'result': None}
                old_cwd = os.getcwd()
                os.chdir(tmpdir)
                try:
                    exec(code, {}, local_vars)
                    output = local_vars.get('result', None)
                    # If chart produced
                    if isinstance(output, str) and "RESULT_IS_PLOT" in output and os.path.exists('plot.png'):
                        with open('plot.png', 'rb') as imgfile:
                            await update.message.reply_photo(imgfile, caption="📊 Chart generated.")
                        output = None
                except KeyError as e:
                    missing = str(e).replace("'", "")
                    matches = get_close_matches(missing, list(df.columns), n=3)
                    output = f"{MESSAGES['error'][lang]} '{missing}'. Похожие столбцы: {', '.join(matches)}"
                except Exception as e:
                    tb = traceback.format_exc()
                    output = f"{MESSAGES['error'][lang]} {e}\n{tb[:500]}"
                finally:
                    os.chdir(old_cwd)
            # Output result (split if needed)
            if output:
                await send_long_message(lambda t, reply_markup=None: update.message.reply_text(t), str(output))
        except Exception as e:
            await update.message.reply_text(f"{MESSAGES['error'][lang]} {e}", reply_markup=main_menu(lang))
        context.user_data['expert'] = False
        await update.message.reply_text(MESSAGES['file_received'][lang], reply_markup=main_menu(lang))
    else:
        await update.message.reply_text(MESSAGES['file_received'][lang], reply_markup=main_menu(lang))

if __name__ == '__main__':
    print("🚀 AI_DATA_BOT: RUNNING ULTRA-ROBUST VERSION")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(CallbackQueryHandler(menu_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

