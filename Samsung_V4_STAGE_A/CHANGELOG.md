# CHANGELOG.md
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A
# (baseline: commit 884cefd6f12a99f6adc14b5ed4c9eeda21d32e04)

Формат: только фактические изменения относительно baseline. Ни один
существующий файл baseline не изменён и не удалён (доказательство побайтовой
идентичности — BASELINE_VS_CANDIDATE.md, FILE_MANIFEST_SHA256.txt).

## Added — архитектура нового движка (candidate/)

- `engine.json` — конфигурация движка рядом с runtime.env (.env):
  `ACTIVE_STRATEGY: null` (явное UNCONFIGURED), `ENGINE_SCHEMA_VERSION: 1`,
  ключи-комментарии. Торговый режим заблокирован; offline-тесты разрешены.
- `strategy_api.py` — единый контракт стратегии: `Strategy` (strategy_id,
  версия, описание параметров `ParamSpec`, валидация, нормализация,
  `get_config` → `StrategyConfig` с config_hash, `evaluate_entry` → `Signal`);
  `ActivationMode` с fail-closed умолчанием REGRESSION_ONLY;
  `compute_config_hash` (SHA-256 по каноническому JSON; секреты/время/пути
  не участвуют); общие валидаторы параметров (типы, NaN/Infinity, диапазоны,
  без скрытых fallback).
- `engine_config.py` — загрузка/объединение/проверка конфигурации движка:
  приоритет env ACTIVE_STRATEGY → engine.json → UNCONFIGURED;
  статусы UNCONFIGURED / CONFIGURED / CONFIG_ERROR (fail-closed: битый JSON,
  не-объект, нестроковое значение, неизвестная стратегия, regression-only
  стратегия); `require_trading_ready()` — шлюз торгового режима;
  предупреждения для неизвестных ключей engine.json.
- `attribution.py` — атрибуция новых объектов: `AttributionContext`
  (strategy_id, config_hash), явный текущий контекст, `stamp()` (fail-closed
  без фиктивных значений), `legacy_attribution_view()` (старые записи —
  явные None, без выдуманных значений), `append_attributed_csv_row()` для
  НОВЫХ журналов движка (атрибут-поля в конец шапки), `TRADE_ATTRIBUTION_FIELDS`
  — зарезервированное предложение для Этапа B.
- `strategies/__init__.py` — пространство стратегий и ЯВНЫЙ реестр:
  `register_strategy` (уникальность, согласованность activatable/
  regression_only с activation_mode), `known_strategy_ids`,
  `activatable_strategy_ids` (на Этапе A всегда пуст), без автосканирования
  и автовыбора.

## Added — изолированный regression-адаптер старой стратегии
## (candidate/strategies/legacy_samsung_v4/)

- `__init__.py` — явная регистрация в реестре строго как regression-only
  (`activatable=False`), исторический эталон, не стратегия торгового режима.
- `strategy.py` — `LegacySamsungV4Strategy`: мост к ОРИГИНАЛЬНОЙ логике
  baseline `strategy.py` (без копирования/изменения); единственный легальный
  путь — `build_regression_config(profile_name)` (origin=«regression_harness»);
  временная установка параметров в модуль config с гарантированным
  восстановлением; ленивые импорты; запрет origin=«engine»; отказ от
  silent defaults.
- `params.json` — исторические базовые параметры (дословно из baseline
  config.py) + описание источника; параметры риск-менеджмента сознательно
  не включены (Этап D).
- `profiles.py` — исторические профили SANDBOX_TEST / TECH_CHECK /
  CONSERVATIVE с неизменёнными значениями; FORCE_TRADE сознательно
  отсутствует; ни один профиль не активен по умолчанию.
- `schema.py` — структурные спецификации 14 параметров, fail-closed
  валидация (типы, NaN/Infinity, домены), семантика RSI: равные пороги
  допустимы (строгие сравнения < и >), инвертированные — ошибка;
  MIN_CANDLES_FOR_SIGNAL и TREND_FILTER_MA_PERIOD сознательно не связаны.

## Added — тесты (candidate/tests/)

- `test_stage_a_strategy_api.py` (22) — контракт и config_hash:
  детерминированность, независимость от порядка ключей, чувствительность
  к изменениям, отказ NaN/Infinity/недетерминируемых типов, каноническая
  форма payload, умолчание REGRESSION_ONLY, отказ silent defaults.
- `test_stage_a_engine_config.py` (24) — N-01…N-04, приоритет env над JSON,
  пустые/некорректные/неизвестные значения, fail-closed битого engine.json,
  UNCONFIGURED поставляемого engine.json, детерминизм загрузки.
- `test_stage_a_schema.py` (18) — T-16 (равные/инвертированные RSI-пороги),
  T-17 (валидность конфигурации ≠ готовность данных; HOLD «Недостаточно
  данных» при короткой истории), структурные проверки, нормализация типов.
- `test_stage_a_legacy_profiles.py` (11) — G-5: идентичность профилей и
  базовых параметров baseline (AST-сверка, baseline только читается),
  отсутствие FORCE_TRADE в новой архитектуре, отсутствие профиля по
  умолчанию.
- `test_stage_a_legacy_adapter.py` (31) — G-1: golden signals
  (5 fixture × 3 профиля, sha256-контроль fixture), идентичность моста
  (адаптер == прямой вызов baseline), изоляция baseline-состояния
  (включая PROFILE="FORCE_TRADE"), запреты origin, размещение в реестре.
- `test_stage_a_attribution.py` (22) — атрибуция новых объектов (в т.ч.
  fail-closed без контекста, конфликт значений), чтение старых записей
  без атрибуции с байт-неизменностью файла, отсутствие фиктивной
  атрибуции, csv-писатель новых журналов и совместимость старого читателя,
  связка с конфигурацией движка.
- `stage_a_golden_tools.py` — детерминированные fixture G-1 и генератор
  эталона (`python -m tests.stage_a_golden_tools`); не собирается pytest.
- `fixtures/legacy_golden_signals.json` — эталон G-1 (ожидания сигналов
  оригинальной логики + sha256 fixture).

## Changed

- Отсутствует. Изменений существующих файлов нет (155/155 baseline-файлов
  байт-идентичны; `orders.zip` тоже байт-идентичен, но исключён из ПОСТАВКИ
  по требованию ТЗ §14 — внутри реальные пользовательские runtime-файлы).

## Removed

- Отсутствует.

## Не выполнено сознательно (запреты ТЗ)

- Реализация этапов B–H (изоляция состояния, evaluate_exit, риск-менеджмент,
  симулятор, Sandbox-адаптер) — заглушек не создано.
- Оптимизация параметров, новые фильтры, FORCE_TRADE, запуск бота,
  подключения к брокеру, отправка заявок, миграция пользовательских данных —
  отсутствуют.
- Автоматический выбор/регистрация старой стратегии как активной —
  отсутствует.
