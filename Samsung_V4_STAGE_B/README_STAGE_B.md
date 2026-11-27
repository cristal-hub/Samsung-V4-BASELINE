# README_STAGE_B.md
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE B
## Изолированное состояние стратегии по ключу (strategy_id, FIGI)

Пакет: `Samsung_V4_STAGE_B` (полная копия принятой Stage A.2.1 +
добавления Stage B). Baseline: commit
`884cefd6f12a99f6adc14b5ed4c9eeda21d32e04`.
Принятая реализация Stage A.2.1: commit
`103d22d34d483fbb7179d1fef07dd0e24b51dfcd` — использована БЕЗ изменений.

## Что это

Stage B: независимое состояние каждой стратегии для каждого инструмента
с ключом изоляции **(strategy_id, FIGI)**. Реализованы компоненты:

1. **`StrategyState`** (§3.1 ТЗ) — неизменяемая модель состояния пары:
   привязка к strategy_id, FIGI, config_hash (формат Stage A.2 —
   SHA-256/64 hex); версия схемы состояния (`STATE_SCHEMA_VERSION = 1`);
   типизированные данные (глубоко неизменяемое ImmutableMapping поверх
   проверенных JSON-совместимых значений); контролируемая
   детерминированная сериализация (`to_payload`/`to_json`/`from_payload`);
   отсутствие общих изменяемых объектов между разными ключами.

2. **`StateStore`** (§3.2 ТЗ) — хранилище: `get_state`, `save_state`,
   `create_state`, `reset_state`, `list_states`. Persistent-режим —
   ТОЛЬКО с явно переданным путём (по одной JSON-записи на ключ,
   атомарная запись, детерминированное содержимое); memory-режим — явный.
   Хранилище проверяет версию схемы, соответствие ключей и config_hash,
   обнаруживает повреждённые записи (не подменяя их пустым состоянием);
   несовпадение config_hash даёт контролируемую ошибку
   `StateConfigMismatchError` — старое состояние НЕ переносится на новую
   конфигурацию автоматически, требуется ЯВНОЕ решение (reset/совместимость).

3. **`StrategyStateManager`** (§3.3 ТЗ) — выдаёт стратегии только её
   собственное состояние; создаёт независимое состояние при отсутствии
   записи; сохраняет изменения; исключает перекрёстное загрязнение;
   корректен при параллельных обращениях; не использует глобальный
   mutable context; не хранит одно состояние на все инструменты.

4. **`resolve_state_store_path`** — путь persistent-хранилища берётся
   ТОЛЬКО из явного ключа `STATE_STORE_PATH` переданной конфигурации;
   отсутствие обязательной конфигурации не приводит к скрытому переходу
   на другой путь (fail-closed); скрытых путей не придумано, старые
   файлы Samsung не используются.

## Ключевые гарантии (завершение Stage B)

* изоляция по (strategy_id, FIGI) — на уровне модели, имён записей и API
  (обращение без обоих компонентов ключа невозможно);
* состояние восстанавливается после перезапуска из сохранённых данных
  (детерминированная сериализация, одинаковые байты);
* fail-closed при несовместимых данных: повреждённая запись,
  неизвестная версия схемы, несовпадающий config_hash — контролируемые
  ошибки, никаких тихих сбросов и подмен пустым состоянием;
* параллельные операции без перекрёстного загрязнения (RLock хранилища
  и менеджера; гонки get/create обработаны; тесты 8–16 потоков);
* интеграция с контрактами Stage A: config — ТОЛЬКО точный тип
  `StrategyConfig` (решение Stage A.2.1), `AttributionContext` — ТОЛЬКО
  проверенный (через `attribution._resolve_context`); `config_hash`
  Stage A не изменился; атрибуция осталась корректной;
* legacy Samsung V4 остаётся `REGRESSION_ONLY`;
* все 1113 тестов Stage A.2.1 проходят без изменений и ослаблений +
  115 новых тестов Stage B: суммарно **1228 passed, 0 failed, 0 skipped**
  (полный набор); канонический поднабор: 593 → **708 passed**;
* golden fixtures не перегенерировались; профили SANDBOX_TEST /
  TECH_CHECK / CONSERVATIVE не менялись; FORCE_TRADE не добавлялся и не
  использовался; Stage C не начат (evaluate_exit не реализован).

## Документы пакета (Stage B)

* `STAGE_B_ARCHITECTURE_REPORT.md` — полный отчёт по архитектуре
  (решения, гарантии, трассировка 16 обязательных сценариев ТЗ);
* `CHANGED_FILES_STAGE_B.md` — отчёт об изменённых файлах (только
  добавления; подтверждение неизменности запрещённых областей);
* `DIFF_STAGE_A_2_1_VS_STAGE_B.patch` / `.md` — полный diff A.2.1 → B;
* `TEST_RESULTS_STAGE_B.txt` — полные логи pytest ДО и ПОСЛЕ;
* `FILE_MANIFEST_SHA256_STAGE_B.txt` — SHA256-манифест (171 неизменный
  файл побайтово, контроль запрещённых областей);
* `VERIFICATION_INSTRUCTIONS_STAGE_B.md` — инструкции проверки;
* `ROLLBACK_INSTRUCTIONS_STAGE_B.md` — откат к Stage A.2.1;
* `KNOWN_LIMITATIONS_STAGE_B.md` — известные ограничения;
* `CHANGELOG.md` — дополнен разделом Stage B.

## Быстрая проверка

```bash
cd candidate
python -m pytest              # полный набор: 1228 passed
python -m pytest tests        # канонический поднабор: 708 passed
python -m pytest tests/test_stage_b_state_isolation.py   # 115 passed
```

Демонстрация изоляции (offline):

```python
import tempfile
from strategy_api import StrategyConfig, compute_config_hash
from strategy_state import StateStore, StrategyStateManager

def cfg(sid, length):
    params = {"length": length}
    return StrategyConfig(strategy_id=sid, strategy_version="v1",
                          params=params,
                          config_hash=compute_config_hash(sid, "v1", params))

with tempfile.TemporaryDirectory() as tmp:
    mgr = StrategyStateManager(StateStore(path=tmp))
    mgr.get_state("s_a", "FIGI_X", config=cfg("s_a", 14))   # создаёт
    mgr.get_state("s_b", "FIGI_X", config=cfg("s_b", 21))   # независимое
    mgr.update_state("s_a", "FIGI_X", config=cfg("s_a", 14),
                     data={"streak": 3})
    assert mgr.get_state("s_b", "FIGI_X",
                         config=cfg("s_b", 21)).data == {}  # не затронуто
    mgr2 = StrategyStateManager(StateStore(path=tmp))       # «перезапуск»
    assert mgr2.get_state("s_a", "FIGI_X",
                          config=cfg("s_a", 14)).data["streak"] == 3
```

## Режим работы

OFFLINE / READ ONLY DATA / RESEARCH ONLY / NO LIVE ORDERS / NO REAL MONEY.
Сетевых обращений, брокерских подключений, Sandbox/LIVE-заявок не было.
GitHub не использовался; ветки/коммиты/PR/issue не создавались; файлы
в пользовательские папки не записывались.
