from app.utils import load_dataframe, get_columns, aggregate_column, safe_send_message
from app.i18n import get_message
from app.config import OPENAI_API_KEY
import openai

user_files = {}

def handle_start(update, context):
    lang = "ru" if update.effective_user.language_code == "ru" else "en"
    safe_send_message(context.bot, update.effective_chat.id, get_message('start', lang))

def handle_file(update, context):
    lang = "ru" if update.effective_user.language_code == "ru" else "en"
    file = update.message.document.get_file()
    file_bytes = file.download_as_bytearray()
    try:
        df = load_dataframe(file_bytes)
        user_files[update.effective_user.id] = df
        safe_send_message(context.bot, update.effective_chat.id, get_message('file_received', lang))
    except Exception as e:
        safe_send_message(context.bot, update.effective_chat.id, f"{get_message('error', lang)} {e}")

def handle_columns(update, context):
    lang = "ru" if update.effective_user.language_code == "ru" else "en"
    df = user_files.get(update.effective_user.id)
    if df is None:
        safe_send_message(context.bot, update.effective_chat.id, get_message('no_file', lang))
    else:
        cols = get_columns(df)
        safe_send_message(context.bot, update.effective_chat.id, f"{get_message('columns', lang)}\n{cols}")

def handle_stat(update, context):
    lang = "ru" if update.effective_user.language_code == "ru" else "en"
    df = user_files.get(update.effective_user.id)
    if df is None:
        safe_send_message(context.bot, update.effective_chat.id, get_message('no_file', lang))
        return
    try:
        args = context.args
        if len(args) < 2:
            safe_send_message(context.bot, update.effective_chat.id, get_message('unsupported', lang))
            return
        column, op = args[0], args[1]
        result = aggregate_column(df, column, op)
        safe_send_message(context.bot, update.effective_chat.id, result)
    except Exception as e:
        safe_send_message(context.bot, update.effective_chat.id, f"{get_message('error', lang)} {e}")

def handle_expert(update, context):
    lang = "ru" if update.effective_user.language_code == "ru" else "en"
    df = user_files.get(update.effective_user.id)
    if df is None:
        safe_send_message(context.bot, update.effective_chat.id, get_message('no_file', lang))
        return
    prompt = update.message.text
    context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant who answers data questions. The DataFrame columns are: " + ", ".join([str(c) for c in df.columns])},
                {"role": "user", "content": f"Columns: {', '.join([str(c) for c in df.columns])}\nPrompt: {prompt}"}
            ],
            api_key=OPENAI_API_KEY,
            temperature=0
        )
        reply = completion.choices[0].message['content']
        safe_send_message(context.bot, update.effective_chat.id, reply)
    except Exception as e:
        safe_send_message(context.bot, update.effective_chat.id, f"{get_message('error', lang)} {e}")

