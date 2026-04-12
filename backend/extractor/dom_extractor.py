"""DOM-анализ: извлечение структурных блоков с сотрудниками."""
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag
from backend.utils.logger import get_logger

logger = get_logger("dom_extractor")


@dataclass
class PersonBlock:
    """Блок данных одного человека, извлечённый из DOM."""
    name: str = ""
    position: str = ""
    email: str = ""
    phone: str = ""
    photo_url: str = ""
    raw_text: str = ""


# Паттерн русского ФИО (Фамилия Имя Отчество)
FIO_PATTERN = re.compile(
    r'([А-ЯЁ][а-яё]{1,30})\s+'
    r'([А-ЯЁ][а-яё]{1,30})\s+'
    r'([А-ЯЁ][а-яё]{1,30})'
)

# Паттерн латинского имени (First Last или First Middle Last)
LATIN_NAME_PATTERN = re.compile(
    r'([A-Z][a-z]{1,30})\s+'
    r'(?:([A-Z][a-z]{1,30})\s+)?'
    r'([A-Z][a-z]{1,30})'
)

# Паттерн ФИО с инициалами: Иванов И.И. или И.И. Иванов
FIO_INITIALS_PATTERN = re.compile(
    r'([А-ЯЁ][а-яё]{1,30})\s+([А-ЯЁ])\.\s*([А-ЯЁ])\.|'
    r'([А-ЯЁ])\.\s*([А-ЯЁ])\.\s*([А-ЯЁ][а-яё]{1,30})'
)

EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
PHONE_PATTERN = re.compile(r'(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}')

# Ключевые слова должностей для идентификации блоков
POSITION_KEYWORDS_RU = [
    "директор", "руководитель", "начальник", "менеджер", "инженер",
    "бухгалтер", "юрист", "заместитель", "председатель", "президент",
    "вице-президент", "главный", "ведущий", "старший", "специалист",
    "координатор", "управляющий", "партнёр", "основатель", "учредитель",
    "собственник", "советник", "консультант", "аналитик",
]

POSITION_KEYWORDS_EN = [
    "director", "manager", "head", "chief", "officer", "president",
    "vice", "founder", "partner", "lead", "senior", "engineer",
    "accountant", "ceo", "cto", "cfo", "coo", "cmo", "cio",
    "executive", "chairman", "board",
]

ALL_POSITION_KEYWORDS = POSITION_KEYWORDS_RU + POSITION_KEYWORDS_EN


def _is_position_text(text: str) -> bool:
    """Содержит ли текст ключевое слово должности."""
    t = text.lower().strip()
    return any(kw in t for kw in ALL_POSITION_KEYWORDS)


def _extract_name(text: str) -> str:
    """Извлечь ФИО из текста."""
    m = FIO_PATTERN.search(text)
    if m:
        return m.group(0).strip()
    m = FIO_INITIALS_PATTERN.search(text)
    if m:
        return m.group(0).strip()
    m = LATIN_NAME_PATTERN.search(text)
    if m:
        return m.group(0).strip()
    return ""


def _find_card_containers(soup: BeautifulSoup) -> list[Tag]:
    """Найти контейнеры-карточки сотрудников."""
    containers = []

    # Стратегия 1: div/li с классами, содержащими ключевые слова
    card_class_patterns = [
        "team", "member", "staff", "person", "employee", "leader",
        "manager", "card", "sotrudnik", "specialist", "expert",
    ]
    for tag in soup.find_all(["div", "li", "article", "section"]):
        classes = " ".join(tag.get("class", [])).lower()
        tag_id = (tag.get("id") or "").lower()
        if any(p in classes or p in tag_id for p in card_class_patterns):
            # Проверяем, что это карточка (не контейнер карточек)
            text = tag.get_text(strip=True)
            if 30 < len(text) < 2000:
                containers.append(tag)

    # Стратегия 2: Если карточек мало — ищем по структуре (img + текст)
    if len(containers) < 2:
        for tag in soup.find_all(["div", "li"]):
            has_img = tag.find("img") is not None
            text = tag.get_text(strip=True)
            if has_img and 30 < len(text) < 1500:
                name = _extract_name(text)
                if name and _is_position_text(text):
                    containers.append(tag)

    return containers


def extract_person_blocks(html: str) -> list[PersonBlock]:
    """Извлечь блоки персон из HTML через DOM-анализ."""
    soup = BeautifulSoup(html, "lxml")
    persons = []
    seen_names = set()

    cards = _find_card_containers(soup)
    for card in cards:
        text = card.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        person = PersonBlock(raw_text=text)

        # Извлечение имени
        for line in lines:
            name = _extract_name(line)
            if name:
                person.name = name
                break

        # Извлечение должности
        for line in lines:
            if _is_position_text(line) and line != person.name:
                person.position = line.strip()
                break

        # Извлечение email из блока
        email_match = EMAIL_PATTERN.search(text)
        if email_match:
            person.email = email_match.group(0).lower()

        # Извлечение телефона из блока
        phone_match = PHONE_PATTERN.search(text)
        if phone_match:
            person.phone = phone_match.group(0)

        # Фото
        img = card.find("img")
        if img and img.get("src"):
            person.photo_url = img["src"]

        # Валидация: нужно хотя бы имя или должность
        if person.name or person.position:
            if person.name not in seen_names:
                seen_names.add(person.name)
                persons.append(person)

    # Стратегия fallback: сканируем весь текст страницы
    if not persons:
        persons = _extract_from_flat_text(soup)

    return persons


def _extract_from_flat_text(soup: BeautifulSoup) -> list[PersonBlock]:
    """Извлечь данные из неструктурированного текста (когда нет карточек)."""
    text = soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    persons = []
    seen_names = set()
    i = 0
    while i < len(lines):
        line = lines[i]
        name = _extract_name(line)
        if name and name not in seen_names:
            person = PersonBlock(name=name)
            # Проверяем следующие 3 строки на должность
            for j in range(1, min(4, len(lines) - i)):
                next_line = lines[i + j]
                if _is_position_text(next_line) and not person.position:
                    person.position = next_line.strip()
                email_m = EMAIL_PATTERN.search(next_line)
                if email_m and not person.email:
                    person.email = email_m.group(0).lower()
                phone_m = PHONE_PATTERN.search(next_line)
                if phone_m and not person.phone:
                    person.phone = phone_m.group(0)
            if person.position or person.email:
                seen_names.add(name)
                persons.append(person)
        i += 1
    return persons


def extract_company_info(html: str) -> dict:
    """Извлечь название компании из мета-тегов и DOM."""
    soup = BeautifulSoup(html, "lxml")
    company_name = ""

    # 1. og:site_name
    og = soup.find("meta", property="og:site_name")
    if og and og.get("content"):
        company_name = og["content"].strip()

    # 2. title
    if not company_name:
        title_tag = soup.find("title")
        if title_tag:
            raw = title_tag.get_text(strip=True)
            # Берём часть до разделителя
            for sep in ["|", "—", "-", "–", "·", "•", "/"]:
                if sep in raw:
                    company_name = raw.split(sep)[0].strip()
                    break
            if not company_name:
                company_name = raw

    # 3. og:title
    if not company_name:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            company_name = og_title["content"].strip()

    return {"company_name": company_name}
