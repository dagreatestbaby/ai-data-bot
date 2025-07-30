MESSAGES = {
    'start': {
        'en': "👋 Hello! Upload your Excel/CSV file to begin.",
        'ru': "👋 Привет! Загрузите файл Excel/CSV, чтобы начать.",
    },
    'file_received': {
        'en': "File received! Choose an action.",
        'ru': "Файл получен! Выберите действие.",
    },
    'no_file': {
        'en': "Please upload your file first.",
        'ru': "Пожалуйста, сначала загрузите файл.",
    },
    'columns': {
        'en': "File columns:",
        'ru': "Столбцы файла:",
    },
    'expert_prompt': {
        'en': "Expert mode: describe your query. (e.g. 'Show mean of column X')",
        'ru': "Экспертный режим: опишите свой запрос (например, 'Показать среднее по столбцу X')",
    },
    'error': {
        'en': "❗ Error:",
        'ru': "❗ Ошибка:",
    },
    'unsupported': {
        'en': "Sorry, I can't do that yet.",
        'ru': "Извините, я не могу выполнить этот запрос.",
    },
    'no_such_column_or_value': {
        'en': "No such column or value",
        'ru': "Нет такой колонки или значения",
    },
}

def get_message(key: str, lang: str = "en") -> str:
    """
    Get a localized message for a given key and language, fallback to English.
    """
    return MESSAGES.get(key, {}).get(lang, MESSAGES[key]['en'])

