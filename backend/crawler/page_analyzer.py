"""Анализатор страницы: оркестрирует загрузку и извлечение контактов."""

from backend.crawler.browser import BrowserManager
from backend.extractor.dom_extractor import extract_person_blocks, extract_company_info
from backend.extractor.regex_extractor import (
    extract_emails, extract_phones, extract_inn, extract_kpp,
    extract_social_links, classify_email,
)
from backend.extractor.language_detector import detect_language
from backend.utils.logger import get_logger

logger = get_logger("page_analyzer")


class PageAnalyzer:
    def __init__(self, browser: BrowserManager):
        self._browser = browser

    async def analyze_site(self, url: str) -> list[dict]:
        """Анализирует сайт: главная + подстраницы."""
        all_contacts: list[dict] = []
        visited: set[str] = set()

        # 1. Загружаем главную
        try:
            result = await self._browser.get_page_html(url)
        except Exception as e:
            logger.error("main_page_error", url=url, error=str(e)[:200])
            raise

        html = result["html"]
        visited.add(result["final_url"].rstrip("/"))

        # 2. Извлекаем контакты с главной
        contacts = self._extract_contacts(html, url, result["final_url"])
        all_contacts.extend(contacts)

        # 3. Находим подстраницы
        subpages = await self._browser.get_subpages(url, html)

        # 4. Обходим подстраницы
        for sub_url in subpages:
            normalized = sub_url.rstrip("/")
            if normalized in visited:
                continue
            visited.add(normalized)

            try:
                sub_result = await self._browser.get_page_html(sub_url)
                sub_html = sub_result["html"]

                sub_contacts = self._extract_contacts(sub_html, url, sub_url)
                all_contacts.extend(sub_contacts)

            except Exception as e:
                logger.warning("subpage_error", url=sub_url, error=str(e)[:200])
                continue

        # 5. Дедупликация
        all_contacts = self._deduplicate(all_contacts)

        logger.info("site_analyzed", url=url, contacts=len(all_contacts),
                     pages_visited=len(visited))

        return all_contacts

    def _extract_contacts(self, html: str, site_url: str, page_url: str) -> list[dict]:
        """Извлекает контакты из одной страницы."""
        contacts: list[dict] = []

        # Информация о компании
        company = extract_company_info(html)

        # Язык страницы
        language = detect_language(html[:5000])

        # Общие данные
        all_emails = extract_emails(html)
        all_phones = extract_phones(html)
        inns = extract_inn(html)
        kpps = extract_kpp(html)
        social = extract_social_links(html)

        # Персоны из DOM
        person_blocks = extract_person_blocks(html)

        if person_blocks:
            # Есть персоны — создаём контакт для каждой
            for person in person_blocks:
                # Классифицируем email персоны
                person_email = person.email
                company_email = ""

                if person_email:
                    email_class = classify_email(person_email)
                    if email_class == "corporate_general":
                        company_email = person_email
                        person_email = ""

                # Ищем company_email из общих
                if not company_email:
                    for em in all_emails:
                        if classify_email(em) == "corporate_general":
                            company_email = em
                            break

                contact = {
                    "company_name": company.get("company_name", ""),
                    "site_url": site_url,
                    "company_email": company_email or company.get("company_email", ""),
                    "company_phone": company.get("company_phone", ""),
                    "person_name": person.name,
                    "position_raw": person.position,
                    "position_norm": "",
                    "role_category": "",
                    "person_email": person_email,
                    "person_phone": person.phone,
                    "inn": inns[0] if inns else "",
                    "kpp": kpps[0] if kpps else "",
                    "social_links": "; ".join(social) if social else "",
                    "page_url": page_url,
                    "page_language": language,
                    "status": "found",
                }
                contacts.append(contact)
        else:
            # Нет персон — собираем общие контакты
            if all_emails or all_phones:
                # Разделяем personal vs company emails
                personal_emails = []
                company_emails = []

                for em in all_emails:
                    cls = classify_email(em)
                    if cls == "corporate_personal":
                        personal_emails.append(em)
                    elif cls in ("corporate_general", "free"):
                        company_emails.append(em)
                    else:
                        company_emails.append(em)

                if personal_emails:
                    # Каждый personal email → отдельный контакт
                    for em in personal_emails:
                        contact = {
                            "company_name": company.get("company_name", ""),
                            "site_url": site_url,
                            "company_email": company_emails[0] if company_emails else company.get("company_email", ""),
                            "company_phone": company.get("company_phone", "") or (all_phones[0] if all_phones else ""),
                            "person_name": "",
                            "position_raw": "",
                            "position_norm": "",
                            "role_category": "",
                            "person_email": em,
                            "person_phone": "",
                            "inn": inns[0] if inns else "",
                            "kpp": kpps[0] if kpps else "",
                            "social_links": "; ".join(social) if social else "",
                            "page_url": page_url,
                            "page_language": language,
                            "status": "found",
                        }
                        contacts.append(contact)
                else:
                    # Только общие данные — один контакт
                    contact = {
                        "company_name": company.get("company_name", ""),
                        "site_url": site_url,
                        "company_email": company_emails[0] if company_emails else company.get("company_email", ""),
                        "company_phone": company.get("company_phone", "") or (all_phones[0] if all_phones else ""),
                        "person_name": "",
                        "position_raw": "",
                        "position_norm": "",
                        "role_category": "",
                        "person_email": "",
                        "person_phone": "",
                        "inn": inns[0] if inns else "",
                        "kpp": kpps[0] if kpps else "",
                        "social_links": "; ".join(social) if social else "",
                        "page_url": page_url,
                        "page_language": language,
                        "status": "found",
                    }
                    contacts.append(contact)

        return contacts

    def _deduplicate(self, contacts: list[dict]) -> list[dict]:
        """Дедупликация контактов по ключу (email+name+site)."""
        seen: set[str] = set()
        unique: list[dict] = []

        for c in contacts:
            key_parts = [
                c.get("site_url", "").lower(),
                c.get("person_email", "").lower(),
                c.get("person_name", "").lower(),
                c.get("company_email", "").lower(),
            ]
            key = "|".join(key_parts)

            if key in seen:
                continue
            seen.add(key)
            unique.append(c)

        if len(contacts) != len(unique):
            logger.info("contacts_deduplicated",
                        before=len(contacts), after=len(unique))

        return unique
