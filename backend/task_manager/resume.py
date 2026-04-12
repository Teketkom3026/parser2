"""Поиск и возобновление прерванных задач после перезапуска."""

from backend.storage.database import Database
from backend.utils.logger import get_logger

logger = get_logger("resume")


async def find_resumable_tasks(db: Database) -> list[str]:
    """Находит задачи, которые были прерваны (running/paused)."""
    tasks = await db.list_tasks()
    resumable = []

    for task in tasks:
        status = task.get("status", "")
        task_id = task.get("id", "")

        if status in ("running", "paused"):
            processed = task.get("processed_urls", 0) or 0
            total = task.get("total_urls", 0) or 0

            if processed < total:
                resumable.append(task_id)
                logger.info("found_resumable_task",
                            task_id=task_id,
                            status=status,
                            processed=processed,
                            total=total)

    logger.info("resumable_tasks_scan", found=len(resumable))
    return resumable
