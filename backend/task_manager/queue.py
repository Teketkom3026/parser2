"""Менеджер задач — оркестрация парсинга."""
import asyncio
import json
import random
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin

from backend.config import settings
from backend.crawler.browser import BrowserManager
from backend.crawler.http_client import fetch_page
from backend.crawler.page_finder import find_relevant_links, is_contact_page
from backend.crawler.robots_checker import is_allowed
from backend.extractor.dom_extractor import extract_person_blocks, extract_company_info
from backend.extractor.regex_extractor import extract_all_regex, classify_email
from backend.extractor.normalizer import normalize_position, classify_role, filter_by_positions
from backend.extractor.name_validator import is_valid_person_name, split_fio
from backend.extractor.position_cleaner import clean_position_raw, is_valid_position
from backend.extractor.company_name_cleaner import clean_company_name
from backend.extractor.language_detector import detect_language
from backend.blacklist.blacklist_engine import BlacklistEngine
from backend.output.excel_generator import generate_excel
from backend.output.summary import TaskSummary
from backend.storage.database import Database
from backend.utils.html_cleaner import clean_html
from backend.utils.url_normalizer import normalize_url, extract_domain
from backend.utils.logger import get_logger

logger = get_logger("task_manager")

# Стандартные пути страниц контактов для поиска ИНН/email/телефона
CONTACT_PAGE_PATHS = [
    "/kontakty/", "/contacts/", "/contact/", "/about/contacts/",
    "/o-kompanii/", "/about/", "/about-us/", "/company/contacts/",
    "/kontaktyi/", "/kontakt/", "/kontaktyi",
]


class TaskManager:
    def __init__(self, db: Database, browser: BrowserManager) -> None:
        self.db = db
        self.browser = browser
        self.blacklist = BlacklistEngine(db)
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._progress_callbacks: dict[str, list] = {}

    def register_progress_callback(self, task_id: str, callback) -> None:
        if task_id not in self._progress_callbacks:
            self._progress_callbacks[task_id] = []
        self._progress_callbacks[task_id].append(callback)

    def unregister_progress_callback(self, task_id: str, callback) -> None:
        if task_id in self._progress_callbacks:
            self._progress_callbacks[task_id] = [
                cb for cb in self._progress_callbacks[task_id] if cb != callback
            ]

    async def _notify_progress(self, task_id: str, data: dict) -> None:
        for cb in self._progress_callbacks.get(task_id, []):
            try:
                await cb(data)
            except Exception:
                pass

    # ── Создание задачи ──────────────────────────────────────────────────────
    async def create_task(
        self,
        urls: list[str],
        mode: str,
        target_positions: list[str] | None = None,
        input_file: str | None = None,
    ) -> str:
        task_id = str(uuid.uuid4())[:12]
        clean_urls = [normalize_url(u) for u in urls if u.strip()]
        await self.db.create_task(
            task_id=task_id,
            mode=mode,
            total_urls=len(clean_urls),
            target_positions=target_positions,
            input_file=input_file,
        )
        for url in clean_urls:
            await self.db.add_site(task_id, url)
        logger.info("task_created", task_id=task_id, mode=mode, urls=len(clean_urls))
        return task_id

    # ── Запуск задачи ────────────────────────────────────────────────────────
    async def start_task(self, task_id: str) -> None:
        task = await self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        await self.db.update_task(task_id, status="running")
        async_task = asyncio.create_task(self._process_task(task_id))
        self._running_tasks[task_id] = async_task

    async def _process_task(self, task_id: str) -> None:
        task = await self.db.get_task(task_id)
        mode = task["mode"]
        target_positions = json.loads(task["target_positions"]) if task["target_positions"] else []
        summary = TaskSummary(total_urls=task["total_urls"])
        all_contacts = []
        try:
            for site_row in await self.db.get_pending_sites(task_id):
                site_id = site_row["id"]
                url = site_row["url"]
                await self.db.update_site(site_id, status="processing")
                await self._notify_progress(task_id, {
                    "task_id": task_id, "status": "running",
                    "processed": summary.processed_urls,
                    "total": summary.total_urls,
                    "found_contacts": summary.total_contacts,
                    "errors": len(summary.errors),
                    "current_url": url,
                    "message": f"Обрабатываю: {url}",
                })
                start_time = time.time()
                try:
                    contacts = await self._process_site(url, mode, target_positions)
                    contacts = await self.blacklist.filter_contacts(contacts)
                    elapsed = int((time.time() - start_time) * 1000)
                    for c in contacts:
                        c["task_id"] = task_id
                        await self.db.save_contact(**c)
                    all_contacts.extend(contacts)
                    await self.db.update_site(
                        site_id,
                        status="ok" if contacts else "partial",
                        contacts_found=len(contacts),
                        processing_time_ms=elapsed,
                    )
                    summary.processed_urls += 1
                    summary.successful_urls += 1
                    summary.total_contacts += len(contacts)
                except Exception as e:
                    elapsed = int((time.time() - start_time) * 1000)
                    error_str = str(e)[:500]
                    error_code = "UNKNOWN"
                    if "captcha" in error_str.lower(): error_code = "CAPTCHA"
                    elif "timeout" in error_str.lower(): error_code = "TIMEOUT"
                    elif "403" in error_str: error_code = "403"
                    elif "404" in error_str: error_code = "404"
                    elif "429" in error_str: error_code = "429"
                    await self.db.update_site(
                        site_id, status="error",
                        error_code=error_code, error_message=error_str,
                        processing_time_ms=elapsed,
                    )
                    summary.processed_urls += 1
                    summary.failed_urls += 1
                    summary.add_error(url, error_code, error_str)
                    logger.error("site_error", url=url, error=error_str)

                await self.db.update_task(
                    task_id,
                    processed_urls=summary.processed_urls,
                    found_contacts=summary.total_contacts,
                    errors_count=len(summary.errors),
                )
                await asyncio.sleep(random.uniform(
                    settings.CRAWLER_DELAY_MIN_SEC,
                    settings.CRAWLER_DELAY_MAX_SEC,
                ))

            # Генерация Excel
            output_dir = Path(settings.RESULTS_DIR) / datetime.now().strftime("%Y-%m-%d_%H-%M")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f"result_{task_id}.xlsx")
            generate_excel(all_contacts, output_path)

            await self.db.update_task(
                task_id, status="completed",
                output_file=output_path,
                completed_at=datetime.now().isoformat(),
            )
            await self._notify_progress(task_id, {
                "task_id": task_id, "status": "completed",
                "processed": summary.processed_urls,
                "total": summary.total_urls,
                "found_contacts": summary.total_contacts,
                "errors": len(summary.errors),
                "current_url": "", "message": "Обработка завершена!",
            })
        except Exception as e:
            await self.db.update_task(task_id, status="failed")
            logger.error("task_failed", task_id=task_id, error=str(e))
        finally:
            self._running_tasks.pop(task_id, None)

    # ── Обработка одного сайта ───────────────────────────────────────────────
    async def _process_site(self, url: str, mode: str, target_positions: list[str]) -> list[dict]:
        domain = extract_domain(url)
        parsed_url = urlparse(url)
        base = f"{parsed_url.scheme}://{parsed_url.netloc}"

        # 1. Главная страница
        try:
            main_html, status_code = await self.browser.fetch_page(url)
        except Exception:
            main_html, status_code = await fetch_page(url)
        if status_code >= 400:
            raise Exception(f"HTTP {status_code} для {url}")

        # 2. Название компании
        company_info = extract_company_info(main_html)
        company_name = company_info.get("company_name", "")

        # 3. Страница /контакты — отдельно для email/телефона/ИНН/КПП компании
        company_emails: list[str] = []
        company_phones: list[str] = []
        inn_list: list[str] = []
        kpp_list: list[str] = []

        contact_html = await self._fetch_contacts_page(base)
        if contact_html:
            contact_text = clean_html(contact_html)
            cr = extract_all_regex(contact_html, contact_text)
            company_emails = [e for e in cr["emails"] if classify_email(e) == "corporate_general"]
            company_phones = cr["phones"]
            inn_list = cr["inn"]
            kpp_list = cr["kpp"]

        # Fallback: regex из главной если ничего не нашли
        if not company_emails or not company_phones:
            main_text = clean_html(main_html)
            mr = extract_all_regex(main_html, main_text)
            if not company_emails:
                company_emails = [e for e in mr["emails"] if classify_email(e) == "corporate_general"]
            if not company_phones:
                company_phones = mr["phones"]
            if not inn_list:
                inn_list = mr["inn"]
            if not kpp_list:
                kpp_list = mr["kpp"]

        # 4. Язык страницы
        main_text = clean_html(main_html)
        lang = detect_language(main_text)

        # 5. Поиск страниц с командой
        relevant_links = find_relevant_links(main_html, url)
        pages_to_parse = [url]
        max_pages = settings.CRAWLER_MAX_PAGES_PER_SITE
        for link in relevant_links[:max_pages - 1]:
            if link not in pages_to_parse:
                pages_to_parse.append(link)

        # 6. Парсинг сотрудников
        all_persons = []
        for page_url in pages_to_parse:
            try:
                if page_url == url:
                    html = main_html
                else:
                    await asyncio.sleep(random.uniform(
                        settings.CRAWLER_DELAY_MIN_SEC,
                        settings.CRAWLER_DELAY_MAX_SEC,
                    ))
                    try:
                        html, st = await self.browser.fetch_page(page_url)
                    except Exception:
                        html, st = await fetch_page(page_url)
                    if st >= 400:
                        continue

                person_blocks = extract_person_blocks(html)

                # Дополняем ИНН/КПП из страницы команды
                page_text = clean_html(html)
                page_regex = extract_all_regex(html, page_text)
                for inn in page_regex["inn"]:
                    if inn not in inn_list:
                        inn_list.append(inn)
                for kpp in page_regex["kpp"]:
                    if kpp not in kpp_list:
                        kpp_list.append(kpp)

                for pb in person_blocks:
                    # Валидация имени — пропускаем нерелевантные
                    if pb.name and not is_valid_person_name(pb.name):
                        pb.name = ""

                    # Очистка должности
                    raw_pos = clean_position_raw(pb.position)
                    norm_pos = normalize_position(raw_pos)
                    role_cat = classify_role(raw_pos or norm_pos)

                    # Разбивка ФИО
                    fio_parts = split_fio(pb.name) if pb.name else {}

                    person_dict = {
                        "site_url":       url,
                        "page_url":       page_url,
                        "company_name":   company_name,
                        "company_email":  company_emails[0] if company_emails else "",
                        "company_phone":  company_phones[0] if company_phones else "",
                        "person_name":    pb.name or "",
                        "last_name":      fio_parts.get("last_name", ""),
                        "first_name":     fio_parts.get("first_name", ""),
                        "patronymic":     fio_parts.get("patronymic", ""),
                        "initials":       fio_parts.get("initials", ""),
                        "position_raw":   raw_pos,
                        "position_norm":  norm_pos,
                        "role_category":  role_cat,
                        "person_email":   pb.email or "",
                        "person_phone":   pb.phone or "",
                        "inn":            inn_list[0] if inn_list else "",
                        "kpp":            kpp_list[0] if kpp_list else "",
                        "social_links":   json.dumps(page_regex.get("social_links", []), ensure_ascii=False),
                        "page_language":  lang,
                        "extraction_method": "regex",
                        "status":         "OK" if (pb.name and raw_pos) else "Частично",
                        "comment":        "" if (pb.name and raw_pos) else "Неполные данные",
                        "scan_date":      datetime.now().strftime("%Y-%m-%d"),
                    }
                    all_persons.append(person_dict)
            except Exception as e:
                logger.warning("page_error", page_url=page_url, error=str(e))
                continue

        # 7. Фильтрация по должностям (Режим 1)
        if mode == "mode_1" and target_positions:
            all_persons = filter_by_positions(all_persons, target_positions)

        # 8. Если ничего не нашли — заглушка
        if not all_persons:
            all_persons.append({
                "site_url": url, "page_url": url,
                "company_name": company_name,
                "company_email": company_emails[0] if company_emails else "",
                "company_phone": company_phones[0] if company_phones else "",
                "person_name": "", "last_name": "", "first_name": "",
                "patronymic": "", "initials": "",
                "position_raw": "", "position_norm": "", "role_category": "",
                "person_email": "", "person_phone": "",
                "inn": inn_list[0] if inn_list else "",
                "kpp": kpp_list[0] if kpp_list else "",
                "social_links": "", "page_language": lang,
                "extraction_method": "regex",
                "status": "Частично", "comment": "Контакты сотрудников не найдены",
                "scan_date": datetime.now().strftime("%Y-%m-%d"),
            })

        return all_persons

    async def _fetch_contacts_page(self, base_url: str) -> str | None:
        """Загрузить страницу /контакты для получения email/телефона/ИНН."""
        for path in CONTACT_PAGE_PATHS:
            contact_url = base_url.rstrip("/") + path
            try:
                try:
                    html, st = await self.browser.fetch_page(contact_url)
                except Exception:
                    html, st = await fetch_page(contact_url)
                if st == 200 and html:
                    return html
            except Exception:
                continue
        return None

    # ── Управление задачами ──────────────────────────────────────────────────
    async def pause_task(self, task_id: str) -> None:
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
        await self.db.update_task(task_id, status="paused")

    async def cancel_task(self, task_id: str) -> None:
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            del self._running_tasks[task_id]
        await self.db.update_task(task_id, status="cancelled")

    async def resume_task(self, task_id: str) -> None:
        task = await self.db.get_task(task_id)
        if task and task["status"] == "paused":
            await self.db.update_task(task_id, status="running")
            self._running_tasks[task_id] = asyncio.create_task(self._process_task(task_id))
