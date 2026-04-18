"""
Модуль извлечения контактных данных из HTML-страниц.
Полностью переписан для 3-фазного пайплайна с Perplexity AI (Вариант B).

Фаза 1: Классическое regex-извлечение (предобработка)
  - Извлечение email, телефонов, ИНН, КПП, соцсетей через regex
  - Извлечение названия компании из DOM
  - Поиск блоков персон в DOM
  - НЕ пытаемся извлечь должности и классифицировать email

Фаза 2: LLM-извлечение и нормализация (Perplexity AI)
  - Отправляем очищенный текст + предварительно извлечённые данные в LLM
  - LLM извлекает: ФИО, должности, классификацию email, типы ролей
  - Строгий промпт для отсечения политиков и нерелевантных людей

Фаза 3: Пост-процессинг / нормализация
  - Валидация ФИО, должностей, email
  - Фильтрация мусора из должностей
  - Классификация email на личные/общие
  - Дедупликация
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from app.config import settings
from app.models import (
    ContactRecord,
    ExtractionVariant,
    FallbackReason,
    ParseMode,
    SocialLinks,
)

logger = logging.getLogger(__name__)

# ── Пути к словарям ─────────────────────────────────────────────────────────
_DICT_DIR = Path(__file__).parent.parent / "dictionaries"


def _load_json(filename: str) -> Any:
    path = _DICT_DIR / filename
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


# ── Регулярные выражения ────────────────────────────────────────────────────

# Email: стандартный паттерн RFC 5322 упрощённый
RE_EMAIL = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.I,
)

# Телефоны: российские и международные форматы
RE_PHONE = re.compile(
    r"""
    (?:
        (?:\+7|8|7)          # Российский префикс
        [\s\-\(\.]*
        (?:\d{3}|\(\d{3}\))  # Код города/оператора
        [\s\-\)\.]*
        \d{3}
        [\s\-\.]*
        \d{2}
        [\s\-\.]*
        \d{2}
    )
    |
    (?:
        \+\d{1,3}            # Международный
        [\s\-\(\.]*
        \d{2,4}
        [\s\-\)\.]*
        \d{3,4}
        [\s\-\.]*
        \d{3,4}
    )
    """,
    re.VERBOSE,
)

# ИНН: 10 или 12 цифр (с контекстом для снижения ложных срабатываний)
RE_INN = re.compile(
    r"""
    (?:
        (?:ИНН|инн|inn|INN)  # Явный контекст
        [\s:№\-]*
        (\d{10}|\d{12})      # Значение
    )
    |
    (?<!\d)(\d{10}|\d{12})(?!\d)  # Изолированное число
    """,
    re.VERBOSE | re.I,
)

# КПП: 9 цифр (с контекстом)
RE_KPP = re.compile(
    r"""
    (?:
        (?:КПП|кпп|kpp|KPP)
        [\s:№\-]*
        (\d{9})
    )
    |
    (?<!\d)(\d{9})(?!\d)
    """,
    re.VERBOSE | re.I,
)

# ФИО: три компонента с большой буквы (русские)
RE_FIO_RU = re.compile(
    r"""
    \b
    ([\u0410-\u042f\u0401][\u0430-\u044f\u0451]+(?:-[\u0410-\u042f\u0401][\u0430-\u044f\u0451]+)?)   # Фамилия
    \s+
    ([\u0410-\u042f\u0401][\u0430-\u044f\u0451]+)                         # Имя
    \s+
    ([\u0410-\u042f\u0401][\u0430-\u044f\u0451]*(?:вич|вна|ич|на|евна|евич|ович|овна|ич|ина|\u044cич|\u044cевна)\b)  # Отчество
    """,
    re.VERBOSE,
)

# Инициалы + фамилия: И.О. Фамилия
RE_FIO_INITIALS = re.compile(
    r"""
    \b
    ([\u0410-\u042f\u0401]\.)         # Инициал имени
    ([\u0410-\u042f\u0401]\.)         # Инициал отчества
    \s*
    ([\u0410-\u042f\u0401][\u0430-\u044f\u0451]+)   # Фамилия
    \b
    """,
    re.VERBOSE,
)

# Социальные сети
RE_SOCIAL = {
    "vk": re.compile(r"(?:https?://)?(?:www\.)?vk\.com/[^\s\"'<>]+", re.I),
    "telegram": re.compile(r"(?:https?://)?(?:t\.me|telegram\.me)/[^\s\"'<>]+", re.I),
    "linkedin": re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/(?:in|company)/[^\s\"'<>]+", re.I),
    "facebook": re.compile(r"(?:https?://)?(?:www\.)?facebook\.com/[^\s\"'<>]+", re.I),
    "instagram": re.compile(r"(?:https?://)?(?:www\.)?instagram\.com/[^\s\"'<>]+", re.I),
    "twitter": re.compile(r"(?:https?://)?(?:www\.)?(?:twitter|x)\.com/[^\s\"'<>]+", re.I),
    "youtube": re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/(?:channel|user|c)/[^\s\"'<>]+", re.I),
    "ok": re.compile(r"(?:https?://)?(?:www\.)?ok\.ru/[^\s\"'<>]+", re.I),
}

# ── Списки общих email-префиксов (НЕ личные) ───────────────────────────────
GENERIC_EMAIL_PREFIXES = frozenset({
    "info", "support", "help", "admin", "office", "pr", "secretary",
    "reception", "contact", "mail", "noreply", "sales", "marketing",
    "press", "media", "feedback", "webmaster", "postmaster", "abuse",
    "security", "careers", "jobs", "hr", "legal", "compliance",
    "billing", "finance", "accounting", "it", "tech", "dev", "api",
    "team", "hello", "general", "service", "inquiry", "request",
    "booking", "order", "subscribe", "unsubscribe", "newsletter",
    "post", "no-reply", "do-not-reply", "donotreply",
})

# ── Ключевые слова должностей для валидации ─────────────────────────────────
POSITION_KEYWORDS_RU = {
    "директор", "менеджер", "начальник", "руководитель", "специалист",
    "инженер", "бухгалтер", "экономист", "юрист", "аналитик",
    "координатор", "администратор", "секретарь", "ассистент",
    "консультант", "заведующий", "председатель", "президент",
    "вице-президент", "заместитель", "главный", "старший", "младший",
    "ведущий", "главбух", "технолог", "программист", "разработчик",
    "дизайнер", "маркетолог", "логист", "оператор", "диспетчер",
    "мастер", "механик", "электрик", "водитель", "охранник",
    "продавец", "кассир", "товаровед", "агент", "представитель",
    "партнёр", "учредитель", "основатель", "совладелец", "акционер",
    "член правления", "советник", "эксперт", "исследователь",
    "professor", "доцент", "профессор", "врач", "доктор",
}

POSITION_KEYWORDS_EN = {
    "director", "manager", "head", "chief", "officer", "president",
    "vice president", "vp", "ceo", "cto", "cfo", "coo", "cmo", "cio",
    "lead", "senior", "junior", "engineer", "developer", "designer",
    "analyst", "consultant", "coordinator", "specialist", "assistant",
    "secretary", "accountant", "lawyer", "advisor", "partner",
    "founder", "co-founder", "owner", "chairman", "board member",
}



# ── Быстрая валидация позиции (до нормализатора) ──────────────────────────────

_MONTHS_RU = {"января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря","январь","февраль","март","апрель","май","июнь","июль","август","сентябрь","октябрь","ноябрь","декабрь"}
_GARBAGE_POS = {"подробнее","подробности","далее","галерея","республика","кооперативная","пленэр","бокситов","тимана","компания","корпорация","конференция","форум","выставка"}

def _quick_validate_position(text: str) -> bool:
    """Быстрая проверка: может ли текст быть должностью."""
    if not text or len(text) < 3 or len(text) > 100:
        return False
    lower = text.lower()
    # Содержит месяц → дата
    for m in _MONTHS_RU:
        if m in lower:
            return False
    # Начинается с цифры → дата или номер
    if text[0].isdigit():
        return False
    # Мусорные слова
    for w in lower.split():
        if w.strip(".,;:-") in _GARBAGE_POS:
            return False
    # Содержит @ или URL
    if "@" in text or "http" in lower or "www." in lower:
        return False
    # Заканчивается на ":"
    if text.endswith(":"):
        return False
    # Год (2020-2030)
    import re as _re
    if _re.search(r"\b20[12]\d\b", text):
        return False
    return True


_GENITIVE_HISTORICAL = {"ленина","менделеева","ломоносова","пушкина","сеченова","пирогова","губкина","баумана","плеханова","вернадского","королёва","королева","сербского","мозолина","гагарина","чайковского","толстого","достоевского","чехова","горького","тургенева","лермонтова","тимирязева","прянишникова","бакулева","лавёрова","лаверова","вавилова","мичурина","докучаева","склифосовского","боткина","филатова","бурденко","бехтерева","павлова","мечникова","туполева","курчатова","герцена","кирова","фрунзе"}
_PREPOSITIONAL_PLACES = {"россии","москве","петербурге","челябинске","екатеринбурге","казани","новосибирске","красноярске","самаре","уфе","перми","воронеже","волгограде","краснодаре","омске","ростове","нижнем","крыму","сибири","урале"}

_GARBAGE_NAME_WORDS = {"подробнее","подробности","банкротство","банкротства","практика","компания","компании","галерея","кооперативная","республика","металлургический","пленэр","юрист","адвокат","партнер","партнёр","сооснователь","основатель","бокситов","тимана","конференция","форум","выставка","мероприятие","семинар","далее","ещё","еще","смотреть","читать","туркменистан","узбекистан","украина","казахстан","таджикистан","кыргызстан","белоруссия","беларусь","грузия","армения","азербайджан","молдова","латвия","литва","эстония","гайана","гайаны","арест","ареста","строительства","итоги","активная","фаза","победы","трудовые","будни"}

def _quick_validate_name(fio: str) -> bool:
    """Быстрая проверка: может ли текст быть реальным ФИО."""
    if not fio or len(fio) < 4 or len(fio) > 70:
        return False
    words = fio.lower().split()
    for w in words:
        if w.strip(".,;:-") in _GARBAGE_NAME_WORDS:
            return False
    # Содержит цифры — не ФИО
    if any(c.isdigit() for c in fio):
        return False
    # Содержит метки полей
    for w in fio.lower().split():
        wc = w.strip(".,;:-()")
        if wc in ("тел", "tel", "телефон", "email", "e-mail", "факс", "fax", "адрес"):
            return False
    # Последнее слово — род. падеж исторической личности (название объекта)
    fio_words = fio.lower().split()
    if fio_words and fio_words[-1].strip(".,;:-") in _GENITIVE_HISTORICAL:
        return False
    # Первое слово — город/страна в предл. падеже
    if fio_words and fio_words[0].strip(".,;:-") in _PREPOSITIONAL_PLACES:
        return False
    return True


class ContactExtractor:
    """
    Извлекает контактные данные из HTML-страниц.
    Использует 3-фазный пайплайн: regex → LLM → post-processing.
    Всегда работает в режиме Variant B (AI) с fallback на Variant A.
    """

    def __init__(
        self,
        variant: ExtractionVariant = ExtractionVariant.AI,
        target_positions: Optional[list[str]] = None,
        mode: ParseMode = ParseMode.SITES_ALL_POSITIONS,
    ) -> None:
        self._variant = variant
        self._target_positions = target_positions or []
        self._mode = mode

        # Загружаем словари должностей
        self._positions_ru: dict = _load_json("positions_ru.json")
        self._positions_en: dict = _load_json("positions_en.json")

        # Все нормализованные должности для fuzzy-поиска
        self._all_positions: list[str] = (
            list(self._positions_ru.keys()) + list(self._positions_en.keys())
        )

        # LLM клиент (ленивая инициализация)
        self._llm: Optional[Any] = None

        # Счётчики
        self.tokens_used: int = 0
        self.fallback_count: int = 0
        self._fallback_log: list[dict] = []

    def _get_llm(self):
        """Ленивая инициализация LLM-клиента."""
        if self._llm is None:
            from app.core.llm_client import LLMClient
            self._llm = LLMClient()
        return self._llm

    async def extract(
        self,
        html: str,
        page_url: str,
        site_url: str,
        company_name: Optional[str] = None,
        inn: Optional[str] = None,
        language: str = "unknown",
    ) -> list[ContactRecord]:
        """
        Извлекает контактные данные из HTML страницы.
        3-фазный пайплайн: regex предобработка → LLM → пост-процессинг.
        """
        if not html:
            return []

        # ── Фаза 1: Regex предобработка ─────────────────────────────────
        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all(["script", "style", "noscript", "head"]):
            tag.decompose()

        full_text = soup.get_text(separator=" ", strip=True)
        clean_text = soup.get_text(separator="\n", strip=True)

        # Предварительное извлечение данных regex-ом
        pre_data = self._phase1_regex_extract(full_text, html, soup, site_url, company_name, inn)

        # ── Фаза 2: LLM извлечение (Вариант B) ─────────────────────────
        if self._variant == ExtractionVariant.AI:
            try:
                contacts = await self._phase2_llm_extract(
                    clean_text=clean_text,
                    page_url=page_url,
                    site_url=site_url,
                    pre_data=pre_data,
                    language=language,
                )
                # ── Фаза 3 уже применена внутри _phase2_llm_extract ────
                return contacts
            except Exception as exc:
                from app.core.llm_client import LLMClientError
                if isinstance(exc, LLMClientError):
                    reason = exc.reason
                else:
                    reason = FallbackReason.LLM_UNAVAILABLE

                self.fallback_count += 1
                self._fallback_log.append({
                    "url": page_url,
                    "reason": reason.value,
                    "error": str(exc),
                    "timestamp": datetime.utcnow().isoformat(),
                })
                logger.warning(
                    "Фоллбэк на Вариант A для %s (причина: %s): %s",
                    page_url,
                    reason.value,
                    exc,
                )
                # Фоллбэк на классический вариант + фаза 3 пост-процессинг
                contacts = self._extract_classic(
                    html=html,
                    page_url=page_url,
                    site_url=site_url,
                    company_name=pre_data["company_name"],
                    inn=pre_data["inn"],
                    language=language,
                    variant=ExtractionVariant.CLASSIC,
                    pre_data=pre_data,
                )
                return self._phase3_postprocess(contacts, site_url)
        else:
            contacts = self._extract_classic(
                html=html,
                page_url=page_url,
                site_url=site_url,
                company_name=pre_data["company_name"],
                inn=pre_data["inn"],
                language=language,
                pre_data=pre_data,
            )
            # Всегда применяем фазу 3 даже для Варианта A
            return self._phase3_postprocess(contacts, site_url)

    # ── Фаза 1: Regex предобработка ─────────────────────────────────────────

    def _phase1_regex_extract(
        self,
        full_text: str,
        html: str,
        soup: BeautifulSoup,
        site_url: str,
        company_name: Optional[str],
        inn: Optional[str],
    ) -> dict[str, Any]:
        """
        Фаза 1: Извлекает базовые данные regex-ом.
        НЕ пытается извлечь должности или классифицировать email.
        """
        detected_company = company_name or self._extract_company_name(soup, site_url) or ""
        detected_inn = inn or self._extract_inn_from_text(full_text)
        detected_kpp = self._extract_kpp_from_text(full_text)

        # Все email
        all_emails = list(set(RE_EMAIL.findall(full_text)))

        # Классификация email на общие и потенциально личные
        company_emails = []
        candidate_personal_emails = []
        for email in all_emails:
            if self._is_generic_email(email):
                company_emails.append(email.lower())
            else:
                candidate_personal_emails.append(email.lower())

        # Лучший общий email
        best_company_email = self._extract_company_email(full_text, site_url)

        # Все телефоны
        all_phones = self._extract_phones(full_text)

        # Социальные сети
        social_links = self._extract_social_links(html)

        # ФИО (для передачи в LLM как подсказка)
        all_fios = self._extract_all_fios(full_text)

        return {
            "company_name": detected_company,
            "inn": detected_inn,
            "kpp": detected_kpp,
            "company_email": best_company_email,
            "company_emails": company_emails,
            "candidate_personal_emails": candidate_personal_emails,
            "all_phones": all_phones,
            "social_links": social_links,
            "all_fios": all_fios,
        }

    # ── Фаза 2: LLM извлечение ──────────────────────────────────────────────

    async def _phase2_llm_extract(
        self,
        clean_text: str,
        page_url: str,
        site_url: str,
        pre_data: dict[str, Any],
        language: str,
    ) -> list[ContactRecord]:
        """
        Фаза 2: Отправляет данные в LLM (Perplexity) для интеллектуального извлечения.
        """
        llm = self._get_llm()

        if not llm.is_available:
            from app.core.llm_client import LLMClientError
            raise LLMClientError(
                "LLM недоступен (не настроен или бюджет исчерпан)",
                FallbackReason.LLM_UNAVAILABLE,
            )

        # Вызываем LLM
        result = await llm.extract_contacts(
            text=clean_text,
            page_url=page_url,
            company_name=pre_data.get("company_name"),
            target_positions=self._target_positions or None,
        )
        self.tokens_used = llm.tokens_used

        # Парсим ответ LLM в ContactRecord
        contacts: list[ContactRecord] = []

        llm_company = result.get("company_name") or pre_data.get("company_name")
        llm_inn = result.get("inn") or pre_data.get("inn")
        llm_kpp = result.get("kpp") or pre_data.get("kpp")

        # Общий email: из LLM или из regex
        llm_company_emails = result.get("company_emails", [])
        company_email = None
        if llm_company_emails and isinstance(llm_company_emails, list):
            company_email = llm_company_emails[0] if llm_company_emails else None
        if not company_email:
            company_email = pre_data.get("company_email")

        for item in result.get("contacts", []):
            if not isinstance(item, dict):
                continue

            fio = item.get("full_name")
            if not fio:
                continue

            position_raw = item.get("position_raw")
            position_normalized = item.get("position_normalized")

            # Если LLM не дал нормализованную должность, попробуем сами
            if position_raw and not position_normalized:
                position_normalized = self._normalize_position(position_raw)

            # Фильтр по целевым должностям (режим 1)
            if (
                self._mode == ParseMode.SITES_WITH_TARGET_POSITIONS
                and self._target_positions
                and not self._position_matches_targets(position_raw or "", position_normalized or "")
            ):
                continue

            phone_raw = item.get("phone")
            phone_normalized = self._normalize_phone(phone_raw) if phone_raw else None

            personal_email = item.get("personal_email")

            role_type = item.get("role_type")

            social_data = item.get("social_links", {}) or {}
            social_links = SocialLinks(
                vk=social_data.get("vk"),
                telegram=social_data.get("telegram"),
                linkedin=social_data.get("linkedin"),
                facebook=social_data.get("facebook"),
                instagram=social_data.get("instagram"),
                twitter=social_data.get("twitter"),
            )

            comment = f"Роль: {role_type}" if role_type else None

            contacts.append(ContactRecord(
                company_name=llm_company,
                site_url=site_url,
                inn=llm_inn,
                kpp=llm_kpp,
                company_email=company_email,
                position_raw=position_raw,
                position_normalized=position_normalized,
                full_name=fio,
                personal_email=personal_email,
                phone=phone_normalized,
                phone_raw=phone_raw,
                social_links=social_links,
                source_url=page_url,
                page_language=language,
                status="ok",
                extraction_variant=ExtractionVariant.AI,
                comment=comment,
            ))

        # Применяем Фазу 3: пост-процессинг
        return self._phase3_postprocess(contacts, site_url)

    # ── Фаза 3: Пост-процессинг / Валидация ─────────────────────────────────

    def _phase3_postprocess(
        self,
        contacts: list[ContactRecord],
        site_url: str,
    ) -> list[ContactRecord]:
        """
        Фаза 3: Строгая валидация и очистка извлечённых контактов.
        Применяется ВСЕГДА — после LLM и после классического извлечения.
        """
        validated: list[ContactRecord] = []

        for contact in contacts:
            # Валидация ФИО
            if not self._validate_full_name(contact.full_name):
                logger.debug("Отклонено ФИО: %s", contact.full_name)
                continue

            # Валидация должности
            contact.position_raw = self._validate_position(contact.position_raw)
            if contact.position_raw:
                if not contact.position_normalized:
                    contact.position_normalized = self._normalize_position(contact.position_raw)
            else:
                contact.position_normalized = None

            # Валидация личного email
            if contact.personal_email:
                if self._is_generic_email(contact.personal_email):
                    # Перемещаем общий email в company_email если там пусто
                    if not contact.company_email:
                        contact.company_email = contact.personal_email.lower()
                    contact.personal_email = None
                else:
                    contact.personal_email = contact.personal_email.lower()

            # Валидация ИНН
            if contact.inn:
                digits = contact.inn.strip()
                if not digits.isdigit() or len(digits) not in (10, 12):
                    contact.inn = None

            # Валидация КПП
            if contact.kpp:
                digits = contact.kpp.strip()
                if not digits.isdigit() or len(digits) != 9:
                    contact.kpp = None

            validated.append(contact)

        # Дедупликация
        return self._deduplicate(validated)

    @staticmethod
    def _validate_full_name(name: Optional[str]) -> bool:
        """
        Проверяет, что ФИО похоже на реальное имя.
        Отклоняет: одиночные слова, числа, URL, предложения,
        организации, подразделения, политиков.
        """
        if not name or not name.strip():
            return False

        name = name.strip()

        # Слишком короткое или длинное
        if len(name) < 4 or len(name) > 100:
            return False

        # Содержит числа, URL, email
        if re.search(r"[\d@:/]", name):
            return False

        # Содержит слишком много слов (предложение)
        words = name.split()
        if len(words) < 2 or len(words) > 5:
            return False

        # Каждое слово должно начинаться с заглавной буквы
        for word in words:
            # Разрешаем дефисные фамилии и инициалы (А.)
            for part in word.split("-"):
                part_clean = part.rstrip(".")
                if part_clean and not part_clean[0].isupper():
                    return False

        # Исключаем организационные термины
        org_keywords = {
            "компания", "отдел", "управление", "департамент", "служба",
            "филиал", "представительство", "группа", "холдинг", "корпорация",
            "общество", "фонд", "ассоциация", "союз", "институт",
            "министерство", "правительство", "администрация", "комитет",
        }
        name_lower = name.lower()
        for kw in org_keywords:
            if kw in name_lower:
                return False

        # Исключаем известных политиков
        politicians = {
            "путин", "медведев", "мишустин", "лавров", "шойгу",
            "навальный", "зеленский", "байден", "трамп", "макрон",
            "си цзиньпин", "меркель",
        }
        for pol in politicians:
            if pol in name_lower:
                return False

        return True

    @staticmethod
    def _validate_position(position: Optional[str]) -> Optional[str]:
        """
        Проверяет, что должность — это реальное название позиции.
        Отклоняет: телефоны, email, адреса, даты, URL, мусор.
        """
        if not position or not position.strip():
            return None

        position = position.strip()

        # Слишком короткое или длинное
        if len(position) < 3 or len(position) > 150:
            return None

        # Содержит email
        if "@" in position:
            return None

        # Содержит URL
        if re.search(r"https?://|www\.", position, re.I):
            return None

        # Содержит телефонный номер
        if re.search(r"(?:\+7|8[\s\-]?\(?\d{3})\)?[\s\-]?\d{3}", position):
            return None

        # Содержит дату (ДД.ММ.ГГГГ или ГГГГ-ММ-ДД)
        if re.search(r"\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2}", position):
            return None

        # Содержит слишком много цифр (адрес, индекс)
        digit_count = sum(1 for c in position if c.isdigit())
        if digit_count > 4:
            return None

        # Содержит физический адрес
        address_markers = ["ул.", "пр.", "пер.", "д.", "кв.", "корп.", "стр.", "г.", "обл."]
        pos_lower = position.lower()
        address_hits = sum(1 for m in address_markers if m in pos_lower)
        if address_hits >= 2:
            return None

        # Слишком длинное предложение (>6 слов обычно не должность)
        if len(position.split()) > 8:
            return None

        return position

    @staticmethod
    def _is_generic_email(email: str) -> bool:
        """Проверяет, является ли email общим/корпоративным (НЕ личным)."""
        if not email:
            return False
        prefix = email.split("@")[0].lower().strip()
        # Точное совпадение с общими префиксами
        if prefix in GENERIC_EMAIL_PREFIXES:
            return True
        # Проверяем с дефисами и точками: no-reply, do.not.reply
        normalized = prefix.replace("-", "").replace(".", "").replace("_", "")
        normalized_prefixes = {p.replace("-", "").replace(".", "").replace("_", "") for p in GENERIC_EMAIL_PREFIXES}
        if normalized in normalized_prefixes:
            return True
        return False

    @staticmethod
    def _deduplicate(contacts: list[ContactRecord]) -> list[ContactRecord]:
        """Удаляет дубликаты контактов (по ФИО + компания)."""
        seen: set[str] = set()
        unique: list[ContactRecord] = []
        for c in contacts:
            key = f"{(c.full_name or '').lower().strip()}|{(c.company_name or '').lower().strip()}"
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique

    # ── Вариант A: Классическое извлечение (fallback) ────────────────────────

    def _extract_classic(
        self,
        html: str,
        page_url: str,
        site_url: str,
        company_name: Optional[str],
        inn: Optional[str],
        language: str,
        variant: ExtractionVariant = ExtractionVariant.CLASSIC,
        pre_data: Optional[dict[str, Any]] = None,
    ) -> list[ContactRecord]:
        """Классическое извлечение через DOM + регулярные выражения."""
        soup = BeautifulSoup(html, "lxml")

        for tag in soup.find_all(["script", "style", "noscript", "head"]):
            tag.decompose()

        full_text = soup.get_text(separator=" ", strip=True)

        detected_company = company_name or self._extract_company_name(soup, site_url) or ""
        detected_inn = inn or self._extract_inn_from_text(full_text)
        detected_kpp = pre_data.get("kpp") if pre_data else self._extract_kpp_from_text(full_text)
        company_email = pre_data.get("company_email") if pre_data else self._extract_company_email(full_text, site_url)
        social_links_global = pre_data.get("social_links") if pre_data else self._extract_social_links(html)

        person_blocks = self._find_person_blocks(soup)

        contacts: list[ContactRecord] = []

        if person_blocks:
            for block in person_blocks:
                block_text = block.get_text(separator=" ", strip=True)
                block_html = str(block)

                fio = self._extract_fio(block_text)
                if not fio:
                    continue

                position_raw = self._extract_position_from_block(block)
                position_normalized = self._normalize_position(position_raw) if position_raw else None

                if (
                    self._mode == ParseMode.SITES_WITH_TARGET_POSITIONS
                    and self._target_positions
                    and not self._position_matches_targets(position_raw or "", position_normalized or "")
                ):
                    continue

                emails = RE_EMAIL.findall(block_html)
                personal_email = next(
                    (e for e in emails if not self._is_generic_email(e)),
                    None,
                )

                phones = self._extract_phones(block_text)
                phone_raw = phones[0] if phones else None
                phone_normalized = self._normalize_phone(phone_raw) if phone_raw else None

                block_social = self._extract_social_links(block_html)

                contacts.append(ContactRecord(
                    company_name=detected_company,
                    site_url=site_url,
                    inn=detected_inn,
                    kpp=detected_kpp,
                    company_email=company_email,
                    position_raw=position_raw,
                    position_normalized=position_normalized,
                    full_name=fio,
                    personal_email=personal_email,
                    phone=phone_normalized,
                    phone_raw=phone_raw,
                    social_links=block_social,
                    source_url=page_url,
                    page_language=language,
                    status="ok",
                    extraction_variant=variant,
                ))

        if not contacts:
            all_fios = self._extract_all_fios(full_text)
            all_emails = RE_EMAIL.findall(full_text)
            all_phones = self._extract_phones(full_text)

            for i, fio in enumerate(all_fios[:20]):
                position_raw = self._extract_position_near_fio(full_text, fio)
                position_normalized = self._normalize_position(position_raw) if position_raw else None

                if (
                    self._mode == ParseMode.SITES_WITH_TARGET_POSITIONS
                    and self._target_positions
                    and not self._position_matches_targets(position_raw or "", position_normalized or "")
                ):
                    continue

                personal_email = all_emails[i] if i < len(all_emails) else None
                phone_raw = all_phones[i] if i < len(all_phones) else None
                phone_normalized = self._normalize_phone(phone_raw) if phone_raw else None

                contacts.append(ContactRecord(
                    company_name=detected_company,
                    site_url=site_url,
                    inn=detected_inn,
                    kpp=detected_kpp,
                    company_email=company_email,
                    position_raw=position_raw,
                    position_normalized=position_normalized,
                    full_name=fio,
                    personal_email=personal_email,
                    phone=phone_normalized,
                    phone_raw=phone_raw,
                    social_links=social_links_global if isinstance(social_links_global, SocialLinks) else SocialLinks(),
                    source_url=page_url,
                    page_language=language,
                    status="ok",
                    extraction_variant=variant,
                ))

        return contacts

    # ── Вспомогательные методы ───────────────────────────────────────────────

    @staticmethod
    def _extract_company_name(soup: BeautifulSoup, site_url: str = "") -> Optional[str]:
        """Извлекает юридическое название компании. Приоритет: og:site_name > title domain part.
        НЕ берём H1 и заголовки страниц — они содержат мусор ('Наша команда', 'Контакты')."""
        import re as _re

        # Мусорные заголовки страниц (начало title)
        _TITLE_GARBAGE_PREFIXES = re.compile(
            r'^(наша команда|команда|руководство|контакты|сотрудники|персонал|главная|'
            r'о компании|о нас|менеджмент|management|our team|team|staff|leadership|'
            r'contacts|about us|about)\s*[-—–·:,]?\s*',
            re.IGNORECASE,
        )
        _GARBAGE_WORDS = {
            "главная", "контакты", "о компании", "о нас", "наша команда",
            "команда", "руководство", "сотрудники", "персонал", "меню",
            "management", "our team", "team", "staff", "contacts", "about",
        }
        # Описательные начала — характерны для слоганов, не для названий
        _DESCRIPTION_STARTS = (
            "специализированн", "ведущ", "крупнейш", "производ", "предприятие",
            "компания, которая", "мы ", "our company",
        )
        _GARBAGE_STARTS = (
            "контакт", "главная", "о компании", "о нас", "наша команд",
            "команд", "руководств", "сотрудник", "персонал", "меню",
            "свяжитесь", "пишите", "позвоните", "contact", "reach",
            "get in touch", "write us", "call us", "about us", "about",
            "management", "our team", "team", "staff", "home",
        )

        # og:site_name — самый надёжный источник
        og_site = soup.find("meta", property="og:site_name")
        if og_site and og_site.get("content"):
            name = str(og_site["content"]).strip()
            if name and len(name) >= 2:
                return name

        def _clean_org_name(s: str) -> str:
            """Убираем геогр. уточнения, кавычки, орг. формы."""
            import re as _re2
            s = _re2.sub(r'\s+г\.\s+[\w-]+$', '', s).strip()
            _mq = _re2.search(r'[«\u201c"](.*?)[»\u201d"]', s)
            if _mq:
                s = _mq.group(1).strip()
            s = _re2.sub(r'^(ООО|ОАО|ЗАО|ПАО|ИП|НПАО|МУП|МБОУ|МБУ)\s+', '', s).strip()
            return s

        def _is_garbage_candidate(candidate: str) -> bool:
            """Проверяет, является ли кандидат мусором."""
            low = candidate.lower()
            if low in _GARBAGE_WORDS:
                return True
            if len(candidate) < 2:
                return True
            if any(low.startswith(g) for g in _GARBAGE_STARTS):
                return True
            if any(low.startswith(g) for g in _DESCRIPTION_STARTS):
                return True
            return False

        def _best_part_from_title(text: str) -> Optional[str]:
            """Из title с разделителем выбираем часть не из списка мусора."""
            for sep in ("|", "—", "–", "·"):
                parts = [p.strip() for p in text.split(sep) if p.strip()]
                if len(parts) >= 2:
                    # Сначала пробуем последнюю, потом первую
                    for candidate in [parts[-1], parts[0]]:
                        if not _is_garbage_candidate(candidate):
                            cleaned = _clean_org_name(candidate)
                            return cleaned if cleaned and len(cleaned) >= 2 else candidate
            # ' - ' (с пробелами) — предпочитаем самую короткую неmусорную часть (обычно название)
            if " - " in text:
                parts = [p.strip() for p in text.split(" - ") if p.strip()]
                if len(parts) >= 2:
                    for candidate in sorted(parts, key=len):
                        if not _is_garbage_candidate(candidate):
                            cleaned = _clean_org_name(candidate)
                            return cleaned if cleaned and len(cleaned) >= 2 else candidate
            return None

        # Пробуем title — берём наилучшую часть после разделителя
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
            part = _best_part_from_title(title)
            if part:
                return part
            # Нет подходящего разделителя — пробуем убрать мусорный префикс
            cleaned = _TITLE_GARBAGE_PREFIXES.sub("", title).strip()
            if cleaned and len(cleaned) >= 2 and cleaned.lower() != title.lower():
                # Повторяем поиск разделителя уже в очищенной строке
                # (обрабатывает «Контакты ENBRA – свяжитесь с нами» → «ENBRA»)
                part2 = _best_part_from_title(cleaned)
                if part2:
                    return part2
                cleaned2 = _clean_org_name(cleaned)
                if cleaned2 and len(cleaned2) >= 2:
                    return cleaned2
                return cleaned

        # og:title как последний fallback
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            t = str(og_title["content"]).strip()
            part = _best_part_from_title(t)
            if part:
                return part
            cleaned = _TITLE_GARBAGE_PREFIXES.sub("", t).strip()
            if cleaned and len(cleaned) >= 2 and cleaned.lower() != t.lower():
                part2 = _best_part_from_title(cleaned)
                if part2:
                    return part2
                cleaned2 = _clean_org_name(cleaned)
                return cleaned2 if cleaned2 and len(cleaned2) >= 2 else cleaned
            cleaned_direct = _clean_org_name(t)
            if cleaned_direct and cleaned_direct != t and len(cleaned_direct) >= 2:
                return cleaned_direct

        return None


    @staticmethod
    def _extract_inn_from_text(text: str) -> Optional[str]:
        """Ищет ИНН в тексте с приоритетом явного контекста."""
        for m in RE_INN.finditer(text):
            val = m.group(1) or m.group(2)
            if val and len(val) in (10, 12):
                return val
        return None

    @staticmethod
    def _extract_kpp_from_text(text: str) -> Optional[str]:
        """Ищет КПП в тексте."""
        for m in RE_KPP.finditer(text):
            val = m.group(1) or m.group(2)
            if val:
                return val
        return None

    @staticmethod
    def _extract_company_email(text: str, site_url: str) -> Optional[str]:
        """Извлекает общий email компании."""
        domain = urlparse(site_url).netloc.lower().lstrip("www.")

        emails = RE_EMAIL.findall(text)
        for email in emails:
            if domain and domain in email.lower():
                prefix = email.split("@")[0].lower()
                if prefix in GENERIC_EMAIL_PREFIXES:
                    return email.lower()
        for email in emails:
            lower = email.lower()
            prefix = lower.split("@")[0]
            if prefix in GENERIC_EMAIL_PREFIXES:
                return lower
        return None

    @staticmethod
    def _extract_phones(text: str) -> list[str]:
        """Извлекает все телефонные номера из текста."""
        phones = RE_PHONE.findall(text)
        return [" ".join(p.split()) for p in phones if p.strip()]

    @staticmethod
    def _normalize_phone(raw: Optional[str]) -> Optional[str]:
        """Нормализует телефонный номер в формат E.164."""
        if not raw:
            return None
        try:
            import phonenumbers
            cleaned = re.sub(r"[^\d+]", "", raw)
            if cleaned.startswith("8") and len(cleaned) == 11:
                cleaned = "+7" + cleaned[1:]
            elif cleaned.startswith("7") and len(cleaned) == 11:
                cleaned = "+" + cleaned

            parsed = phonenumbers.parse(cleaned, "RU")
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed,
                    phonenumbers.PhoneNumberFormat.E164,
                )
        except Exception:
            pass
        cleaned = re.sub(r"[^\d+\-\(\)\s]", "", raw).strip()
        return cleaned if cleaned else None

    @staticmethod
    def _extract_fio(text: str) -> Optional[str]:
        """Извлекает первое ФИО из текста."""
        match = RE_FIO_RU.search(text)
        if match:
            fio = f"{match.group(1)} {match.group(2)} {match.group(3)}"
            if _quick_validate_name(fio):
                return fio

        match = RE_FIO_INITIALS.search(text)
        if match:
            return f"{match.group(1)}{match.group(2)} {match.group(3)}"

        return None

    @staticmethod
    def _extract_all_fios(text: str) -> list[str]:
        """Извлекает все ФИО из текста."""
        results = []
        seen: set[str] = set()

        for m in RE_FIO_RU.finditer(text):
            fio = f"{m.group(1)} {m.group(2)} {m.group(3)}"
            if fio not in seen and _quick_validate_name(fio):
                seen.add(fio)
                results.append(fio)

        for m in RE_FIO_INITIALS.finditer(text):
            fio = f"{m.group(1)}{m.group(2)} {m.group(3)}"
            if fio not in seen and _quick_validate_name(fio):
                seen.add(fio)
                results.append(fio)

        return results

    @staticmethod
    def _extract_position_near_fio(text: str, fio: str) -> Optional[str]:
        """Ищет должность рядом с ФИО в тексте."""
        idx = text.find(fio)
        if idx == -1:
            return None

        context_start = max(0, idx - 200)
        context_end = min(len(text), idx + len(fio) + 200)
        context = text[context_start:context_end]

        pos_patterns = [
            r"(Генеральный директор|Директор|Заместитель|Главный \w+|Руководитель|Начальник|Председатель|Президент|Вице-президент|Технический директор|Финансовый директор|Исполнительный директор|CEO|CTO|CFO|COO|VP|Head of|Director of|Manager)",
            r"([\u0410-\u042f\u0401][\u0430-\u044f\u0451]+ директор|[\u0410-\u042f\u0401][\u0430-\u044f\u0451]+ руководитель|[\u0410-\u042f\u0401][\u0430-\u044f\u0451]+ менеджер)",
        ]
        for pattern in pos_patterns:
            m = re.search(pattern, context, re.I)
            if m:
                return m.group(1).strip()

        return None

    def _normalize_position(self, position_raw: Optional[str]) -> Optional[str]:
        """
        Нормализует должность, сопоставляя со словарём через fuzzy-поиск.
        """
        if not position_raw or not position_raw.strip():
            return None

        position_lower = position_raw.strip().lower()

        # Точное совпадение
        for pos_dict in (self._positions_ru, self._positions_en):
            for key, val in pos_dict.items():
                if key.lower() == position_lower:
                    return val if isinstance(val, str) else key

        # Fuzzy-поиск
        try:
            from rapidfuzz import fuzz, process

            all_keys = list(self._positions_ru.keys()) + list(self._positions_en.keys())
            if not all_keys:
                return position_raw

            result = process.extractOne(
                position_lower,
                [k.lower() for k in all_keys],
                scorer=fuzz.token_sort_ratio,
                score_cutoff=75,
            )
            if result:
                best_key = all_keys[result[2]]
                normalized = (
                    self._positions_ru.get(best_key)
                    or self._positions_en.get(best_key)
                    or best_key
                )
                return normalized if isinstance(normalized, str) else best_key
        except ImportError:
            pass

        return position_raw

    def _position_matches_targets(
        self,
        position_raw: str,
        position_normalized: str,
    ) -> bool:
        """Проверяет, соответствует ли должность целевым должностям."""
        if not self._target_positions:
            return True

        combined = f"{position_raw} {position_normalized}".lower()

        for target in self._target_positions:
            target_lower = target.lower()
            if target_lower in combined:
                return True
            try:
                from rapidfuzz import fuzz
                if fuzz.partial_ratio(target_lower, combined) >= 70:
                    return True
            except ImportError:
                pass

        return False

    def _find_person_blocks(self, soup: BeautifulSoup) -> list[Tag]:
        """Находит блоки HTML с информацией о персонах."""
        blocks: list[Tag] = []

        card_patterns = re.compile(
            r"(person|employee|staff|team|member|manager|director|contact|"
            r"card|profile|bio|\u0447еловек|\u0441отрудник|\u0440уководитель|\u043fерсона|\u043aонтакт)",
            re.I,
        )

        for tag in soup.find_all(["div", "article", "section", "li"]):
            classes = " ".join(tag.get("class", []))
            tag_id = tag.get("id", "")
            if card_patterns.search(classes) or card_patterns.search(tag_id):
                text = tag.get_text(strip=True)
                if len(text) > 20 and RE_FIO_RU.search(text):
                    blocks.append(tag)

        if blocks:
            return blocks

        for parent in soup.find_all(["ul", "div", "section"]):
            children = parent.find_all(["li", "div", "article"], recursive=False)
            if len(children) < 2:
                continue
            fio_children = [c for c in children if RE_FIO_RU.search(c.get_text())]
            if len(fio_children) >= 2:
                blocks.extend(fio_children)
                break

        return blocks

    @staticmethod
    def _extract_position_from_block(block: Tag) -> Optional[str]:
        """Извлекает должность из HTML-блока персоны."""
        pos_patterns = re.compile(
            r"(position|title|role|post|job|\u0434\u043e\u043b\u0436\u043d\u043e\u0441\u0442\u044c|\u0437\u0432\u0430\u043d\u0438\u0435|"
            r"subtitle|caption|function|occupation)",
            re.I,
        )

        for tag in block.find_all(["p", "span", "div", "h3", "h4", "small", "em", "strong"]):
            classes = " ".join(tag.get("class", []))
            if pos_patterns.search(classes):
                text = tag.get_text(strip=True)
                if text and 3 < len(text) < 100 and _quick_validate_position(text):
                    return text

        texts = [t.strip() for t in block.stripped_strings]
        for i, text in enumerate(texts):
            if RE_FIO_RU.search(text) and i + 1 < len(texts):
                next_text = texts[i + 1]
                if 3 < len(next_text) < 100 and not RE_EMAIL.match(next_text) and _quick_validate_position(next_text):
                    return next_text

        return None

    @staticmethod
    def _extract_social_links(html_or_text: str) -> SocialLinks:
        """Извлекает ссылки на социальные сети."""
        result: dict[str, Optional[str]] = {}
        for network, pattern in RE_SOCIAL.items():
            match = pattern.search(html_or_text)
            if match:
                url = match.group()
                if not url.startswith("http"):
                    url = "https://" + url
                result[network] = url
            else:
                result[network] = None
        return SocialLinks(**result)


    async def extract_regex_only(
        self,
        html: str,
        page_url: str,
        site_url: str,
        company_name: Optional[str] = None,
        inn: Optional[str] = None,
        language: str = "unknown",
    ) -> list[ContactRecord]:
        """
        Извлекает контакты ТОЛЬКО regex-ом (Фаза 1 + классический экстрактор). Без LLM.
        Быстро: ~0.1 сек на страницу.
        """
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all(["script", "style", "noscript", "head"]):
            tag.decompose()

        full_text = soup.get_text(separator=" ", strip=True)

        # Фаза 1: Regex предобработка
        pre_data = self._phase1_regex_extract(full_text, html, soup, site_url, company_name, inn)

        # Классический экстрактор (строит ContactRecord без LLM)
        contacts = self._extract_classic(
            html=html,
            page_url=page_url,
            site_url=site_url,
            company_name=pre_data.get("company_name", company_name),
            inn=pre_data.get("inn", inn),
            language=language,
            pre_data=pre_data,
        )

        # Фаза 3: Постобработка
        return self._phase3_postprocess(contacts, site_url)

    async def llm_normalize_batch(
        self,
        contacts: list[ContactRecord],
        company_name: str,
        site_url: str,
    ) -> list[ContactRecord]:
        """
        Нормализует всю таблицу контактов ОДНИМ LLM-запросом.
        Вызывается один раз на весь сайт после regex-извлечения.
        """
        if not contacts:
            return contacts

        llm = self._get_llm()
        if not llm or not llm.is_available:
            return contacts

        # Формируем таблицу для LLM
        rows = []
        for i, c in enumerate(contacts):
            rows.append(f"{i+1}. ФИО: {c.full_name or '-'} | Должность: {c.position_raw or '-'} | Email: {c.personal_email or '-'} | Тел: {c.phone or '-'}")

        table_text = "\n".join(rows)

        prompt_text = (
            f"Сайт: {site_url}\n"
            f"Компания (из входного файла): {company_name}\n\n"
            "Ты нормализуешь таблицу контактов извлечённых парсером с сайта.\n"
            "ПРАВИЛА:\n"
            "1. company_name — ЮРИДИЧЕСКОЕ наименование компании (ООО, ПАО, АО, ЗАО + название). "
            "НЕ домен сайта, НЕ заголовок страницы. Пример: ПАО ММК, ООО АЛРУД, ПАО Лукойл.\n"
            "2. full_name — только реальные ФИО людей. Удали мусор (навигация, заголовки, города). "
            "Если это не человек — поставь null.\n"
            "3. position — реальная должность в компании. "
            "НЕ дата, НЕ город, НЕ заголовок. Если не должность — поставь null.\n"
            "4. personal_email — ТОЛЬКО личный email человека (ivan.petrov@...). "
            "info@, pr@, support@, office@ — это company_email, НЕ личный.\n"
            "5. phone — нормализуй: только цифры, формат 79991234567.\n"
            "6. Если строка полностью мусорная (не человек) — верни full_name: null.\n\n"
            'Верни ТОЛЬКО JSON массив (без markdown, без ```):\n'
            '[{"idx": 1, "company_name": "ООО Название", "full_name": "Фамилия Имя Отчество", '
            '"position": "Должность", "personal_email": "...", "company_email": "...", "phone": "79991234567"}]\n\n'
            f"Таблица:\n{table_text}"
        )

        try:
            import json as _json
            # Используем complete() напрямую, а не extract_contacts()
            llm_provider = llm._provider
            if llm_provider is None:
                return contacts
            
            response = await llm_provider.complete(
                system_prompt="Ты специалист по нормализации контактных данных. Отвечай ТОЛЬКО JSON без markdown.",
                user_prompt=prompt_text,
                max_tokens=4096,
                temperature=0.0,
            )
            
            # Update token count
            self.tokens_used += (response.tokens_prompt or 0) + (response.tokens_completion or 0)
            
            # Parse response
            raw_content = response.content.strip()
            # Strip thinking tags if present
            if "</think>" in raw_content:
                raw_content = raw_content.split("</think>")[-1].strip()
            
            # Try to extract JSON array
            import re as _re_json
            # Look for JSON array
            match = _re_json.search(r'\[.*?\]', raw_content, _re_json.DOTALL)
            if match:
                raw_content = match.group(0)
            
            result_list = _json.loads(raw_content) if raw_content.startswith("[") else []

            normalized = result_list if isinstance(result_list, list) else []
            
            if not normalized:
                return contacts

            # Apply LLM corrections
            idx_map = {item.get("idx", 0): item for item in normalized if isinstance(item, dict)}

            for i, contact in enumerate(contacts):
                correction = idx_map.get(i + 1)
                if not correction:
                    continue

                # If LLM says full_name is null — mark for removal
                if correction.get("full_name") is None:
                    contact.full_name = None
                    continue

                if correction.get("company_name"):
                    contact.company_name = correction["company_name"]
                if correction.get("full_name"):
                    contact.full_name = correction["full_name"]
                if correction.get("position"):
                    contact.position_normalized = correction["position"]
                    if not contact.position_raw:
                        contact.position_raw = correction["position"]
                if correction.get("personal_email"):
                    contact.personal_email = correction["personal_email"]
                if correction.get("company_email") and not contact.company_email:
                    contact.company_email = correction["company_email"]
                if correction.get("phone"):
                    contact.phone = correction["phone"]

            self.tokens_used += len(prompt) // 3  # Approximate

            # Remove entries where LLM set full_name to None
            contacts = [c for c in contacts if c.full_name is not None]

            return contacts

        except Exception as exc:
            logger.warning("LLM batch normalize failed: %s", exc)
            self.fallback_count += 1
            return contacts
