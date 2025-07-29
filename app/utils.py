import pandas as pd
from io import BytesIO

def load_dataframe(file_bytes: bytes) -> pd.DataFrame:
    try:
        return pd.read_excel(BytesIO(file_bytes))
    except Exception:
        return pd.read_csv(BytesIO(file_bytes), encoding='utf-8')

def get_columns(df: pd.DataFrame) -> str:
    return "\n".join(str(c) for c in df.columns)

def aggregate_column(df: pd.DataFrame, column: str, operation: str) -> str:
    if column not in df.columns:
        return f"Column {column} not found."
    try:
        df[column] = pd.to_numeric(df[column], errors='coerce')
        if operation == "mean":
            return f"Mean of {column}: {df[column].mean()}"
        elif operation == "sum":
            return f"Sum of {column}: {df[column].sum()}"
        elif operation == "count":
            return f"Count of {column}: {df[column].count()}"
        elif operation == "unique":
            uniques = df[column].unique()
            uniques = [str(u) for u in uniques if pd.notnull(u)]
            preview = ', '.join(uniques[:20])
            if len(uniques) > 20:
                preview += f", ...and {len(uniques)-20} more"
            return f"Unique values of {column}: {preview}"
        else:
            return "Unsupported operation."
    except Exception as e:
        return f"Error: {e}"

def safe_send_message(bot, chat_id, text):
    MAX_LEN = 4000
    if isinstance(text, str):
        for i in range(0, len(text), MAX_LEN):
            bot.send_message(chat_id=chat_id, text=text[i:i+MAX_LEN])
    elif isinstance(text, list):
        for item in text:
            safe_send_message(bot, chat_id, item)
    else:
        safe_send_message(bot, chat_id, str(text))

