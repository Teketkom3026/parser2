"""DOM-анализ: извлечение контактов из HTML-таблиц, карточек и неструктурированного текста."""
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag
from backend.utils.logger import get_logger

logger = get_logger("dom_extractor")


@dataclass
class PersonBlock:
    name: str = ""
    position: str = ""
    email: str = ""
    phone: str = ""
    photo_url: str = ""
    raw_text: str = ""


# ── Паттерны имён ──
FIO_RU = re.compile(
    r'([А-ЯЁ][а-яё]{1,30})\s+([А-ЯЁ][а-яё]{1,30})\s+([А-ЯЁ][а-яё]{1,30})'
)
FIO_RU_INITIALS = re.compile(
    r'([А-ЯЁ][а-яё]{1,30})\s+([А-ЯЁ])\.\s*([А-ЯЁ])\.'
)
FIO_EN = re.compile(
    r'([A-Z][a-z]{1,25})\s+(?:[A-Z][a-z]{1,25}\s+)?([A-Z][a-z]{1,25})'
)

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
# Телефон с добавочным номером
PHONE_RE = re.compile(
    r'(?:\+7|8|7)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
    r'(?:\s*(?:доб\.?|ext\.?|#)\s*\d{1,6})?'
)

POSITION_KW = [
    "директор", "руководитель", "начальник", "менеджер", "инженер",
    "бухгалтер", "юрист", "заместитель", "председатель", "президент",
    "вице", "главный", "ведущий", "старший", "специалист", "координатор",
    "управляющий", "партнёр", "основатель", "учредитель", "собственник",
    "советник", "консультант", "аналитик", "эксперт", "сотрудник",
    "технолог", "экономист", "бухгалтер", "секретарь", "помощник",
    "director", "manager", "head", "chief", "officer", "president",
    "vice", "founder", "partner", "lead", "senior", "engineer",
    "executive", "chairman", "board", "specialist",
]


def _is_position(text: str) -> bool:
    t = text.lower().strip()
    return any(kw in t for kw in POSITION_KW) and len(t) < 120


def _extract_name(text: str) -> str:
    m = FIO_RU.search(text)
    if m:
        return m.group(0).strip()
    m = FIO_RU_INITIALS.search(text)
    if m:
        return m.group(0).strip()
    m = FIO_EN.search(text)
    if m:
        full = m.group(0).strip()
        if len(full.split()) >= 2:
            return full
    return ""


def _extract_email(text: str) -> str:
    m = EMAIL_RE.search(text)
    if m:
        e = m.group(0).lower().strip(".")
        # Фильтруем технические адреса
        if not any(e.endswith(x) for x in ('.png', '.jpg', '.css', '.js')):
            return e
    return ""


def _extract_phone(text: str) -> str:
    m = PHONE_RE.search(text)
    return m.group(0).strip() if m else ""


# ══════════════════════════════════════════════════════════
#  СТРАТЕГИЯ 1: HTML-таблицы (должность | ФИО | тел | email)
# ══════════════════════════════════════════════════════════

def _parse_contact_table(table: Tag) -> list[PersonBlock]:
    """Парсить HTML-таблицу с контактами сотрудников."""
    persons = []
    rows = table.find_all('tr')
    if not rows:
        return persons

    for row in rows:
        cells = row.find_all(['td', 'th'])
        if len(cells) < 2:
            continue

        cell_texts = [c.get_text(separator=" ", strip=True) for c in cells]
        combined = " | ".join(cell_texts)

        person = PersonBlock(raw_text=combined)

        # Ищем имя и должность по всем ячейкам
        for ct in cell_texts:
            if not person.name:
                person.name = _extract_name(ct)
            if not person.position and _is_position(ct) and ct != person.name:
                person.position = ct.strip()
            if not person.email:
                person.email = _extract_email(ct)
            if not person.phone:
                person.phone = _extract_phone(ct)

        # Если первая ячейка — должность, вторая — ФИО (частый паттерн)
        if not person.position and len(cell_texts) >= 2:
            if _is_position(cell_texts[0]):
                person.position = cell_texts[0].strip()
            if not person.name and len(cell_texts) >= 2:
                person.name = _extract_name(cell_texts[1])

        # Требуем хотя бы имя или (должность + телефон/email)
        if person.name or (person.position and (person.email or person.phone)):
            persons.append(person)

    return persons


def _is_contact_table(table: Tag) -> bool:
    """Проверить, содержит ли таблица контактные данные."""
    text = table.get_text(separator=" ", strip=True).lower()
    # Признаки контактной таблицы
    has_email = '@' in text or 'email' in text or 'почта' in text
    has_phone = bool(re.search(r'\+7|\(8\d{2}\)|тел', text))
    has_position = any(kw in text for kw in POSITION_KW[:10])
    has_name = bool(FIO_RU.search(table.get_text()))
    return (has_email or has_phone) and (has_position or has_name)


# ══════════════════════════════════════════════════════════
#  СТРАТЕГИЯ 2: div/article карточки
# ══════════════════════════════════════════════════════════

CARD_CLASS_PATTERNS = [
    "team", "member", "staff", "person", "employee", "leader",
    "manager", "card", "sotrudnik", "specialist", "expert",
    "contact", "people", "bio",
]


def _find_card_containers(soup: BeautifulSoup) -> list[Tag]:
    containers = []
    for tag in soup.find_all(["div", "li", "article", "section"]):
        classes = " ".join(tag.get("class", [])).lower()
        tag_id = (tag.get("id") or "").lower()
        if any(p in classes or p in tag_id for p in CARD_CLASS_PATTERNS):
            text = tag.get_text(strip=True)
            if 20 < len(text) < 2000:
                containers.append(tag)
    return containers


def _parse_card(card: Tag) -> PersonBlock | None:
    text = card.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    person = PersonBlock(raw_text=text)

    for line in lines:
        if not person.name:
            person.name = _extract_name(line)
        if not person.position and _is_position(line) and line != person.name:
            person.position = line.strip()
        if not person.email:
            person.email = _extract_email(line)
        if not person.phone:
            person.phone = _extract_phone(line)

    img = card.find("img")
    if img and img.get("src"):
        person.photo_url = img["src"]

    if person.name or person.position:
        return person
    return None


# ══════════════════════════════════════════════════════════
#  СТРАТЕГИЯ 3: Структурированные списки (dl, ul с ФИО+должность)
# ══════════════════════════════════════════════════════════

def _parse_definition_lists(soup: BeautifulSoup) -> list[PersonBlock]:
    persons = []
    for dl in soup.find_all('dl'):
        terms = dl.find_all('dt')
        defs = dl.find_all('dd')
        for i, dt in enumerate(terms):
            dt_text = dt.get_text(strip=True)
            dd_text = defs[i].get_text(strip=True) if i < len(defs) else ""
            name = _extract_name(dt_text) or _extract_name(dd_text)
            pos = dt_text if _is_position(dt_text) else (dd_text if _is_position(dd_text) else "")
            if name or pos:
                p = PersonBlock(name=name, position=pos)
                combined = dt_text + " " + dd_text
                p.email = _extract_email(combined)
                p.phone = _extract_phone(combined)
                persons.append(p)
    return persons


# ══════════════════════════════════════════════════════════
#  СТРАТЕГИЯ 4: Сканирование всего текста (fallback)
# ══════════════════════════════════════════════════════════

def _scan_flat_text(soup: BeautifulSoup) -> list[PersonBlock]:
    text = soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    persons = []
    seen = set()
    for i, line in enumerate(lines):
        name = _extract_name(line)
        if name and name not in seen:
            p = PersonBlock(name=name)
            window = "\n".join(lines[max(0,i-1):i+4])
            for wl in lines[max(0,i-1):i+4]:
                if not p.position and _is_position(wl) and wl != line:
                    p.position = wl.strip()
                if not p.email:
                    p.email = _extract_email(wl)
                if not p.phone:
                    p.phone = _extract_phone(wl)
            if p.position or p.email or p.phone:
                seen.add(name)
                persons.append(p)
    return persons


# ══════════════════════════════════════════════════════════
#  ГЛАВНАЯ ФУНКЦИЯ
# ══════════════════════════════════════════════════════════

def extract_person_blocks(html: str) -> list[PersonBlock]:
    soup = BeautifulSoup(html, "lxml")
    persons: list[PersonBlock] = []
    seen_names: set[str] = set()

    # 1. HTML-таблицы (приоритет — самый надёжный источник)
    for table in soup.find_all("table"):
        if _is_contact_table(table):
            table_persons = _parse_contact_table(table)
            for p in table_persons:
                if p.name not in seen_names:
                    seen_names.add(p.name)
                    persons.append(p)
            logger.info("table_parsed", found=len(table_persons))

    # 2. Карточки (div/article)
    if len(persons) < 3:
        for card in _find_card_containers(soup):
            p = _parse_card(card)
            if p and p.name not in seen_names:
                seen_names.add(p.name)
                persons.append(p)

    # 3. Definition lists
    if len(persons) < 3:
        for p in _parse_definition_lists(soup):
            if p.name not in seen_names:
                seen_names.add(p.name)
                persons.append(p)

    # 4. Fallback — плоский текст
    if len(persons) < 2:
        for p in _scan_flat_text(soup):
            if p.name not in seen_names:
                seen_names.add(p.name)
                persons.append(p)

    logger.info("persons_extracted", total=len(persons))
    return persons


def extract_company_info(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    company_name = ""

    og = soup.find("meta", property="og:site_name")
    if og and og.get("content"):
        company_name = og["content"].strip()

    if not company_name:
        title_tag = soup.find("title")
        if title_tag:
            raw = title_tag.get_text(strip=True)
            for sep in ["|", "—", "-", "–", "·", "•", "/"]:
                if sep in raw:
                    company_name = raw.split(sep)[0].strip()
                    break
            if not company_name:
                company_name = raw

    if not company_name:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            company_name = og_title["content"].strip()

    return {"company_name": company_name}
