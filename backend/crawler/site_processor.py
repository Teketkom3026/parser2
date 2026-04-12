"""Обработка одного сайта: обход страниц, извлечение контактов."""

import json
from pathlib import Path
from urllib.parse import urljoin

from backend.crawler.browser import BrowserManager
from backend.blacklist.blacklist_engine import BlacklistEngine
from backend.extractor.dom_extractor import extract_person_blocks, extract_company_info
from backend.extractor.regex_extractor import (
    extract_emails, extract_phones, extract_inn,
    extract_kpp, extract_social_links, classify_email,
)
from backend.extractor.normalizer import normalize_position, classify_role
from backend.extractor.language_detector import detect_language
from backend.utils.url_normalizer import normalize_url, extract_domain, is_same_domain
from backend.utils.logger import get_logger

logger = get_logger("site_processor")

# Загружаем паттерны контактных страниц
_contact_pages_config: dict = {}
_cp_loaded = False


def _load_contact_pages_config():
    global _contact_pages_config, _cp_loaded
    if _cp_loaded:
        return
    cp_path = Path(__file__).parent.parent / "dictionaries" / "contact_pages.json"
    if cp_path.exists():
        _contact_pages_config = json.loads(cp_path.read_text(encoding="utf-8"))
    _cp_loaded = True


class SiteProcessor:
    def __init__(self, browser: BrowserManager, blacklist: BlacklistEngine):
        self.browser = browser
        self.blacklist = blacklist
        _load_contact_pages_config()

    async def process_site(self, url: str) -> list[dict]:
        """Обрабатывает один сайт: главная + контактные страницы."""
        url = normalize_url(url)
        domain = extract_domain(url)

        logger.info("processing_site", url=url, domain=domain)

        # Страницы для обхода
        pages_to_visit = self._get_pages_to_visit(url)
        visited: set[str] = set()
        all_contacts: list[dict] = []

        company_info = {"company_name": "", "company_email": "", "company_phone": ""}

        for page_url in pages_to_visit:
            if page_url in visited:
                continue
            visited.add(page_url)

            try:
                html = await self.browser.fetch_page(page_url)
                if not html or len(html) < 100:
                    continue

                # Извлекаем информацию о компании (с главной)
                if page_url == url:
                    company_info = extract_company_info(html)

                # Определяем язык
                page_lang = detect_language(html[:3000])

                # Ищем дополнительные контактные ссылки на странице
                extra_links = self._find_contact_links_in_html(html, url)
                for link in extra_links:
                    if link not in visited and link not in pages_to_visit:
                        pages_to_visit.append(link)

                # Извлекаем персоны
                persons = extract_person_blocks(html)

                # Извлекаем общие контакты
                page_emails = extract_emails(html)
                page_phones = extract_phones(html)
                page_inn = extract_inn(html)
                page_kpp = extract_kpp(html)
                page_socials = extract_social_links(html)

                # Обновляем общую инфу компании
                if not company_info.get("company_email") and page_emails:
                    for email in page_emails:
                        if classify_email(email) in ("corporate_general",):
                            company_info["company_email"] = email
                            break

                if not company_info.get("company_phone") and page_phones:
                    company_info["company_phone"] = page_phones[0]

                # Формируем контакты из персон
                for person in persons:
                    contact = {
                        "company_name": company_info.get("company_name", ""),
                        "site_url": url,
                        "company_email": company_info.get("company_email", ""),
                        "company_phone": company_info.get("company_phone", ""),
                        "person_name": person.name or "",
                        "position_raw": person.position or "",
                        "position_norm": normalize_position(person.position or ""),
                        "role_category": classify_role(
                            normalize_position(person.position or "")
                        ),
                        "person_email": person.email or "",
                        "person_phone": person.phone or "",
                        "inn": page_inn[0] if page_inn else "",
                        "kpp": page_kpp[0] if page_kpp else "",
                        "social_links": "; ".join(page_socials) if page_socials else "",
                        "page_url": page_url,
                        "page_language": page_lang,
                        "status": "found",
                        "comment": "",
                    }
                    all_contacts.append(contact)

                # Если нет персон, но есть email — создаём контакт без имени
                if not persons and page_emails:
                    for email in page_emails:
                        email_class = classify_email(email)
                        contact = {
                            "company_name": company_info.get("company_name", ""),
                            "site_url": url,
                            "company_email": email if email_class == "corporate_general" else "",
                            "company_phone": company_info.get("company_phone", ""),
                            "person_name": "",
                            "position_raw": "",
                            "position_norm": "",
                            "role_category": "",
                            "person_email": email if email_class == "corporate_personal" else "",
                            "person_phone": "",
                            "inn": page_inn[0] if page_inn else "",
                            "kpp": page_kpp[0] if page_kpp else "",
                            "social_links": "; ".join(page_socials) if page_socials else "",
                            "page_url": page_url,
                            "page_language": page_lang,
                            "status": "found",
                            "comment": f"email_type: {email_class}",
                        }
                        all_contacts.append(contact)

                logger.debug("page_processed",
                             page_url=page_url,
                             persons=len(persons),
                             emails=len(page_emails),
                             phones=len(page_phones))

            except Exception as e:
                logger.warning("page_error", page_url=page_url, error=str(e)[:200])
                continue

        # Дедупликация
        all_contacts = self._deduplicate(all_contacts)

        # Blacklist фильтрация
        all_contacts = await self.blacklist.filter_contacts(all_contacts)

        logger.info("site_processed",
                     url=url,
                     total_contacts=len(all_contacts),
                     pages_visited=len(visited))

        return all_contacts

    def _get_pages_to_visit(self, base_url: str) -> list[str]:
        """Формирует список страниц для обхода."""
        pages = [base_url]
        paths = _contact_pages_config.get("paths", [])

        for path in paths:
            full_url = urljoin(base_url + "/", path.lstrip("/"))
            full_url = normalize_url(full_url)
            if full_url not in pages:
                pages.append(full_url)

        return pages

    def _find_contact_links_in_html(self, html: str, base_url: str) -> list[str]:
        """Ищет ссылки на контактные страницы в HTML."""
        from bs4 import BeautifulSoup

        links: list[str] = []
        keywords = _contact_pages_config.get("keywords_in_text", [])
        url_keywords = _contact_pages_config.get("keywords_in_url", [])

        try:
            soup = BeautifulSoup(html, "lxml")

            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"].strip()
                text = a_tag.get_text(strip=True).lower()

                # Пропускаем внешние ссылки
                if href.startswith(("http://", "https://")) and not is_same_domain(href, base_url):
                    continue

                # Пропускаем не-HTML
                if any(href.endswith(ext) for ext in (".pdf", ".doc", ".jpg", ".png", ".zip")):
                    continue

                href_lower = href.lower()
                matched = False

                # Проверка по URL keywords
                for kw in url_keywords:
                    if kw in href_lower:
                        matched = True
                        break

                # Проверка по тексту ссылки
                if not matched:
                    for kw in keywords:
                        if kw in text:
                            matched = True
                            break

                if matched:
                    full_url = urljoin(base_url + "/", href)
                    full_url = normalize_url(full_url)
                    if full_url not in links and is_same_domain(full_url, base_url):
                        links.append(full_url)

        except Exception as e:
            logger.debug("link_extraction_error", error=str(e)[:200])

        return links[:10]  # Ограничиваем количество дополнительных страниц

    def _deduplicate(self, contacts: list[dict]) -> list[dict]:
        """Дедупликация контактов."""
        seen: set[str] = set()
        result: list[dict] = []

        for contact in contacts:
            # Ключ дедупликации
            key_parts = [
                contact.get("person_name", "").lower().strip(),
                contact.get("person_email", "").lower().strip(),
                contact.get("company_email", "").lower().strip(),
                contact.get("site_url", "").lower().strip(),
            ]
            key = "|".join(key_parts)

            if key in seen:
                continue

            # Пропускаем полностью пустые контакты
            has_data = any([
                contact.get("person_name"),
                contact.get("person_email"),
                contact.get("company_email"),
                contact.get("person_phone"),
                contact.get("company_phone"),
            ])
            if not has_data:
                continue

            seen.add(key)
            result.append(contact)

        return result
