"""Определение языка страницы.""" from langdetect import detect, LangDetectException def detect_language(text: str) -> str: """Определить язык текста. Возвращает ISO 639-1 код в верхнем регистре.""" if not text or len(text.strip()) < 20: return "UNKNOWN" try: lang = detect(text[:5000]) return lang.upper() except LangDetectException: return "UNKNOWN"
ЧАСТЬ 4/7: BLACKLIST + OUTPUT
(Excel)

+

STORAGE

MODELS

+

TASK

MANAGER