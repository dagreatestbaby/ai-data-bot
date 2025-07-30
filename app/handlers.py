import pandas as pd
import logging
import os
from app.i18n import get_message
from app.utils import safe_numeric, sanitize_and_send, safe_telegram_output

# Ensure logs directory exists (best practice)
os.makedirs("app/logs", exist_ok=True)

logging.basicConfig(
    filename="app/logs/bot_handler.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

@safe_telegram_output
def handle_expert_mode(bot, chat_id, df, question, openai_client, lang='en'):
    """
    Main expert mode: get code from LLM, check, execute, return result. Bulletproof output.
    """
    prompt = (
        f"Columns: {list(df.columns)}\n"
        f"User question: '{question}'\n"
        "Generate safe, robust Python code to answer the question using only the Pandas DataFrame 'df'. "
        "Code MUST handle missing values and non-numeric data robustly. "
        "Put the final answer in a variable called 'result'."
    )

    response = openai_client.ChatCompletion.create(
        model="gpt-4",   
        messages=[{"role": "user", "content": prompt}]
    )
    code = extract_code_from_response(response)

    missing_cols = [
        col for col in extract_column_names_from_code(code)
        if col not in df.columns
    ]
    if missing_cols:
        msg = get_message('no_such_column_or_value', lang) + f": {', '.join(missing_cols)}"
        return msg

    for col in df.columns:
        try:
            if df[col].dtype == object or df[col].apply(lambda x: isinstance(x, str)).any():
                df[col] = safe_numeric(df[col])
        except Exception:
            logging.warning(f"Numeric conversion failed for column {col}", exc_info=True)

    local_vars = {"df": df}
    safe_globals = {"__builtins__": {}}  # No builtins for LLM code
    exec(code, safe_globals, local_vars)
    return local_vars.get("result", None)

def extract_code_from_response(response):
    import re
    content = response["choices"][0]["message"]["content"]
    code_blocks = re.findall(r"```python(.*?)```", content, re.DOTALL)
    if code_blocks:
        return code_blocks[0].strip()
    return content.strip()

def extract_column_names_from_code(code):
    import re
    return re.findall(r'df\[\s*[\'"]([^\'"]+)[\'"]\s*\]', code)

