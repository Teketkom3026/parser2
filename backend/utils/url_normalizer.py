"""Нормализация URL."""

from urllib.parse import urlparse, urlunparse
import re


def normalize_url(url: str) -> str:
    """Нормализовать один URL."""
    url = url.strip()
    if not url:
        return ""

    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Убираем www.
    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parsed.path.rstrip("/") or ""

    normalized = urlunparse((scheme, netloc, path, "", "", ""))
    return normalized


def normalize_urls(urls: list[str]) -> list[str]:
    """Нормализовать список URL, убрать дубли и невалидные."""
    seen = set()
    result = []
    for url in urls:
        n = normalize_url(url)
        if n and n not in seen:
            seen.add(n)
            result.append(n)
    return result


def extract_domain(url: str) -> str:
    """Извлечь домен из URL."""
    parsed = urlparse(normalize_url(url))
    return parsed.netloc