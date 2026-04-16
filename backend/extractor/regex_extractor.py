"""Regex-извлечение: email, телефон, ИНН, КПП, соцсети."""
import re
from typing import Optional

import phonenumbers


def extract_emails(text: str) -> list[str]:
    pattern = r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
    emails = re.findall(pattern, text)
    filtered = []
    skip_ext = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.css', '.js',
                '.ico', '.woff', '.woff2', '.ttf', '.eot', '.webp')
    for e in emails:
        e_lower = e.lower().strip(".")
        if any(e_lower.endswith(ext) for ext in skip_ext):
            continue
        if len(e_lower) > 100:
            continue
        if e_lower.count("@") != 1:
            continue
        # Фильтр явно технических адресов
        local = e_lower.split("@")[0]
        if local in ('noreply', 'no-reply', 'donotreply', 'postmaster',
                     'mailer-daemon', 'bounce', 'abuse', 'spam'):
            continue
        filtered.append(e_lower)
    return list(dict.fromkeys(filtered))  # deduplicate, preserve order


def classify_email(email: str) -> str:
    """Классифицировать email: personal / corporate_general / corporate_personal."""
    general_prefixes = (
        "info", "office", "contact", "support", "admin", "mail",
        "hello", "sales", "hr", "help", "reception", "secretary",
        "priemnaya", "priemna", "buh", "zakaz", "manager",
        "department", "team", "service", "request",
    )
    local = email.split("@")[0].lower()
    if any(local == p or local.startswith(p + ".") for p in general_prefixes):
        return "corporate_general"
    return "corporate_personal"


def extract_phones(text: str, default_region: str = "RU") -> list[str]:
    """Извлечь и нормализовать телефоны (включая с доб.)."""
    results = []
    seen_normalized = set()

    # Паттерны для российских и международных номеров
    patterns = [
        r'(?:\+7|8|7)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
        r'(?:\s*(?:доб\.?|ext\.?|#)\s*\d{1,6})?',
        r'\+\d{1,3}[\s\-]?\(?\d{2,5}\)?[\s\-]?\d{2,4}[\s\-]?\d{2,4}[\s\-]?\d{0,4}'
        r'(?:\s*(?:доб\.?|ext\.?|#)\s*\d{1,6})?',
        r'\b\d{1}\s?\(\d{3}\)\s?\d{3}[\-\s]?\d{2}[\-\s]?\d{2}\b',
    ]

    for pat in patterns:
        for match in re.finditer(pat, text):
            raw = match.group().strip()
            # Выделяем добавочный, если есть
            dob_match = re.search(r'(доб\.?\s*\d+|ext\.?\s*\d+|#\s*\d+)$', raw, re.I)
            dob_suffix = ""
            base_raw = raw
            if dob_match:
                dob_suffix = " " + dob_match.group().strip()
                base_raw = raw[:dob_match.start()].strip()

            try:
                parsed = phonenumbers.parse(base_raw, default_region)
                if phonenumbers.is_valid_number(parsed):
                    formatted = phonenumbers.format_number(
                        parsed,
                        phonenumbers.PhoneNumberFormat.INTERNATIONAL
                    )
                    full = formatted + dob_suffix
                    if formatted not in seen_normalized:
                        seen_normalized.add(formatted)
                        results.append(full)
            except phonenumbers.NumberParseException:
                if base_raw.startswith("8") and len(re.sub(r'\D', '', base_raw)) == 11:
                    try:
                        parsed = phonenumbers.parse(
                            "+7" + re.sub(r'\D', '', base_raw)[1:], default_region
                        )
                        if phonenumbers.is_valid_number(parsed):
                            formatted = phonenumbers.format_number(
                                parsed,
                                phonenumbers.PhoneNumberFormat.INTERNATIONAL
                            )
                            full = formatted + dob_suffix
                            if formatted not in seen_normalized:
                                seen_normalized.add(formatted)
                                results.append(full)
                    except Exception:
                        pass

    return results


def extract_inn(text: str) -> list[str]:
    """Извлечь ИНН (10 или 12 цифр)."""
    results = []
    # Паттерны без экранирования в строке
    inn_patterns = [
        r'[Ии][Нн][Нн]\s*[:\-]?\s*(\d{10,12})',
        r'INN\s*[:\-]?\s*(\d{10,12})',
        # ИНН без ключевого слова рядом с КПП
        r'(\d{10})\s*/\s*\d{9}',  # ИНН/КПП формат
    ]
    for pat in inn_patterns:
        for m in re.finditer(pat, text):
            val = m.group(1)
            if len(val) in (10, 12) and val not in results:
                results.append(val)
    return results


def extract_kpp(text: str) -> list[str]:
    """Извлечь КПП (9 цифр)."""
    results = []
    kpp_patterns = [
        r'[Кк][Пп][Пп]\s*[:\-]?\s*(\d{9})',
        r'KPP\s*[:\-]?\s*(\d{9})',
        # ИНН/КПП формат
        r'\d{10}\s*/\s*(\d{9})',
    ]
    for pat in kpp_patterns:
        for m in re.finditer(pat, text):
            val = m.group(1)
            if val not in results:
                results.append(val)
    return results


def extract_social_links(html: str) -> list[str]:
    """Извлечь ссылки на соцсети."""
    social_patterns = [
        r'https?://(?:www\.)?linkedin\.com/in/[\w\-]+/?',
        r'https?://(?:www\.)?t\.me/[\w\-]+/?',
        r'https?://(?:www\.)?vk\.com/[\w\-./]+/?',
        r'https?://(?:www\.)?facebook\.com/[\w\-.]+/?',
        r'https?://(?:www\.)?twitter\.com/[\w\-]+/?',
        r'https?://(?:www\.)?instagram\.com/[\w\-.]+/?',
        r'https?://(?:www\.)?ok\.ru/[\w\-.]+/?',
        r'https?://(?:www\.)?tiktok\.com/@[\w\-.]+/?',
    ]
    results = []
    seen = set()
    for pat in social_patterns:
        for m in re.finditer(pat, html, re.IGNORECASE):
            url = m.group(0).rstrip("/")
            if url not in seen:
                seen.add(url)
                results.append(url)
    return results


def extract_all_regex(html: str, text: str) -> dict:
    """Запустить все regex-экстракторы, вернуть сводный результат."""
    return {
        "emails": extract_emails(text),
        "phones": extract_phones(text),
        "inn": extract_inn(text),
        "kpp": extract_kpp(text),
        "social_links": extract_social_links(html),
    }
