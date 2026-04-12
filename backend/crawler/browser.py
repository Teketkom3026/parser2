"""Playwright headless browser — для SPA/JS- рендеринга."""

import asyncio
from contextlib import asynccontextmanager

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from backend.config import settings
from backend.crawler.user_agents import get_random_user_agent
from backend.utils.logger import get_logger

logger = get_logger("browser")


class BrowserManager:
    def __init__(self) -> None:
        self._playwright = None
        self._browser: Browser | None = None
        self._semaphore = asyncio.Semaphore(settings.CRAWLER_MAX_CONCURRENT)
        self.is_running = False

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        self.is_running = True
        logger.info("browser_started")

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self.is_running = False
        logger.info("browser_stopped")

    async def fetch_page(self, url: str) -> tuple[str, int]:
        """Загрузить страницу через Playwright. Возвращает (html, status_code)."""
        async with self._semaphore:
            context: BrowserContext | None = None
            try:
                context = await self._browser.new_context(
                    user_agent=get_random_user_agent(),
                    ignore_https_errors=True,
                )
                page: Page = await context.new_page()

                response = await page.goto(
                    url,
                    timeout=settings.CRAWLER_PAGE_TIMEOUT_SEC * 1000,
                    wait_until="domcontentloaded",
                )

                # Ждём дополнительно для JS- рендеринга
                await page.wait_for_timeout(2000)

                html = await page.content()
                status = response.status if response else 0

                return html, status

            except Exception as e:
                logger.error("browser_fetch_error", url=url, error=str(e))
                raise
            finally:
                if context:
                    await context.close()