"""Формирование итогов обработки."""
from dataclasses import dataclass, field


@dataclass
class TaskSummary:
    total_urls: int = 0
    processed_urls: int = 0
    successful_urls: int = 0
    failed_urls: int = 0
    skipped_urls: int = 0
    total_contacts: int = 0
    errors: list[dict] = field(default_factory=list)

    def add_error(self, url: str, code: str, message: str) -> None:
        self.errors.append({"url": url, "code": code, "message": message})

    def to_dict(self) -> dict:
        return {
            "total_urls": self.total_urls,
            "processed_urls": self.processed_urls,
            "successful_urls": self.successful_urls,
            "failed_urls": self.failed_urls,
            "skipped_urls": self.skipped_urls,
            "total_contacts": self.total_contacts,
            "errors_count": len(self.errors),
            "errors": self.errors[:100],  # Ограничиваем для API
        }


def build_summary(contacts: list[dict], task: dict) -> str:
    """Формирование текстовой сводки по результатам."""
    total = len(contacts)
    with_name = sum(1 for c in contacts if c.get("person_name"))
    with_email = sum(1 for c in contacts if c.get("person_email"))
    unique_sites = len(set(c.get("site_url", "") for c in contacts if c.get("site_url")))
    lines = [
        "═══ СВОДКА ═══",
        f"Режим: {task.get('mode', '?')}",
        f"Всего сайтов: {task.get('total_urls', 0)}",
        f"Обработано: {task.get('processed_urls', 0)}",
        f"Ошибок: {task.get('errors_count', 0)}",
        "",
        f"Найдено записей: {total}",
        f"— с ФИО: {with_name}",
        f"— с email: {with_email}",
        f"Уникальных компаний: {unique_sites}",
    ]
    return "\n".join(lines)
