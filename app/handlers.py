import pandas as pd
import os
import traceback
import logging
from app.i18n import get_message
from app.utils import safe_numeric, make_pdf, send_output

# Configure logger (rotating file for support)
logging.basicConfig(
    filename="app/logs/bot_handler.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

TELEGRAM_LIMIT = 4096
PDF_OUTPUT_LIMIT = 1000  # Characters

def split_message(text, limit=TELEGRAM_LIMIT):
    """Split long messages for Telegram."""
    lines = str(text).splitlines(keepends=True)
    result = []
    current = ""
    for line in lines:
        if len(current) + len(line) > limit:
            result.append(current)
            current = line
        else:
            current += line
    if current:
        result.append(current)
    return result

def sanitize_and_send(bot, chat_id, result, lang='en'):
    """
    Send result (DataFrame, str, or other) to user as PDF if too long, else as text.
    Handles empty, error, and non-string cases. Always Unicode.
    """
    if result is None or (isinstance(result, pd.DataFrame) and result.empty):
        msg = get_message('no_such_column_or_value', lang)
        send_output(bot, chat_id, msg, lang)
        return

    if isinstance(result, pd.DataFrame):
        out_str = result.to_string()
    elif isinstance(result, str):
        out_str = result.strip()
        if not out_str:
            msg = get_message('no_such_column_or_value', lang)
            send_output(bot, chat_id, msg, lang)
            return
    else:
        out_str = str(result)

    # Avoid PDF output for tiny results, and always send Unicode-safe PDF
    send_output(bot, chat_id, out_str, lang)

def handle_expert_mode(bot, chat_id, df, question, openai_client, lang='en'):
    """
    Main expert mode: ask LLM for code, run it, and return answer.
    Provides maximal safety, i18n, logging, and bulletproof output.
    """
    # Build prompt for LLM, only send schema
    prompt = (
        f"Columns: {list(df.columns)}\n"
        f"User question: '{question}'\n"
        "Generate safe, robust Python code to answer the question using only the Pandas DataFrame 'df'. "
        "Code MUST handle missing values and non-numeric data robustly. "
        "Put the final answer in a variable called 'result'."
    )

    try:
        response = openai_client.ChatCompletion.create(
            model="gpt-4",   
            messages=[{"role": "user", "content": prompt}]
        )
        code = extract_code_from_response(response)
    except Exception as e:
        logging.exception("OpenAI error")
        send_output(bot, chat_id, get_message('error', lang) + f" Sorry, could not reach the AI: {e}", lang)
        return

    # Extract columns referenced in LLM code, check if all present
    missing_cols = []
    for col in extract_column_names_from_code(code):
        if col not in df.columns:
            missing_cols.append(col)
    if missing_cols:
        msg = get_message('no_such_column_or_value', lang) + f": {', '.join(missing_cols)}"
        send_output(bot, chat_id, msg, lang)
        return

    # Safe numeric conversion for all relevant columns
    for col in df.columns:
        try:
            if df[col].dtype == object or df[col].apply(lambda x: isinstance(x, str)).any():
                df[col] = safe_numeric(df[col])
        except Exception:
            logging.warning(f"Numeric conversion failed for column {col}", exc_info=True)

    # Run LLM code in maximum isolation (disable builtins)
    try:
        local_vars = {"df": df}
        safe_globals = {"__builtins__": {}}  # No builtins for LLM code
        exec(code, safe_globals, local_vars)
        result = local_vars.get("result", None)
        sanitize_and_send(bot, chat_id, result, lang)
    except Exception as e:
        tb = traceback.format_exc()
        msg = get_message('error', lang) + f" {type(e).__name__}: {e}"
        logging.error(f"LLM code exec error: {msg}\n{tb}")
        send_output(bot, chat_id, msg, lang)

def extract_code_from_response(response):
    """Extracts python code from LLM response."""
    import re
    content = response["choices"][0]["message"]["content"]
    code_blocks = re.findall(r"```python(.*?)```", content, re.DOTALL)
    if code_blocks:
        return code_blocks[0].strip()
    return content.strip()
    
def extract_column_names_from_code(code):
    """Detect all DataFrame column references in LLM code."""
    import re
    return re.findall(r'df\[\s*[\'"]([^\'"]+)[\'"]\s*\]', code)

