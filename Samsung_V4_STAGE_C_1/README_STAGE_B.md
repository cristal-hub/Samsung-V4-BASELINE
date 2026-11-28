# README_STAGE_B.md
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE B + КОРРЕКЦИЯ B.1
## Изолированное состояние стратегии по ключу (strategy_id, FIGI)

Пакет: `Samsung_V4_STAGE_B` (полная копия принятой Stage A.2.1 +
добавления Stage B + корректирующие исправления Stage B.1).
Baseline: commit `884cefd6f12a99f6adc14b5ed4c9eeda21d32e04`.
Принятая реализация Stage A.2.1: commit
`103d22d34d483fbb7179d1fef07dd0e24b51dfcd` — использована БЕЗ изменений.
Полный пакет Stage B НЕ перезаписан с нуля — точечные исправления
дефектов №1–№3 изоляции состояния (ТЗ Stage B.1).

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

## Исправления Stage B.1 (дефекты изоляции и конкурентного обновления)

1. **Дефект №1 — коллизия имён файлов.** Прежний шаблон
   `f"{strategy_id}__{figi}.json"` не был инъективным: пары
   `("alpha__beta","FIGI1")` и `("alpha","beta__FIGI1")` давали одно имя
   файла и перезаписывали состояние друг друга. Теперь имя записи —
   инъективное длинно-префиксное кодирование
   `{len(s1)}--{s1}--{len(s2)}--{s2}.json`
   (`encode_state_filename`/`decode_state_filename`); разбор строго
   позиционный, инъективность доказуема для всех допустимых значений.
   Скрытой миграции старого формата нет; старые имена обнаруживаются как
   повреждение (`list_states` → `StateCorruptionError`).
2. **Дефект №2 — проверка ключа после чтения.** `StateStore._load`
   после десериализации ОБЯЗАТЕЛЬНО сверяет `state.strategy_id` и
   `state.figi` с запрошенными; несовпадение — `StateCorruptionError`:
   состояние не возвращается, пустым не подменяется, файл не изменяется.
   Проверка выполняется и в memory-режиме (единый контракт).
3. **Дефект №3 — конкурентное обновление.** Атомарный read-modify-write
   вынесен в `StateStore.update_state`/`StateStore.get_or_create`:
   чтение + updater + запись под ОДНИМ RLock хранилища — атомарно
   относительно ВСЕХ менеджеров, разделяющих один StateStore.
   Дополнительно все экземпляры StateStore одного процесса на одном
   реальном каталоге разделяют один RLock (реестр по realpath).
   Граница гарантии: ОДИН процесс; межпроцессная блокировка не
   поддерживается (честно зафиксировано в KNOWN_LIMITATIONS_STAGE_B.md).
   Локальный RLock менеджера больше НЕ является механизмом атомарности.

## Ключевые гарантии (завершение Stage B)

* изоляция по (strategy_id, FIGI) — на уровне модели, имён записей и API
  (обращение без обоих компонентов ключа невозможно);
* состояние восстанавливается после перезапуска из сохранённых данных
  (детерминированная сериализация, одинаковые байты);
* fail-closed при несовместимых данных: повреждённая запись,
  неизвестная версия схемы, несовпадающий config_hash — контролируемые
  ошибки, никаких тихих сбросов и подмен пустым состоянием;
* параллельные операции без перекрёстного загрязнения; атомарный
  read-modify-write для всех менеджеров одного хранилища (Stage B.1);
  тесты 8–16 потоков, две менеджера × один store, детерминированный
  итог повторов;
* интеграция с контрактами Stage A: config — ТОЛЬКО точный тип
  `StrategyConfig` (решение Stage A.2.1), `AttributionContext` — ТОЛЬКО
  проверенный (через `attribution._resolve_context`); `config_hash`
  Stage A не изменился; атрибуция осталась корректной;
* legacy Samsung V4 остаётся `REGRESSION_ONLY`;
* все тесты Stage A.2.1 проходят без изменений и ослаблений + 115
  тестов Stage B + 33 новых теста Stage B.1: суммарно
  **1261 passed, 0 failed, 0 skipped** (полный набор);
  канонический поднабор: 708 → **741 passed**;
  до Stage B.1 (Stage B): 1228 / 708;
* golden fixtures не перегенерировались; профили SANDBOX_TEST /
  TECH_CHECK / CONSERVATIVE не менялись; FORCE_TRADE не добавлялся и не
  использовался; Stage C не начат (evaluate_exit не реализован).

## Документы пакета (актуальные для Stage B.1)

Канонические документы в корне пакета (ТЗ Stage B.1 §7):

* `IMPLEMENTATION_REPORT_STAGE_B.md` — отчёт о реализации Stage B+B.1;
* `TEST_RESULTS_STAGE_B.txt` — полные реальные логи pytest ДО/ПОСЛЕ
  (до B.1: 1228/708; после B.1: 1261/741);
* `STAGE_B_ARCHITECTURE_REPORT.md` — архитектура Stage B (разделы 1–9)
  и исправлений B.1 (разделы 10–13);
* `CHANGED_FILES_STAGE_B.md` — отчёт об изменённых файлах;
* `KNOWN_LIMITATIONS_STAGE_B.md` — известные ограничения (включая
  границы гарантии конкурентности и отсутствие миграции старого формата);
* `README_STAGE_B.md` — этот файл;
* `FILE_MANIFEST_SHA256_STAGE_B.txt` — SHA256-манифест всего пакета;
* `DIFF_STAGE_B_VS_B_1.md` — полный diff Stage B → Stage B.1;
* `ROLLBACK_INSTRUCTIONS_STAGE_B_1.md` — откат Stage B.1 → Stage B;
* `VERIFICATION_INSTRUCTIONS_STAGE_B.md` — инструкции проверки.

Отчёты Stage A/A.1/A.2/A.2.1 перенесены в `archive/` с явной пометкой
«неактуально для Stage B.1» (`archive/ARCHIVE_README.md`) — они НЕ
являются отчётами Stage B.

## Быстрая проверка

```bash
cd candidate
python -m pytest              # полный набор: 1261 passed
python -m pytest tests        # канонический поднабор: 741 passed
python -m pytest tests/test_stage_b_state_isolation.py   # 115 passed (Stage B)
python -m pytest tests/test_stage_b1_state_key_and_concurrency.py  # 33 passed (B.1)
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
