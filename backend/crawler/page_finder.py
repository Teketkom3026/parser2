"""Поиск разделов «Руководство», «Команда», «Контакты» на сайте."""

import json
import re
from pathlib import Path
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup

from backend.utils.logger import get_logger

logger = get_logger("page_finder")

# Ключевые слова для поиска нужных разделов
NAV_KEYWORDS_RU = [
    "руководство", "команда", "о компании", "о нас", "контакты",
    "структура", "менеджмент", "управление", "дирекция", "коллектив",
    "наша команда", "сотрудники", "правление", "совет директоров",
    "лидеры", "специалисты", "staff", "personel",
]

NAV_KEYWORDS_EN = [
    "team", "leadership", "management", "about", "about us",
    "contacts", "our team", "executives", "board", "directors",
    "staff", "people", "who we are",
]

ALL_KEYWORDS = NAV_KEYWORDS_RU + NAV_KEYWORDS_EN

# URL- паттерны
URL_PATTERNS = [
    r"/team", r"/about", r"/management", r"/leadership",
    r"/contacts", r"/kontakty", r"/o-kompanii", r"/rukovodstvo",
    r"/komanda", r"/staff", r"/people", r"/executives",
    r"/struktura", r"/board", r"/our-team", r"/o-nas",
    r"/direkciya", r"/pravlenie",
]


def find_relevant_links(html: str, base_url: str) -> list[str]:
    """Найти ссылки на разделы руководства/команды/контактов."""
    soup = BeautifulSoup(html, "lxml")
    found = []
    seen = set()

    base_domain = urlparse(base_url).netloc

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        text = a_tag.get_text(strip=True).lower()

        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue

        full_url = urljoin(base_url, href)
        link_domain = urlparse(full_url).netloc

        # Только внутренние ссылки
        if link_domain != base_domain:
            continue

        if full_url in seen:
            continue

        # Проверяем текст ссылки
        text_match = any(kw in text for kw in ALL_KEYWORDS)

        # Проверяем URL- паттерн
        url_path = urlparse(full_url).path.lower()
        url_match = any(re.search(pat, url_path) for pat in URL_PATTERNS)

        if text_match or url_match:
            seen.add(full_url)
            found.append(full_url)

    # Приоритизация: руководство/команда выше контактов
    def priority(url: str) -> int:
        path = urlparse(url).path.lower()
        if any(w in path for w in ["team", "komanda", "rukovodstvo", "management",
"leadership"]):

            return 0
        if any(w in path for w in ["about", "o-kompanii", "o-nas"]):
            return 1
        if any(w in path for w in ["contact", "kontakt"]):
            return 2
        return 3

    found.sort(key=priority)
    return found


def is_contact_page(html: str) -> bool:
    """Определить, содержит ли страница контактную информацию сотрудников."""
    text = html.lower()

    # Ищем характерные паттерны
    has_names = bool(re.search(
        r'[ А-ЯЁ][а-яё]+\ s+[ А-ЯЁ][а-яё]+\ s+[ А-ЯЁ][а-яё]+', html
    ))
    has_positions = any(kw in text for kw in [
        "директор", "руководитель", "начальник", "менеджер",
        "инженер", "бухгалтер", "юрист", "ceo", "cto", "cfo",
        "manager", "director", "head of", "chief",
    ])
    has_email = bool(re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', html))

    return (has_names and has_positions) or (has_positions and has_email)