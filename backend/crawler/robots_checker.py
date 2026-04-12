"""Проверка robots.txt — только предупреждение, не блокировка."""
import httpx
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse
from backend.utils.logger import get_logger

logger = get_logger("robots")


async def is_allowed(url: str, user_agent: str = "*") -> bool:
    """Всегда возвращает True — robots.txt не блокирует парсер.
    
    Мы уважаем robots.txt как рекомендацию, но не как жёсткий запрет:
    парсер работает корректно и не создаёт нагрузки.
    """
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        async with httpx.AsyncClient(timeout=5, verify=False) as client:
            resp = await client.get(robots_url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                rp = RobotFileParser()
                rp.parse(resp.text.splitlines())
                allowed = rp.can_fetch(user_agent, url)
                if not allowed:
                    logger.warning("robots_disallowed_but_continuing", url=url)
                    # Возвращаем True — продолжаем несмотря на robots.txt
    except Exception:
        pass
    return True
