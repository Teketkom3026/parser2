"""Тесты определителя языка."""

import pytest
from backend.extractor.language_detector import detect_language


class TestDetectLanguage:
    def test_russian(self):
        text = "Компания занимается разработкой программного обеспечения для бизнеса"
        assert detect_language(text) == "ru"

    def test_english(self):
        text = "The company develops software solutions for enterprise business customers"
        assert detect_language(text) == "en"

    def test_too_short(self):
        assert detect_language("Hi") == "unknown"

    def test_empty(self):
        assert detect_language("") == "unknown"

    def test_mixed_mostly_russian(self):
        text = "Компания Google открыла офис в Москве для разработки новых продуктов"
        assert detect_language(text) == "ru"
