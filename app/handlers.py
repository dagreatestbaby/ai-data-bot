import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.i18n import get_message
from app.utils import load_dataframe, get_columns, aggregate_column
from app.config import OPENAI_API_KEY
import openai

user_files = {}

def get_lang(update):
    return getattr(update.effective_user, "language_code", "en")[:2]

def main_menu(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_message('columns', lang), callback_data='show_columns')],
        [InlineKeyboardButton("💡 Expert", callback_data='expert')],
    ])

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update)
    await update.message.reply_text(get_message('start', lang))

async def file_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update)
    file = update.message.document
    new_file = await context.bot.get_file(file.file_id)
    file_bytes = await new_file.download_as_bytearray()
    user_files[update.effective_user.id] = file_bytes
    await update.message.reply_text(get_message('file_received', lang), reply_markup=main_menu(lang))

async def menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update)
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    file_bytes = user_files.get(user_id)
    if not file_bytes:
        await query.edit_message_text(get_message('no_file', lang))
        return
    df = load_dataframe(file_bytes)
    if query.data == 'show_columns':
        cols = get_columns(df)
        await query.edit_message_text(f"{get_message('columns', lang)}\n{cols}", reply_markup=main_menu(lang))
    elif query.data == 'expert':
        await query.edit_message_text(get_message('expert_prompt', lang))
        context.user_data['expert'] = True

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update)
    user_id = update.effective_user.id
    if context.user_data.get('expert'):
        file_bytes = user_files.get(user_id)
        if not file_bytes:
            await update.message.reply_text(get_message('no_file', lang), reply_markup=main_menu(lang))
            context.user_data['expert'] = False
            return
        df = load_dataframe(file_bytes)
        # Use LLM to interpret, but only allow whitelisted operations!
        prompt = (
            "You are an assistant for a Telegram data analytics bot. "
            "User can ask for: mean, sum, count, unique for any column. "
            "Reply ONLY in the format: <operation>:<column>\n"
            "Examples:\nmean:age\nsum:sales\nunique:gender"
        )
        user_query = update.message.text
        try:
            openai.api_key = OPENAI_API_KEY
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0.0,
                max_tokens=20
            )
            answer = response['choices'][0]['message']['content'].strip().lower()
            # Parse and validate!
            if ':' in answer:
                op, col = answer.split(':', 1)
                op, col = op.strip(), col.strip()
                if op in {"mean", "sum", "count", "unique"} and col in df.columns:
                    result = aggregate_column(df, col, op)
                else:
                    result = get_message('unsupported', lang)
            else:
                result = get_message('unsupported', lang)
            await update.message.reply_text(result, reply_markup=main_menu(lang))
        except Exception as e:
            logging.error(f"Expert mode error: {e}")
            await update.message.reply_text(get_message('error', lang) + str(e))
        context.user_data['expert'] = False
    else:
        await update.message.reply_text(get_message('file_received', lang), reply_markup=main_menu(lang))

