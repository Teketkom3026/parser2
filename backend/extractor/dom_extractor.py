"""DOM-анализ: HTML-таблицы, карточки, плоский текст."""
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from backend.extractor.name_validator import is_valid_person_name
from backend.extractor.position_cleaner import clean_position_raw, is_valid_position
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


# ── Regex ──────────────────────────────────────────────────────────────────────
FIO_RU = re.compile(
    r'\b([А-ЯЁ][а-яё]{1,30})\s+([А-ЯЁ][а-яё]{1,20})\s+([А-ЯЁ][а-яё]{1,20})\b'
)
FIO_RU_INITIALS = re.compile(
    r'\b([А-ЯЁ][а-яё]{1,30})\s+([А-ЯЁ])\.?\s*([А-ЯЁ])\.\b'
)
FIO_EN = re.compile(
    r'\b([A-Z][a-z]{1,25})\s+(?:[A-Z][a-z]{1,25}\s+)?([A-Z][a-z]{1,25})\b'
)
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
PHONE_RE = re.compile(
    r'(?:\+7|8|7)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
    r'(?:\s*(?:доб\.?|ext\.?|#)\s*\d{1,6})?'
)


def _extract_name(text: str) -> str:
    m = FIO_RU.search(text)
    if m and is_valid_person_name(m.group(0)):
        return m.group(0).strip()
    m = FIO_RU_INITIALS.search(text)
    if m and is_valid_person_name(m.group(0)):
        return m.group(0).strip()
    m = FIO_EN.search(text)
    if m and is_valid_person_name(m.group(0)):
        full = m.group(0).strip()
        if len(full.split()) >= 2:
            return full
    return ""


def _extract_email(text: str) -> str:
    m = EMAIL_RE.search(text)
    if m:
        e = m.group(0).lower().strip(".")
        if not any(e.endswith(x) for x in ('.png', '.jpg', '.css', '.js')):
            return e
    return ""


def _extract_phone(text: str) -> str:
    m = PHONE_RE.search(text)
    return m.group(0).strip() if m else ""


# ══════════════════════════════════════════════════════════════════════════════
#  СТРАТЕГИЯ 1: HTML-таблицы
# ══════════════════════════════════════════════════════════════════════════════

def _is_contact_table(table: Tag) -> bool:
    text = table.get_text(separator=" ", strip=True).lower()
    has_email = '@' in text or 'email' in text or 'почта' in text
    has_phone = bool(re.search(r'\+7|\(8\d{2}\)|тел|тел\.', text))
    has_position = is_valid_position(text)
    has_name = bool(FIO_RU.search(table.get_text()))
    return (has_email or has_phone) and (has_position or has_name)


def _parse_contact_table(table: Tag) -> list[PersonBlock]:
    persons = []
    for row in table.find_all('tr'):
        cells = row.find_all(['td', 'th'])
        if len(cells) < 2:
            continue
        cell_texts = [c.get_text(separator=" ", strip=True) for c in cells]
        combined = " | ".join(cell_texts)
        person = PersonBlock(raw_text=combined)

        for ct in cell_texts:
            if not person.name:
                person.name = _extract_name(ct)
            if not person.position:
                cleaned_pos = clean_position_raw(ct)
                if cleaned_pos and is_valid_position(cleaned_pos) and ct != person.name:
                    person.position = cleaned_pos
            if not person.email:
                person.email = _extract_email(ct)
            if not person.phone:
                person.phone = _extract_phone(ct)

        # Паттерн: первая ячейка — должность, вторая — ФИО
        if not person.position and len(cell_texts) >= 1:
            cleaned = clean_position_raw(cell_texts[0])
            if cleaned and is_valid_position(cleaned):
                person.position = cleaned
        if not person.name and len(cell_texts) >= 2:
            person.name = _extract_name(cell_texts[1])

        if person.name or (person.position and (person.email or person.phone)):
            persons.append(person)
    return persons


# ══════════════════════════════════════════════════════════════════════════════
#  СТРАТЕГИЯ 2: карточки div/article
# ══════════════════════════════════════════════════════════════════════════════

CARD_CLASS_PATTERNS = [
    "team", "member", "staff", "person", "employee", "leader",
    "manager", "card", "sotrudnik", "specialist", "expert",
    "contact", "people", "bio",
]


def _find_cards(soup: BeautifulSoup) -> list[Tag]:
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
        if not person.position:
            cleaned = clean_position_raw(line)
            if cleaned and is_valid_position(cleaned) and line != person.name:
                person.position = cleaned
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


# ══════════════════════════════════════════════════════════════════════════════
#  СТРАТЕГИЯ 3: плоский текст (fallback)
# ══════════════════════════════════════════════════════════════════════════════

def _scan_flat(soup: BeautifulSoup) -> list[PersonBlock]:
    text = soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    persons = []
    seen = set()
    for i, line in enumerate(lines):
        name = _extract_name(line)
        if name and name not in seen:
            p = PersonBlock(name=name)
            for wl in lines[max(0, i - 1): i + 4]:
                cleaned = clean_position_raw(wl)
                if not p.position and cleaned and is_valid_position(cleaned) and wl != line:
                    p.position = cleaned
                if not p.email:
                    p.email = _extract_email(wl)
                if not p.phone:
                    p.phone = _extract_phone(wl)
            if p.position or p.email or p.phone:
                seen.add(name)
                persons.append(p)
    return persons


# ══════════════════════════════════════════════════════════════════════════════
#  ГЛАВНАЯ ФУНКЦИЯ
# ══════════════════════════════════════════════════════════════════════════════

def extract_person_blocks(html: str) -> list[PersonBlock]:
    soup = BeautifulSoup(html, "lxml")
    persons: list[PersonBlock] = []
    seen_names: set[str] = set()

    # 1. Таблицы
    for table in soup.find_all("table"):
        if _is_contact_table(table):
            for p in _parse_contact_table(table):
                if p.name not in seen_names:
                    seen_names.add(p.name)
                    persons.append(p)

    # 2. Карточки
    if len(persons) < 3:
        for card in _find_cards(soup):
            p = _parse_card(card)
            if p and p.name not in seen_names:
                seen_names.add(p.name)
                persons.append(p)

    # 3. Fallback
    if len(persons) < 2:
        for p in _scan_flat(soup):
            if p.name not in seen_names:
                seen_names.add(p.name)
                persons.append(p)

    logger.info("persons_extracted", total=len(persons))
    return persons


def extract_company_info(html: str) -> dict:
    from backend.extractor.company_name_cleaner import clean_company_name
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

    # Очистка
    return {"company_name": clean_company_name(company_name)}
