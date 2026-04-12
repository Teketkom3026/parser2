"""Проверка robots.txt."""

from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger("robots")

_cache: dict[str, RobotFileParser] = {}


async def is_allowed(url: str, user_agent: str = "*") -> bool:
    """Проверить, разрешён ли URL к обходу по robots.txt."""
    if not settings.CRAWLER_RESPECT_ROBOTS_TXT:
        return True

    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    if robots_url in _cache:
        rp = _cache[robots_url]
    else:
        rp = RobotFileParser()
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(robots_url)
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    # Нет robots.txt — всё разрешено
                    rp.allow_all = True
        except Exception as e:
            logger.warning("robots_fetch_error", url=robots_url, error=str(e))
            rp.allow_all = True

        _cache[robots_url] = rp

    try:
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True