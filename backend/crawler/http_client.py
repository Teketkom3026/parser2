"""Лёгкий HTTP-клиент на httpx (fallback без JS-рендеринга)."""
import httpx
from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger("http_client")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


async def fetch_page(url: str) -> tuple[str, int]:
    async with httpx.AsyncClient(
        timeout=settings.CRAWLER_PAGE_TIMEOUT_SEC,
        follow_redirects=True,
        verify=False,
        headers=HEADERS,
    ) as client:
        response = await client.get(url)
        return response.text, response.status_code
