"""Конфигурация приложения."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "kodis-parser-mvp"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    VARIANT: str = "A"

    CRAWLER_MAX_CONCURRENT: int = 5
    CRAWLER_PAGE_TIMEOUT_SEC: int = 30
    CRAWLER_DELAY_MIN_SEC: float = 1.0
    CRAWLER_DELAY_MAX_SEC: float = 5.0
    CRAWLER_MAX_PAGES_PER_SITE: int = 10
    CRAWLER_RESPECT_ROBOTS_TXT: bool = True

    PROXY_URL: str = ""

    SQLITE_DB_PATH: str = "./data/parser.db"
    RESULTS_DIR: str = "./results"

    BLACKLIST_FILE_PATH: str = "./data/blacklist.xlsx"

    LOG_DIR: str = "./data/logs/app"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()