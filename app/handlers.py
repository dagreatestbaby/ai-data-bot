import pandas as pd
import traceback
import os

TELEGRAM_LIMIT = 4096

def split_message(text, limit=TELEGRAM_LIMIT):
    lines = text.splitlines(keepends=True)
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

def send_long_message(bot, chat_id, text):
    for chunk in split_message(str(text)):
        bot.send_message(chat_id, chunk)

def handle_expert_mode(bot, chat_id, df, question, openai_client):
    # Step 1: Build prompt for LLM (schema only, never user data)
    prompt = (
        f"Columns: {list(df.columns)}\n"
        f"User question: '{question}'\n"
        "Generate safe Python code to answer using the Pandas DataFrame 'df'. "
        "Put the final answer in a variable called 'result'."
    )

    # Step 2: Get code from LLM (not data)
    code = None
    try:
        response = openai_client.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        # You must define extract_code_from_response to get the code block as a string
        code = extract_code_from_response(response)
    except Exception as e:
        send_long_message(bot, chat_id, f"Sorry, there was a problem reaching the AI: {e}")
        return

    # Step 3: Check for columns not in DataFrame
    missing_cols = []
    for col in extract_column_names_from_code(code):
        if col not in df.columns:
            missing_cols.append(col)
    if missing_cols:
        send_long_message(bot, chat_id, f"Sorry, the following columns do not exist: {missing_cols}\nAvailable: {list(df.columns)}")
        return

    # Step 4: Run code, handle all errors and long results
    try:
        local_vars = {"df": df}
        exec(code, {}, local_vars)
        result = local_vars.get("result")
        if result is None:
            send_long_message(bot, chat_id, "Sorry, the code did not produce any result.")
            return
        # Handle DataFrame results
        if isinstance(result, pd.DataFrame):
            if len(result) > 20:
                short = result.head(10).to_string()
                send_long_message(bot, chat_id, f"First 10 rows (of {len(result)}):\n{short}\n(Full result attached as CSV)")
                result.to_csv("expert_result.csv", index=False)
                with open("expert_result.csv", "rb") as f:
                    bot.send_document(chat_id, f)
                os.remove("expert_result.csv")
            else:
                send_long_message(bot, chat_id, result.to_string())
        # Handle long text/string results
        elif isinstance(result, str) and len(result) > TELEGRAM_LIMIT:
            send_long_message(bot, chat_id, result)
        else:
            send_long_message(bot, chat_id, str(result))
    except Exception as e:
        # Friendly error, not traceback
        send_long_message(bot, chat_id, f"Sorry, there was an error: {type(e).__name__}: {e}")

# --- You must implement these two helpers based on your LLM response format ---

def extract_code_from_response(response):
    # Your code here: parse out the code block from OpenAI's response
    # For example, if response["choices"][0]["message"]["content"] contains "```python\n ... \n```"
    import re
    content = response["choices"][0]["message"]["content"]
    code_blocks = re.findall(r"```python(.*?)```", content, re.DOTALL)
    if code_blocks:
        return code_blocks[0].strip()
    # fallback: return all if no code block
    return content.strip()

def extract_column_names_from_code(code):
    # Very basic: try to find all words after df[" or df['
    import re
    return re.findall(r'df\[\s*[\'"]([^\'"]+)[\'"]\s*\]', code)

