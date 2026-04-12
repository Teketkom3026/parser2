"""Очистка HTML для извлечения текста."""

import re
from bs4 import BeautifulSoup


def clean_html(html: str) -> str:
    """Удалить скрипты, стили, навигацию и извлечь текст."""
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript", "iframe", "svg", "meta", "link"]):
        tag.decompose()

    for tag in soup.find_all(["nav", "footer", "header"]):
        # Оставляем footer — там бывают контакты
        if tag.name in ("nav",):
            tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    # Убираем пустые строки
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def extract_links(html: str, base_url: str) -> list[dict]:
    """Извлечь все ссылки со страницы."""
    from urllib.parse import urljoin

    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(strip=True)
        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        full_url = urljoin(base_url, href)
        links.append({"url": full_url, "text": text.lower()})
    return links