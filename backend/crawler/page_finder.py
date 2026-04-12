"""Поиск страниц с командой, сотрудниками, контактами."""
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

# Ключевые слова в URL, сигнализирующие о странице с командой/контактами
CONTACT_URL_KEYWORDS = [
    # Русские
    "команда", "kontakty", "sotrudniki", "rukovodstvo", "о-нас",
    "o-nas", "o-kompanii", "nasha-komanda", "contacts", "contact",
    "about", "team", "staff", "people", "leadership", "management",
    "about-us", "our-team", "who-we-are", "руководство", "сотрудники",
    # Прочие
    "kontakt", "uber-uns", "equipe", "nosotros",
]

# Ключевые слова в тексте ссылок
CONTACT_LINK_TEXTS = [
    "команда", "команде", "наша команда", "контакты", "о компании", "о нас",
    "сотрудники", "руководство", "коллектив", "специалисты",
    "contacts", "contact us", "about", "our team", "team", "staff",
    "leadership", "management", "meet us", "people",
]


def is_contact_page(url: str, link_text: str = "") -> bool:
    url_lower = url.lower()
    text_lower = link_text.lower().strip()
    for kw in CONTACT_URL_KEYWORDS:
        if kw in url_lower:
            return True
    for kw in CONTACT_LINK_TEXTS:
        if kw in text_lower:
            return True
    return False


def find_relevant_links(html: str, base_url: str) -> list[str]:
    """Найти все ссылки на страницы с командой/контактами."""
    soup = BeautifulSoup(html, "lxml")
    base_parsed = urlparse(base_url)
    base_domain = base_parsed.netloc

    relevant = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        link_text = a.get_text(strip=True)

        # Нормализуем URL
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)

        # Только тот же домен, только http/https
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc != base_domain:
            continue

        # Убираем якоря и query
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if clean_url in seen or clean_url == base_url:
            continue

        if is_contact_page(clean_url, link_text):
            seen.add(clean_url)
            relevant.append(clean_url)

    # Дополнительно — стандартные URL-паттерны (даже если нет ссылки)
    common_paths = [
        "/contacts/", "/kontakty/", "/about/", "/team/",
        "/kontakty/nasha-komanda/", "/about/team/", "/o-nas/",
        "/o-kompanii/", "/company/team/", "/about-us/", "/our-team/",
        "/contact/", "/staff/", "/management/", "/leadership/",
        "/contacts", "/kontakty", "/about", "/team",
    ]
    for path in common_paths:
        url = f"{base_parsed.scheme}://{base_domain}{path}"
        if url not in seen and url != base_url:
            seen.add(url)
            relevant.append(url)

    return relevant
