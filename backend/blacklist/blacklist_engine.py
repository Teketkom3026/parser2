"""Модуль blacklist — фильтрация контактов."""
from urllib.parse import urlparse

from backend.storage.database import Database
from backend.utils.logger import get_logger

logger = get_logger("blacklist")


class BlacklistEngine:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def check_contact(self, email: str = "", domain: str = "") -> bool:
        """Проверить, заблокирован ли контакт. True = заблокирован."""
        if email:
            if await self.db.is_blacklisted(email):
                logger.info("blacklisted_email", email=email)
                return True
            # Проверяем домен email
            email_domain = email.split("@")[-1].lower()
            if await self.db.is_domain_blacklisted(email_domain):
                logger.info("blacklisted_email_domain", domain=email_domain)
                return True
        if domain:
            d = domain.lower().strip()
            if d.startswith("www."):
                d = d[4:]
            if await self.db.is_domain_blacklisted(d):
                logger.info("blacklisted_domain", domain=d)
                return True
        return False

    async def filter_contacts(self, contacts: list[dict]) -> list[dict]:
        """Отфильтровать контакты по blacklist. Возвращает только разрешённые."""
        allowed = []
        for c in contacts:
            email = c.get("person_email", "") or c.get("company_email", "") or ""
            domain = ""
            site_url = c.get("site_url", "")
            if site_url:
                parsed = urlparse(site_url)
                domain = parsed.netloc
            if not await self.check_contact(email=email, domain=domain):
                allowed.append(c)
            else:
                logger.info("contact_filtered", person=c.get("person_name", ""), email=email)
        return allowed

    async def load_from_file(self, file_path: str) -> int:
        """Загрузить blacklist из Excel/CSV файла."""
        import openpyxl
        count = 0
        try:
            wb = openpyxl.load_workbook(file_path, read_only=True)
            ws = wb.active
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row or not row[0]:
                    continue
                value = str(row[0]).strip().lower()
                if "@" in value:
                    entry_type = "email"
                else:
                    entry_type = "domain"
                    if value.startswith("www."):
                        value = value[4:]
                if await self.db.add_blacklist_entry(entry_type, value):
                    count += 1
            wb.close()
        except Exception as e:
            logger.error("blacklist_load_error", error=str(e))
            raise
        logger.info("blacklist_loaded", entries_added=count)
        return count
