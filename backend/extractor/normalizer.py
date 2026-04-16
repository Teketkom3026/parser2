"""Нормализация должностей, классификация ролей, фильтрация по должностям.

Теперь использует position_cleaner.py и name_validator.py как основу.
"""
from rapidfuzz import fuzz, process

from backend.extractor.position_cleaner import (
    normalize_position_text,
    classify_role_by_industry,
    is_valid_position,
)
from backend.extractor.name_validator import is_valid_person_name, split_fio
from backend.utils.logger import get_logger

logger = get_logger("normalizer")


def normalize_position(position: str) -> str:
    """Публичный API: нормализовать должность."""
    return normalize_position_text(position)


def classify_role(position: str) -> str:
    """Публичный API: классифицировать по отрасли."""
    return classify_role_by_industry(position)


def filter_by_positions(persons: list[dict], target_positions: list[str]) -> list[dict]:
    """Фильтровать персон по целевым должностям (Режим 1). Нечёткий поиск."""
    if not target_positions:
        return persons
    targets_lower = [p.lower().strip() for p in target_positions]
    filtered = []
    for person in persons:
        raw_pos = (person.get("position_raw") or "").lower()
        norm_pos = (person.get("position_norm") or "").lower()

        matched = False
        for t in targets_lower:
            if t in raw_pos or t in norm_pos:
                matched = True
                break

        if not matched:
            for t in targets_lower:
                if fuzz.token_sort_ratio(t, raw_pos) >= 75:
                    matched = True
                    break
                if fuzz.token_sort_ratio(t, norm_pos) >= 75:
                    matched = True
                    break

        if matched:
            filtered.append(person)
    return filtered
