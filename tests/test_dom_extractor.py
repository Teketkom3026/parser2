"""Тесты DOM- извлечения.""" from backend.extractor.dom_extractor import ( extract_person_blocks, extract_company_info, ) def test_extract_person_from_card(): html = """ <div class="team-member">
        <h3> Иванов Иван Иванович</ h3> <p> Генеральный директор</ p> <p>ivanov@company.ru</p> </div> """ persons = extract_person_blocks(html) assert len(persons) >= 1 assert "Иванов" in persons[0].name assert "директор" in persons[0].position.lower() def test_extract_person_from_flat_text(): html = """ <div> <p> Петров Пётр Петрович</ p> <p> Финансовый директор</ p> <p>petrov@company.ru</p> </div> """ persons = extract_person_blocks(html) assert len(persons) >= 1 def test_extract_company_info(): html = '<html><head><title> ООО Ромашка |
Главная</
title></head><body></body></html>'
     info = extract_company_info(html) assert "Ромашка" in info["company_name"] def test_extract_company_from_og(): html = '<html><head><meta property="og:site_name" content=" Компания
Тест"></
head><body></body></html>'
     info = extract_company_info(html) assert "Тест" in info["company_name"]