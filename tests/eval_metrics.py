"""Скрипт автоматического замера Precision/Recall по Gold Standard. Использование: python -m tests.eval_metrics --result result.xlsx --gold tests/fixtures/gold_standard.xlsx """ import argparse import sys import openpyxl from rapidfuzz import fuzz def load_excel(path: str) -> list[dict]: wb = openpyxl.load_workbook(path, read_only=True) ws = wb.active headers = [str(cell.value or "").strip() for cell in next(ws.iter_rows(min_row=1,
max_row=1))]
     rows = [] for row in ws.iter_rows(min_row=2, values_only=True): d = {headers[i]: (str(row[i]).strip() if row[i] else "") for i in range(len(headers))} rows.append(d) wb.close() return rows def match_contact(result: dict, gold: dict) -> bool: """Проверить, совпадает ли контакт. TP если ≥2 поля совпадают.""" matches = 0 # ФИО: ≥2 из 3 компонентов r_name = (result.get(" ФИО сотрудника") or "").lower() g_name = (gold.get(" ФИО сотрудника") or gold.get("person_name") or "").lower() if r_name and g_name: score = fuzz.token_sort_ratio(r_name, g_name) if score >= 70: matches += 1 # Должность r_pos = (result.get(" Должность (нормализованная)") or "").lower() g_pos = (gold.get(" Должность (нормализованная)") or gold.get("position_norm") or
"").lower()
     if r_pos and g_pos: score = fuzz.token_sort_ratio(r_pos, g_pos) if score >= 75: matches += 1
     # Email r_email = (result.get(" Личный email") or "").lower() g_email = (gold.get(" Личный email") or gold.get("person_email") or "").lower() if r_email and g_email and r_email == g_email: matches += 1 return matches >= 2 def evaluate(result_path: str, gold_path: str) -> dict: results = load_excel(result_path) golds = load_excel(gold_path) tp = 0 fp = 0 fn = 0 matched_golds = set() for r in results: found = False for i, g in enumerate(golds): if i in matched_golds: continue r_site = (r.get(" Сайт (домен)") or "").lower() g_site = (g.get(" Сайт (домен)") or g.get("site_url") or "").lower() if r_site and g_site and (r_site in g_site or g_site in r_site): if match_contact(r, g): tp += 1 matched_golds.add(i) found = True break if not found: fp += 1 fn = len(golds) - len(matched_golds) precision = tp / (tp + fp) if (tp + fp) > 0 else 0 recall = tp / (tp + fn) if (tp + fn) > 0 else 0 f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0 fp_rate = fp / (tp + fp) if (tp + fp) > 0 else 0 return { "TP": tp, "FP": fp, "FN": fn, "Precision": round(precision * 100, 1), "Recall": round(recall * 100, 1), "F1": round(f1 * 100, 1),
        "FP_Rate": round(fp_rate * 100, 1), "Total_Results": len(results), "Total_Gold": len(golds), } if __name__ == "__main__": parser = argparse.ArgumentParser(description=" Замер метрик качества парсера") parser.add_argument("--result", required=True, help=" Путь к результату парсера (.xlsx)") parser.add_argument("--gold", required=True, help=" Путь к Gold Standard (.xlsx)") args = parser.parse_args() metrics = evaluate(args.result, args.gold) print("\n" + "=" * 50) print(" ОТЧЁТ О МЕТРИКАХ КАЧЕСТВА") print("=" * 50) for k, v in metrics.items(): print(f" {k:20s}: {v}") print("=" * 50) target_ok = metrics["Precision"] >= 80.0 and metrics["Recall"] >= 70.0 and
metrics["FP_Rate"]

<=

20.0
     print(f"\n Целевые метрики: {' ✅ ПРОЙДЕНЫ' if target_ok else ' ❌ НЕ ПРОЙДЕНЫ'}") print(f" Precision ≥ 80%: {metrics['Precision']}% {' ✅ ' if metrics['Precision'] >= 80 else
'
❌
'}")
     print(f" Recall ≥ 70%: {metrics['Recall']}% {' ✅ ' if metrics['Recall'] >= 70 else ' ❌ '}") print(f" FP Rate ≤ 20%: {metrics['FP_Rate']}% {' ✅ ' if metrics['FP_Rate'] <= 20 else
'
❌
'}")
      sys.exit(0 if target_ok else 1)