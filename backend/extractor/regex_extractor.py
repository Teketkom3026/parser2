"""Regex-извлечение: email, телефон, ИНН, КПП, соцсети."""
import re
from typing import Optional

import phonenumbers


def extract_emails(text: str) -> list[str]:
    pattern = r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
    emails = re.findall(pattern, text)
    filtered = []
    skip_ext = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.css', '.js', '.ico', '.woff', '.woff2')
    for e in emails:
        e_lower = e.lower().strip(".")
        if any(e_lower.endswith(ext) for ext in skip_ext):
            continue
        if len(e_lower) > 100:
            continue
        if e_lower.count("@") != 1:
            continue
        filtered.append(e_lower)
    return list(set(filtered))


def classify_email(email: str) -> str:
    """Классифицировать email: personal / corporate_general / corporate_personal."""
    general_prefixes = (
        "info", "office", "contact", "support", "admin", "mail",
        "hello", "sales", "hr", "help", "reception", "secretary",
        "priemnaya", "priemna", "buh", "zakaz",
    )
    local = email.split("@")[0].lower()
    if any(local.startswith(p) for p in general_prefixes):
        return "corporate_general"
    if "." in local or "_" in local or any(c.isdigit() for c in local[:3]):
        return "corporate_personal"
    return "corporate_personal"


def extract_phones(text: str, default_region: str = "RU") -> list[str]:
    """Извлечь и нормализовать телефоны (включая с доб.)."""
    results = set()
    # Паттерны для российских и международных номеров
    patterns = [
        r'(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?:\s*(?:доб\.?|ext\.?|#)\s*\d{1,6})?',
        r'\+\d{1,3}[\s\-]?\(?\d{2,5}\)?[\s\-]?\d{2,4}[\s\-]?\d{2,4}[\s\-]?\d{0,4}(?:\s*(?:доб\.?|ext\.?|#)\s*\d{1,6})?',
        r'\b\d{1}\s?\(\d{3}\)\s?\d{3}[\-\s]?\d{2}[\-\s]?\d{2}\b',
    ]
    for pat in patterns:
        for match in re.finditer(pat, text):
            raw = match.group().strip()
            try:
                parsed = phonenumbers.parse(raw, default_region)
                if phonenumbers.is_valid_number(parsed):
                    formatted = phonenumbers.format_number(
                        parsed,
                        phonenumbers.PhoneNumberFormat.INTERNATIONAL
                    )
                    results.add(formatted)
            except phonenumbers.NumberParseException:
                # Пробуем с явным +7 для 8-ки
                if raw.startswith("8") and len(re.sub(r'\D', '', raw)) == 11:
                    try:
                        parsed = phonenumbers.parse("+7" + re.sub(r'\D', '', raw)[1:], default_region)
                        if phonenumbers.is_valid_number(parsed):
                            formatted = phonenumbers.format_number(
                                parsed,
                                phonenumbers.PhoneNumberFormat.INTERNATIONAL
                            )
                            results.add(formatted)
                    except Exception:
                        pass
    return list(results)


def extract_inn(text: str) -> list[str]:
    """Извлечь ИНН (10 или 12 цифр)."""
    results = []
    inn_patterns = [
        r'ИНН[\s:]*(\\d{10,12})',
        r'инн[\s:]*(\d{10,12})',
        r'INN[\s:]*(\d{10,12})',
    ]
    for pat in inn_patterns:
        for m in re.finditer(pat, text):
            val = m.group(1)
            if len(val) in (10, 12):
                results.append(val)
    return list(set(results))


def extract_kpp(text: str) -> list[str]:
    """Извлечь КПП (9 цифр)."""
    results = []
    kpp_patterns = [
        r'КПП[\s:]*(\d{9})',
        r'кпп[\s:]*(\d{9})',
        r'KPP[\s:]*(\d{9})',
    ]
    for pat in kpp_patterns:
        for m in re.finditer(pat, text):
            results.append(m.group(1))
    return list(set(results))


def extract_social_links(html: str) -> list[str]:
    """Извлечь ссылки на соцсети."""
    social_patterns = [
        r'https?://(?:www\.)?linkedin\.com/in/[\w\-]+/?',
        r'https?://(?:www\.)?t\.me/[\w\-]+/?',
        r'https?://(?:www\.)?vk\.com/[\w\-]+/?',
        r'https?://(?:www\.)?facebook\.com/[\w\-.]+/?',
        r'https?://(?:www\.)?twitter\.com/[\w\-]+/?',
        r'https?://(?:www\.)?instagram\.com/[\w\-.]+/?',
    ]
    results = set()
    for pat in social_patterns:
        for m in re.finditer(pat, html, re.IGNORECASE):
            results.add(m.group(0).rstrip("/"))
    return list(results)


def extract_all_regex(html: str, text: str) -> dict:
    """Запустить все regex-экстракторы, вернуть сводный результат."""
    return {
        "emails": extract_emails(text),
        "phones": extract_phones(text),
        "inn": extract_inn(text),
        "kpp": extract_kpp(text),
        "social_links": extract_social_links(html),
    }
