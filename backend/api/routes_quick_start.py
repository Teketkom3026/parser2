"""Эндпоинт «Быстрый старт» — один URL, введённый вручную."""
from fastapi import APIRouter, HTTPException
from backend.storage.models import QuickStartRequest, TaskResponse
from backend.utils.logger import get_logger

logger = get_logger("quick_start")

router = APIRouter(prefix="/api/v1")


def get_db():
    from backend.main import app_state
    return app_state["db"]


def get_task_manager():
    from backend.main import app_state
    return app_state["task_manager"]


@router.post("/quick-start", response_model=TaskResponse)
async def quick_start(req: QuickStartRequest):
    if not req.url or not req.url.strip():
        raise HTTPException(400, "URL обязателен")
    db = get_db()
    tm = get_task_manager()
    mode = req.mode if req.mode in ("mode_1", "mode_2") else "mode_2"
    target_positions = req.positions if mode == "mode_1" else None
    task_id = await tm.create_task(
        urls=[req.url.strip()],
        mode=mode,
        target_positions=target_positions,
    )
    await tm.start_task(task_id)
    task = await db.get_task(task_id)
    return TaskResponse(
        task_id=task_id,
        status=task["status"],
        mode=mode,
        total_urls=1,
    )
