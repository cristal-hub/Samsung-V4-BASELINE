# STAGE_C_PRE_IMPLEMENTATION_BASELINE.md
# SAMSUNG V4 — STAGE C — ФИКСАЦИЯ СОСТОЯНИЯ ДО РЕАЛИЗАЦИИ (ТЗ §7)

Дата фиксации: 2026-11-28 (до любых изменений Stage C).
База: принятый пакет Stage B.1, commit
`e413c5bd6bdec436ffd7aeece4c28b5e969c6306`, распакованный в
изолированную рабочую копию Stage C.

## 1. Полный перечень файлов Stage B.1 (ТЗ §7, п. 1)

Файл: `STAGE_C_PRE_BASELINE_FILES.txt` — 223 файла принятого пакета
(корневые отчёты, archive/, docs/, candidate/), реальный список на
момент распаковки принятого ZIP, до начала работ.

## 2. SHA256 исходных файлов (ТЗ §7, п. 2)

Файл: `STAGE_C_PRE_BASELINE_SHA256.txt` — SHA256 всех 174 файлов
`candidate/` (исходники, тесты, fixtures, appendix). Вычислены до
любых изменений; сверка ПОСЛЕ реализации показала: все 174 файла
побайтово неизменны (STAGE_C_IMMUTABILITY_PROOF.txt).

Ключевые контрольные хеши ДО (совпадают ПОСЛЕ):

| Файл | SHA256 (начало) |
|---|---|
| candidate/strategy_api.py | (см. STAGE_C_PRE_BASELINE_SHA256.txt) |
| candidate/attribution.py | (см. STAGE_C_PRE_BASELINE_SHA256.txt) |
| candidate/strategy_state.py | (см. STAGE_C_PRE_BASELINE_SHA256.txt) |
| candidate/tests/fixtures/legacy_golden_signals.json | (см. там же) |

## 3. Точный список планируемых изменений (ТЗ §7, п. 3)

ЗАЯВЛЕННЫЙ ПЛАН (зафиксирован ДО реализации):

* ДОБАВИТЬ `candidate/strategy_contracts.py` — контрактный слой
  Stage C (Entry/Exit контракты, price gate, merge, координатор);
* ДОБАВИТЬ `candidate/tests/test_stage_c_contracts.py` — тесты
  контрактов (ТЗ §6.1–§6.8, §6.14);
* ДОБАВИТЬ `candidate/tests/test_stage_c_exit_service.py` — тесты
  координатора и интеграции состояния (ТЗ §6.9–§6.17);
* ДОБАВИТЬ отчётные/diff/manifest/log-файлы Stage C в корень пакета и
  `appendix_stage_c/`;
* НЕ ИЗМЕНЯТЬ ни одного существующего файла;
* НЕ УДАЛЯТЬ ни одного файла, теста или проверки;
* НЕ перегенерировать golden fixtures;
* НЕ менять Stage A.2.1, Stage B.1, legacy_samsung_v4,
  baseline-файлы торговли.

ФАКТ ПОСЛЕ РЕАЛИЗАЦИИ: план выполнен ТОЧНО — изменённых файлов 0,
добавленных исходных 3 (см. CHANGED_FILES_STAGE_C.md,
STAGE_C_IMMUTABILITY_PROOF.txt).

## 4. Прогон «ДО» на этой же копии (реальные логи)

* полный набор: 1261 passed (appendix_stage_c/pytest_before_full.log);
* канонический набор: 741 passed
  (appendix_stage_c/pytest_before_canonical.log).
