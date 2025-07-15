viewed_count = df['Просмотрено менеджером (да/нет)'].str.lower().str.strip().value_counts().get('да', 0)
result = f"Number of interviews viewed by managers: {str(viewed_count)}"