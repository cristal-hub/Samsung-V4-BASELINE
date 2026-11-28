# README_STAGE_A_1.md
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.1 (CORRECTIVE PACKAGE)

Исправление трёх замечаний независимого аудита Stage A:
1. **Замечание №1** — StrategyConfig теперь ДЕЙСТВИТЕЛЬНО immutable, включая
   вложенные структуры; config_hash всегда соответствует фактической
   конфигурации.
2. **Замечание №2** — атрибуция нового движка оформлена как единый явный
   интерфейс (AttributionContext → AttributionFactory) для всех типов новых
   объектов (события, виртуальные ордера, виртуальные позиции, строки
   исследовательского CSV/JSONL); старые production-механизмы Samsung V4
   не изменялись; граница Этапа A задокументирована честно.
3. **Замечание №3** — глобальный контекст атрибуции УДАЛЕН
   (set_current_context/get_current_context/clear_current_context не
   существуют); только явное внедрение зависимости; изоляция при параллельной
   работе доказана тестами (в т.ч. потоками).

**Тесты:** 980 passed / 0 failed / 0 skipped = 771 baseline + 128 Stage A +
81 corrective (48 неизменяемость + 33 явная атрибуция). Новых регрессий нет.
**Ограничения:** STRATEGY LOGIC: UNCHANGED. RESEARCH ONLY. NO LIVE ORDERS.
NO BROKER EXECUTION. NO SANDBOX EXECUTION. Stage B–H не начинались.

## СТРУКТУРА ПАКЕТА

```
Samsung_V4_STAGE_A_1/
├── README_STAGE_A_1.md                 ← этот файл
├── CORRECTIVE_IMPLEMENTATION_REPORT.md ← главный отчёт Stage A.1
├── BASELINE_VS_STAGE_A_1_DIFF.md       ← diff относительно исходного Stage A
│                                         (причины/содержание/совместимость/тесты)
├── APPENDIX_FULL_DIFF.patch            ← полный машинный diff (2113 строк)
├── TEST_RESULTS.txt                    ← полный протокол тестирования Stage A.1
├── FILE_MANIFEST_SHA256.txt            ← SHA256 всех файлов пакета Stage A.1
├── ROLLBACK_INSTRUCTIONS.md            ← откат Stage A.1 → Stage A → baseline
├── TEST_RESULTS_STAGE_A.txt            ← протокол Stage A (сохранён для сверки)
├── ROLLBACK_INSTRUCTIONS_STAGE_A.md    ← откат Stage A (сохранён для сверки)
├── FILE_MANIFEST_SHA256_STAGE_A.txt    ← манифест Stage A (сохранён для сверки)
├── README_STAGE_A.md, IMPLEMENTATION_REPORT.md, CHANGELOG.md,
│   BASELINE_VS_CANDIDATE.md            ← отчёты Stage A (без изменений)
├── candidate/                          ← ПОЛНЫЙ исправленный пакет движка
│   ├── strategy_api.py                 ← [ИЗМЕНЁН, замечание №1]
│   ├── attribution.py                  ← [ИЗМЕНЁН, замечания №2/№3]
│   ├── engine_config.py                ← [ИЗМЕНЁН, единый механизм контекста]
│   ├── tests/test_stage_a_attribution.py      ← [ИЗМЕНЁН, адаптация к DI]
│   ├── tests/test_stage_a1_config_immutability.py      ← [НОВЫЙ, 48 тестов]
│   ├── tests/test_stage_a1_attribution_explicit.py     ← [НОВЫЙ, 33 теста]
│   ├── tests/test_stage_a_*.py         ← Stage A тесты (128, эталоны не менялись)
│   ├── strategies/legacy_samsung_v4/   ← regression-адаптер (без изменений)
│   ├── engine.json                     ← UNCONFIGURED (без изменений)
│   └── ... (все прочие файлы Stage A — байт-неизменны)
└── docs/                               ← документация Stage A (без изменений)
```

## КАК ПРОВЕРИТЬ

```
cd candidate
python -m pytest           # 980 passed (полный набор)
python -m pytest tests     # 460 passed (канонический поднабор)
python -m pytest tests/test_stage_a1_config_immutability.py \
         tests/test_stage_a1_attribution_explicit.py    # corrective: 81 passed
```

Требуемое окружение — то же, что у Stage A: Python 3.12, pytest 9.x,
pandas 2.2.x, numpy 2.1.x, pandas-ta-classic>=0.3.14b, python-dotenv,
python-telegram-bot>=20,<22; при отсутствии t-tech-investments работает
штатная заглушка tests/conftest.py. Все прогоны offline.

## ЧТО ДАЛЬШЕ (после независимой проверки результата)

* Stage B НЕ начинался (по ТЗ). Подключение атрибуции к компонентам нового
  движка и расширение TRADE_FIELDS логгера — Этап B
  (см. CORRECTIVE_IMPLEMENTATION_REPORT.md п. 3.3).
* Откат: ROLLBACK_INSTRUCTIONS.md (исходный пакет Stage A сохраняется).
