"""Нормализация должностей и классификация ролей."""
import json
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz, process
from backend.utils.logger import get_logger

logger = get_logger("normalizer")

# Словарь маппинга должностей → нормализованная форма
POSITION_MAP_RU = {
    "генеральный директор": "Генеральный директор",
    "ген. директор": "Генеральный директор",
    "гендиректор": "Генеральный директор",
    "ген директор": "Генеральный директор",
    "исполнительный директор": "Исполнительный директор",
    "финансовый директор": "Финансовый директор",
    "финдиректор": "Финансовый директор",
    "коммерческий директор": "Коммерческий директор",
    "технический директор": "Технический директор",
    "операционный директор": "Операционный директор",
    "директор по развитию": "Директор по развитию",
    "директор по маркетингу": "Директор по маркетингу",
    "директор по персоналу": "Директор по персоналу",
    "директор по it": "Директор по IT",
    "директор по информационным технологиям": "Директор по IT",
    "главный инженер": "Главный инженер",
    "главный бухгалтер": "Главный бухгалтер",
    "главбух": "Главный бухгалтер",
    "главный юрист": "Главный юрист",
    "председатель правления": "Председатель правления",
    "заместитель генерального директора": "Заместитель генерального директора",
    "зам. генерального директора": "Заместитель генерального директора",
    "управляющий директор": "Управляющий директор",
    "президент": "Президент",
    "вице-президент": "Вице-президент",
    "учредитель": "Учредитель",
    "основатель": "Основатель",
    "собственник": "Собственник",
    "партнёр": "Партнёр",
    "партнер": "Партнёр",
    "начальник отдела": "Начальник отдела",
    "руководитель отдела": "Руководитель отдела",
    "руководитель направления": "Руководитель направления",
    "руководитель проекта": "Руководитель проекта",
    "менеджер проекта": "Руководитель проекта",
}

POSITION_MAP_EN = {
    "ceo": "CEO",
    "chief executive officer": "CEO",
    "cfo": "CFO",
    "chief financial officer": "CFO",
    "cto": "CTO",
    "chief technology officer": "CTO",
    "coo": "COO",
    "chief operating officer": "COO",
    "cmo": "CMO",
    "chief marketing officer": "CMO",
    "cio": "CIO",
    "chief information officer": "CIO",
    "chro": "CHRO",
    "chief human resources officer": "CHRO",
    "managing director": "Managing Director",
    "executive director": "Executive Director",
    "vice president": "Vice President",
    "vp": "Vice President",
    "svp": "Senior Vice President",
    "evp": "Executive Vice President",
    "founder": "Founder",
    "co-founder": "Co-Founder",
    "chairman": "Chairman",
    "president": "President",
    "partner": "Partner",
    "head of": "Head of",
    "director of": "Director of",
    "general manager": "General Manager",
}

POSITION_MAP = {**POSITION_MAP_RU, **POSITION_MAP_EN}

# Классификация ролей
TOP_MANAGEMENT_KEYWORDS = [
    "директор", "президент", "председатель", "вице-президент",
    "управляющий", "основатель", "учредитель", "собственник",
    "партнёр", "партнер", "главный", "член правления",
    "ceo", "cfo", "cto", "coo", "cmo", "cio", "chro", "cpo", "cso", "cdo",
    "founder", "co-founder", "chairman", "president", "vice president",
    "managing director", "executive director", "partner", "svp", "evp", "board member",
]

MIDDLE_MANAGEMENT_KEYWORDS = [
    "начальник", "руководитель", "заведующий", "заместитель директора",
    "head of", "team lead", "department manager", "project manager",
    "senior manager", "group head", "руководитель направления",
]


def normalize_position(position: str) -> str:
    """Нормализовать должность. Прямое совпадение → нечёткий поиск."""
    if not position:
        return ""
    pos_lower = position.lower().strip()

    # Прямое совпадение
    if pos_lower in POSITION_MAP:
        return POSITION_MAP[pos_lower]

    # Нечёткий поиск
    keys = list(POSITION_MAP.keys())
    match = process.extractOne(pos_lower, keys, scorer=fuzz.token_sort_ratio, score_cutoff=80)
    if match:
        return POSITION_MAP[match[0]]

    # Не найдено → возвращаем как есть, первая буква заглавная
    return position.strip().capitalize() if position else ""


def classify_role(position: str) -> str:
    """Классифицировать роль: Топ-менеджмент / Средний менеджмент / Специалист."""
    if not position:
        return "Специалист"
    pos_lower = position.lower()
    for kw in TOP_MANAGEMENT_KEYWORDS:
        if kw in pos_lower:
            return "Топ-менеджмент"
    for kw in MIDDLE_MANAGEMENT_KEYWORDS:
        if kw in pos_lower:
            return "Средний менеджмент"
    return "Специалист"


def filter_by_positions(persons: list[dict], target_positions: list[str]) -> list[dict]:
    """Фильтровать персон по целевым должностям (Режим 1). Нечёткий поиск."""
    if not target_positions:
        return persons
    targets_lower = [p.lower().strip() for p in target_positions]
    filtered = []
    for person in persons:
        raw_pos = (person.get("position_raw") or "").lower()
        norm_pos = (person.get("position_norm") or "").lower()

        # Точное вхождение
        matched = False
        for t in targets_lower:
            if t in raw_pos or t in norm_pos:
                matched = True
                break

        # Нечёткий поиск
        if not matched:
            for t in targets_lower:
                score = fuzz.token_sort_ratio(t, raw_pos)
                if score >= 75:
                    matched = True
                    break
                score = fuzz.token_sort_ratio(t, norm_pos)
                if score >= 75:
                    matched = True
                    break

        if matched:
            filtered.append(person)
    return filtered
