"""Проверка email/доменов по blacklist."""

from backend.storage.database import Database
from backend.utils.url_normalizer import extract_domain
from backend.utils.logger import get_logger

logger = get_logger("blacklist")


class BlacklistChecker:
    """Проверяет email и домены по blacklist из БД."""

    def __init__(self, db: Database):
        self._db = db
        self._cache_domains: set[str] = set()
        self._cache_emails: set[str] = set()
        self._loaded = False

    async def load(self):
        """Загружает blacklist из БД в кэш."""
        entries = await self._db.get_blacklist()

        self._cache_domains.clear()
        self._cache_emails.clear()

        for entry in entries:
            entry_type = entry.get("entry_type", "")
            value = entry.get("value", "").strip().lower()

            if not value:
                continue

            if entry_type == "domain":
                # Нормализуем домен
                if value.startswith(("http://", "https://")):
                    value = extract_domain(value)
                if value.startswith("www."):
                    value = value[4:]
                self._cache_domains.add(value)

            elif entry_type == "email":
                self._cache_emails.add(value)

        self._loaded = True
        logger.info("blacklist_loaded",
                     domains=len(self._cache_domains),
                     emails=len(self._cache_emails))

    def invalidate_cache(self):
        """Сбрасывает кэш — будет перезагружен при следующей проверке."""
        self._loaded = False

    async def _ensure_loaded(self):
        """Загружает кэш, если ещё не загружен."""
        if not self._loaded:
            await self.load()

    async def is_email_blacklisted(self, email: str) -> bool:
        """Проверяет, есть ли email в blacklist."""
        await self._ensure_loaded()

        if not email:
            return False

        email_lower = email.lower().strip()

        # Прямое совпадение email
        if email_lower in self._cache_emails:
            return True

        # Проверка домена email
        if "@" in email_lower:
            domain = email_lower.split("@")[1]
            if domain in self._cache_domains:
                return True

        return False

    async def is_domain_blacklisted(self, url: str) -> bool:
        """Проверяет, есть ли домен URL в blacklist."""
        await self._ensure_loaded()

        if not url:
            return False

        domain = extract_domain(url).lower()

        if domain in self._cache_domains:
            return True

        # Проверка с www
        if domain.startswith("www."):
            if domain[4:] in self._cache_domains:
                return True
        else:
            if f"www.{domain}" in self._cache_domains:
                return True

        return False

    async def filter_contacts(self, contacts: list[dict]) -> list[dict]:
        """Фильтрует контакты — убирает заблокированные."""
        await self._ensure_loaded()

        if not self._cache_domains and not self._cache_emails:
            return contacts

        filtered = []
        removed = 0

        for contact in contacts:
            blocked = False

            # Проверяем email персоны
            person_email = contact.get("person_email", "")
            if person_email and await self.is_email_blacklisted(person_email):
                blocked = True

            # Проверяем email компании
            if not blocked:
                company_email = contact.get("company_email", "")
                if company_email and await self.is_email_blacklisted(company_email):
                    blocked = True

            # Проверяем домен сайта
            if not blocked:
                site_url = contact.get("site_url", "")
                if site_url and await self.is_domain_blacklisted(site_url):
                    blocked = True

            if blocked:
                removed += 1
            else:
                filtered.append(contact)

        if removed:
            logger.info("blacklist_filtered", removed=removed, kept=len(filtered))

        return filtered
