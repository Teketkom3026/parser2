"""Точка входа FastAPI-приложения."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.storage.database import Database
from backend.crawler.browser import BrowserManager
from backend.task_manager.queue import TaskManager
from backend.task_manager.resume import find_resumable_tasks
from backend.utils.logger import setup_logging, get_logger
from backend.api.routes import router as main_router
from backend.api.routes_quick_start import router as quick_start_router
from backend.api.websocket import router as ws_router

setup_logging()
logger = get_logger("main")

# Глобальное состояние
app_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация и завершение приложения."""
    logger.info("app_starting", variant=settings.VARIANT)

    Path(settings.RESULTS_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.LOG_DIR).mkdir(parents=True, exist_ok=True)
    Path("./data/inputs").mkdir(parents=True, exist_ok=True)

    db = Database()
    await db.initialize()
    app_state["db"] = db

    browser = BrowserManager()
    await browser.start()
    app_state["browser"] = browser

    tm = TaskManager(db=db, browser=browser)
    app_state["task_manager"] = tm

    resumable = await find_resumable_tasks(db)
    for tid in resumable:
        logger.info("resuming_task", task_id=tid)
        try:
            await tm.resume_task(tid)
        except Exception as e:
            logger.error("resume_failed", task_id=tid, error=str(e))

    logger.info("app_started")
    yield

    logger.info("app_stopping")
    await browser.stop()
    await db.close()
    logger.info("app_stopped")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="MVP-система автоматизированного сбора контактной информации с веб-сайтов",
    lifespan=lifespan,
    root_path="/parser2",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(main_router)
app.include_router(quick_start_router)
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok", "variant": settings.VARIANT}
