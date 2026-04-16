"""Валидация и разбивка ФИО на составляющие."""
import re

# ── Паттерны ФИО ──────────────────────────────────────────────────────────────

# Русское ФИО: Фамилия Имя Отчество (все три части)
FIO_RU_FULL = re.compile(
    r'\b([А-ЯЁ][а-яё]{1,30})\s+'
    r'([А-ЯЁ][а-яё]{1,20})\s+'
    r'([А-ЯЁ][а-яё]{1,20}(?:на|вич|вна|ич|евна|ьич|ьевна)?)\b'
)

# Русское ФИО с инициалами: Иванов И.И. или Иванов И. И.
FIO_RU_INITIALS = re.compile(
    r'\b([А-ЯЁ][а-яё]{1,30})\s+([А-ЯЁ])\.\s*([А-ЯЁ])\.\b'
)

# Латинское ФИО: First Last или First Middle Last
FIO_EN_FULL = re.compile(
    r'\b([A-Z][a-z]{1,25})\s+(?:([A-Z][a-z]{1,25})\s+)?([A-Z][a-z]{1,25})\b'
)

# ── Стоп-слова: то что НЕ является именем ─────────────────────────────────────

# Русские должности и звания
_STOP_WORDS_RU = {
    "генеральный", "директор", "главный", "заместитель", "начальник",
    "руководитель", "менеджер", "инженер", "бухгалтер", "юрист", "технический",
    "коммерческий", "финансовый", "исполнительный", "операционный",
    "президент", "председатель", "управляющий", "партнёр", "партнер",
    "специалист", "аналитик", "консультант", "советник", "эксперт",
    "координатор", "ведущий", "старший", "младший", "первый",
    "региональный", "федеральный", "государственный", "министерством",
    "московского", "санкт-петербургского", "российской", "городского",
    "ломбарда", "совета", "федерации",
    # Организационные
    "ооо", "оао", "зао", "пао", "ип", "фгуп", "муп", "гуп",
    "ltd", "inc", "gmbh", "llc", "corp",
}

# Стоп-паттерны для целых строк — не могут быть именем
_STOP_PATTERNS = [
    re.compile(r'^\s*-\s+', re.I),                          # - директор...
    re.compile(r'^\s*—\s+', re.I),                          # — директор...
    re.compile(r'^\s*,\s+', re.I),                          # , директор...
    re.compile(r'^\s*\(', re.I),                             # (Директор)
    re.compile(r'^\s*\d+', re.I),                            # 74,6 миллиарда...
    re.compile(r'директор|менеджер|инженер|бухгалтер|юрист|специалист|руководитель|начальник|президент|председатель|управляющий|координатор|аналитик|советник|консультант|помощник', re.I),
    re.compile(r'\bчлен\b|\bсовет\b|\bкомиссии\b|\bпредставитель\b', re.I),
    re.compile(r'\bdirector\b|\bmanager\b|\bhead\b|\bchief\b|\bofficer\b|\bspecialist\b|\bconsultant\b|\bchef\b|\blegal\b|\bdepartment\b|\bdirectorate\b|\beducation\b|\bcorporate\b|\buniversity\b|\bmanagement\b|\brevenue\b', re.I),
    re.compile(r'ооо|оао|зао|пао|ltd|inc|gmbh|llc|corp', re.I),
    re.compile(r'университет|институт|академия|школа|колледж|college|university|school', re.I),
    re.compile(r'группа|group|holding|холдинг|концерн|корпорация|corporation', re.I),
    re.compile(r'москва|санкт-петербург|петербург|екатеринбург|новосибирск|казань|город|city|поселок', re.I),
    re.compile(r'отдел|department|управление|департамент|division|unit', re.I),
    re.compile(r'https?://', re.I),
    re.compile(r'\d{4,}'),                   # длинные числа
    re.compile(r'.{100,}'),                  # слишком длинная строка
]

# Минимальная длина имени (2 слова минимум)
_MIN_NAME_WORDS = 2


def _passes_stop_patterns(text: str) -> bool:
    """True если текст НЕ является мусором."""
    for pat in _STOP_PATTERNS:
        if pat.search(text):
            return False
    # Первое слово — стоп-слово?
    first_word = text.strip().split()[0].lower().rstrip('.,;:')
    if first_word in _STOP_WORDS_RU:
        return False
    return True


def is_valid_person_name(name: str) -> bool:
    """Проверить, является ли строка именем человека."""
    if not name or len(name.strip()) < 4:
        return False
    if not _passes_stop_patterns(name):
        return False
    # Должно содержать хотя бы 2 слова, начинающихся с заглавной буквы
    words = name.strip().split()
    if len(words) < _MIN_NAME_WORDS:
        return False
    capitalized = sum(1 for w in words if w and w[0].isupper())
    if capitalized < 2:
        return False
    return True


# Типичные окончания отчеств (помогают определить порядок слов)
_PATRONYMIC_ENDINGS = ('вич', 'вна', 'ьич', 'ьевна', 'ьична', 'овна', 'евна', 'ична')


def _is_patronymic(word: str) -> bool:
    return any(word.endswith(e) for e in _PATRONYMIC_ENDINGS)


def _is_firstname(word: str) -> bool:
    """Эвристика: имя короче фамилии и не оканчивается на патроним."""
    return not _is_patronymic(word) and 2 < len(word) < 15


def split_fio(full_name: str) -> dict:
    """Разбить ФИО на составляющие.

    Поддерживает форматы:
        Фамилия Имя Отчество
        Имя Отчество Фамилия
        Фамилия И.О.
        First Last (латинское)
    """
    result = {
        'last_name':  '',
        'first_name': '',
        'patronymic': '',
        'initials':   '',
    }
    if not full_name:
        return result

    name = full_name.strip()
    words = name.split()

    # Вариант: Фамилия И.О.
    m = FIO_RU_INITIALS.match(name)
    if m:
        result['last_name']  = m.group(1)
        result['first_name'] = m.group(2) + "."
        result['patronymic'] = m.group(3) + "."
        result['initials']   = f"{m.group(2)}.{m.group(3)}."
        return result

    if len(words) == 3:
        w0, w1, w2 = words
        # Определяем порядок: ФИО vs ИОФ vs ИФО
        if _is_patronymic(w2):
            # Фамилия Имя Отчество
            result['last_name']  = w0
            result['first_name'] = w1
            result['patronymic'] = w2
        elif _is_patronymic(w1):
            # Имя Отчество Фамилия (редкий вариант)
            result['last_name']  = w2
            result['first_name'] = w0
            result['patronymic'] = w1
        else:
            # Нет явного отчества — считаем Фамилия Имя Отчество
            result['last_name']  = w0
            result['first_name'] = w1
            result['patronymic'] = w2

        if result['first_name'] and result['patronymic']:
            fn = result['first_name'].rstrip('.')
            pn = result['patronymic'].rstrip('.')
            if fn and pn:
                result['initials'] = f"{fn[0]}.{pn[0]}."
        return result

    if len(words) == 2:
        result['last_name']  = words[0]
        result['first_name'] = words[1]
        result['initials']   = f"{words[1][0]}." if words[1] else ""
        return result

    # Латинское имя
    m = FIO_EN_FULL.match(name)
    if m:
        parts = [p for p in m.groups() if p]
        if len(parts) >= 2:
            result['last_name']  = parts[-1]
            result['first_name'] = parts[0]
            if len(parts) == 3:
                result['patronymic'] = parts[1]
        return result

    # Fallback: разбиваем по словам
    if len(words) >= 2:
        result['last_name']  = words[0]
        result['first_name'] = words[1]
        if len(words) >= 3:
            result['patronymic'] = words[2]

    return result
