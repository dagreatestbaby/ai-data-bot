import numpy as np
import pandas as pd
import re
import io
import os
from fpdf import FPDF

# Try to use a Unicode font, fallback to default if missing
FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf"
]

def get_unicode_font_path():
    for path in FONTS:
        if os.path.exists(path):
            return path
    return None  # Will fallback to Arial

def safe_numeric(series):
    """
    Convert pandas Series to float, robust to Russian 'до 10', ranges, junk, empty, etc.
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
    Create a PDF from any Unicode text. Font fallback handled.
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

def send_output(bot, chat_id, text, lang='en', filename='result.pdf', char_limit=1000):
    """
    If text > char_limit, send as Unicode PDF. Else send as Telegram message.
    """
    if not text or text.strip() == "":
        from app.i18n import get_message
        msg = get_message('no_such_column_or_value', lang)
        bot.send_message(chat_id, msg)
        return
    if len(text) > char_limit or ('\n' in text and sum(len(line) for line in text.split('\n')) > char_limit):
        pdf = make_pdf(text, filename=filename)
        bot.send_document(chat_id, pdf)
    else:
        # Split to avoid Telegram hard limit
        for part in split_message(text):
            bot.send_message(chat_id, part)

TELEGRAM_LIMIT = 4096

def split_message(text, limit=TELEGRAM_LIMIT):
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

