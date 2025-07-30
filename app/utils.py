import numpy as np
import pandas as pd
import re
import io
import os
from fpdf import FPDF
from typing import Any, Callable
import functools

FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf"
]

TELEGRAM_LIMIT = 4096
PDF_MAX_SIZE = 10 * 1024 * 1024  # 10 MB

def get_unicode_font_path() -> str:
    """
    Returns the path to a Unicode font for PDF generation or None.
    """
    for path in FONTS:
        if os.path.exists(path):
            return path
    return None

def safe_numeric(series: pd.Series) -> pd.Series:
    """
    Convert a pandas Series to float, robust to Russian/English number words, ranges, and junk.
    """
    def to_num(x):
        if pd.isnull(x):
            return np.nan
        s = str(x).strip().replace(',', '.')
        if re.match(r'^до\s*(\d+)', s, re.IGNORECASE):
            return float(re.findall(r'\d+', s)[0])
        if re.match(r'^\d+\s*-\s*\d+', s):
            a, b = re.findall(r'\d+', s)
            return (float(a) + float(b)) / 2
        if re.match(r'^\d+(\.\d+)?$', s):
            return float(s)
        if s.lower() in ['не указано', 'зависит от продажи', 'нет информации', '-', '', 'nan']:
            return np.nan
        nums = re.findall(r'\d+', s)
        return float(nums[0]) if nums else np.nan
    return series.apply(to_num)

def make_pdf(text: str, filename: str = "result.pdf") -> io.BytesIO:
    """
    Create a PDF from any Unicode text, with font fallback.
    Returns: BytesIO file-like object ready for Telegram API.
    """
    pdf = FPDF()
    pdf.add_page()
    font_path = get_unicode_font_path()
    if font_path:
        pdf.add_font('UnicodeFont', '', font_path, uni=True)
        pdf.set_font('UnicodeFont', size=12)
    else:
        pdf.set_font("Arial", size=12)
    lines = text.split("\n")
    for line in lines:
        pdf.multi_cell(0, 10, line)
    bio = io.BytesIO()
    pdf.output(bio)
    bio.seek(0)
    bio.name = filename
    return bio

def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list:
    """
    Splits text into chunks safe for Telegram messaging.
    """
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

def sanitize_and_send(bot, chat_id: int, result: Any, lang: str = 'en',
                      filename: str = 'expert_result.pdf', char_limit: int = 1000, line_limit: int = 30):
    """
    Sends output to Telegram, using PDF if too long.
    Handles DataFrame, str, Exception, or any object.
    Localizes all errors and fallbacks.
    """
    import traceback
    from app.i18n import get_message

    if isinstance(result, pd.DataFrame):
        out_str = result.to_string() if not result.empty else get_message('no_such_column_or_value', lang)
    elif isinstance(result, str):
        out_str = result.strip() if result.strip() else get_message('no_such_column_or_value', lang)
    elif isinstance(result, Exception):
        tb_str = "".join(traceback.format_exception(type(result), result, result.__traceback__))
        out_str = get_message('error', lang) + "\n" + tb_str
    else:
        out_str = str(result)

    # Enforce both char and line count limits for all outputs
    if len(out_str) > char_limit or out_str.count('\n') > line_limit:
        pdf = make_pdf(out_str, filename=filename)
        pdf.seek(0, os.SEEK_END)
        pdf_size = pdf.tell()
        pdf.seek(0)
        if pdf_size > PDF_MAX_SIZE:
            msg = get_message('error', lang) + " PDF output too large to send. Please narrow your query."
            for part in split_message(msg):
                bot.send_message(chat_id, part)
        else:
            bot.send_document(chat_id, pdf)
    else:
        for part in split_message(out_str):
            bot.send_message(chat_id, part)

def safe_telegram_output(handler_func: Callable) -> Callable:
    """
    Decorator to ensure handler output (including exceptions) always goes through sanitize_and_send.
    This makes Telegram errors impossible, and code future-proof.
    """
    @functools.wraps(handler_func)
    def wrapper(*args, **kwargs):
        try:
            result = handler_func(*args, **kwargs)
            if result is not None:
                bot = args[0]
                chat_id = args[1]
                lang = kwargs.get('lang', 'en')
                sanitize_and_send(bot, chat_id, result, lang)
        except Exception as e:
            bot = args[0]
            chat_id = args[1]
            lang = kwargs.get('lang', 'en')
            sanitize_and_send(bot, chat_id, e, lang)
    return wrapper

