# README_STAGE_A.md
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A:
# STRATEGY CONTRACTS, CONFIGURATION AND ATTRIBUTION

## 1. Что это

Фундамент нового торгового движка Samsung V4 с независимыми стратегиями:
единый контракт стратегии, отдельная конфигурация движка, явное управление
выбором стратегии, строгая fail-closed валидация, атрибуция новых объектов
и регрессионная совместимость со старым Samsung V4.

Чего здесь НЕТ (и быть не должно по ТЗ): новой торговой стратегии,
изменения существующей торговой логики, оптимизаций, новых фильтров,
FORCE_TRADE, заявок, подключений к брокеру, реализации этапов B–H.

## 2. Состав поставки

```
SAMSUNG_V4_STAGE_A/
├── IMPLEMENTATION_REPORT.md     — полный отчёт реализации (ТЗ §15)
├── CHANGELOG.md                 — все изменения относительно baseline
├── BASELINE_VS_CANDIDATE.md     — байт-сверка с baseline 884cefd
├── TEST_RESULTS.txt             — протокол тестов (baseline + Stage A)
├── FILE_MANIFEST_SHA256.txt     — SHA-256 всех файлов поставки
├── ROLLBACK_INSTRUCTIONS.md     — полный откат до baseline
├── README_STAGE_A.md            — этот файл
├── candidate/                   — полная рабочая копия проекта
│   ├── <все файлы baseline — байт-идентичны 884cefd>
│   ├── engine.json              — НОВОЕ: конфигурация движка (ACTIVE_STRATEGY)
│   ├── strategy_api.py          — НОВОЕ: контракт стратегии
│   ├── engine_config.py         — НОВОЕ: конфигурация движка (env > json)
│   ├── attribution.py           — НОВОЕ: атрибуция объектов
│   ├── strategies/
│   │   ├── __init__.py          — НОВОЕ: явный реестр стратегий
│   │   └── legacy_samsung_v4/   — НОВОЕ: regression-only адаптер старой
│   │       ├── __init__.py        стратегии (исторический эталон; НЕ
│   │       ├── strategy.py        стратегия торгового режима)
│   │       ├── params.json
│   │       ├── profiles.py      — SANDBOX_TEST / TECH_CHECK / CONSERVATIVE
│   │       └── schema.py          (значения байт-в-байт из baseline)
│   └── tests/
│       ├── <все тесты baseline — байт-идентичны>
│       ├── test_stage_a_*.py    — НОВОЕ: 6 файлов, 128 тестов
│       ├── stage_a_golden_tools.py — НОВОЕ: fixture G-1 + генератор эталона
│       └── fixtures/legacy_golden_signals.json — НОВОЕ: эталон G-1
└── docs/                        — документация baseline (без изменений)
```

Не включён в поставку: `candidate/orders.zip` (есть в baseline; внутри —
реальные пользовательские runtime-файлы: state.json, журналы сделок; ТЗ §14
запрещает их включать). Файл не изменялся; SHA-256 для сверки — в
`BASELINE_VS_CANDIDATE.md` §4. Также в поставке нет `.env`, токенов,
`state.json`, журналов сделок и прочих пользовательских данных.

## 3. Конфигурация движка (engine.json + ACTIVE_STRATEGY)

- `engine.json` лежит рядом с runtime.env (.env), в корне `candidate/`.
- Поле `ACTIVE_STRATEGY`:
  - `null` (текущее поставляемое состояние) — **UNCONFIGURED**: торговый
    режим запрещён; offline-тесты разрешены. Это осознанное состояние:
    новой стратегии ещё нет, автовыбора нет.
  - Приоритет: переменная окружения `ACTIVE_STRATEGY` → значение из
    `engine.json` → UNCONFIGURED.
  - Неизвестное значение — ошибка конфигурации (fail-closed). Известная, но
    regression-only стратегия (`legacy_samsung_v4`) тоже отклоняется.
  - На Этапе A ЛЮБОЕ непустое значение отклоняется: активируемых стратегий
    нет — торговля невозможна по построению.
- Пример (будущее, после Этапа B/C — сейчас работать не будет):
  `ACTIVE_STRATEGY = "<id новой стратегии>"` — только вручную, только после
  явного выбора владельцем.
- Ключи `engine.json`, начинающиеся с `_`, — комментарии; неизвестные ключи
  дают предупреждение и не влияют на поведение.

Использование в коде (точка интеграции Этапа B; production main.py Этапом A
не менялся):

```python
import engine_config

cfg = engine_config.load_engine_config()
if cfg.trading_allowed:                    # только status == CONFIGURED
    ctx = engine_config.require_trading_ready(cfg)   # AttributionContext
```

## 4. Контракт стратегии (strategy_api.py)

Кратко:

```python
from strategy_api import Strategy, ParamSpec, ParamType, EntrySignalInput, Signal

class MyStrategy(Strategy):
    strategy_id = "my_strategy"          # уникальный
    strategy_version = "0.1.0"
    activation_mode = ActivationMode.TRADING_ALLOWED   # ЯВНО (умолчание —
                                                       # REGRESSION_ONLY!)
    def param_specs(self): ...
    def validate_params(self, params): ...
    def evaluate_entry(self, signal_input, config) -> Signal: ...
```

- `get_config(params)` валидирует и возвращает `StrategyConfig` с
  `config_hash` — стабильный SHA-256 по каноническому JSON
  (strategy_id + версия + нормализованные параметры; секреты, время,
  пути и переменные окружения не участвуют; порядок ключей не влияет).
- `Signal` несёт `strategy_id` и `config_hash` — атрибуция решения.
- Выход из позиции (evaluate_exit), изоляция состояния (strategy_id, FIGI),
  риск-менеджмент, симулятор, Sandbox-адаптер — Этапы B/C/D/E/F, здесь
  сознательно отсутствуют.

## 5. Старая стратегия (regression-only)

- `strategies/legacy_samsung_v4/` — изолированный адаптер к ОРИГИНАЛЬНОЙ
  логике `candidate/strategy.py`. Он НЕ копирует логику и НЕ активируется
  торговым режимом (`activatable=False`).
- Исторические профили SANDBOX_TEST / TECH_CHECK / CONSERVATIVE сохранены
  с точными значениями baseline (проверяется тестом G-5). FORCE_TRADE
  сознательно не перенесён.
- Регрессионный запуск сигнала (offline, тестовое окружение):

```python
from strategies.legacy_samsung_v4.strategy import LegacySamsungV4Strategy
s = LegacySamsungV4Strategy()
cfg = s.build_regression_config("TECH_CHECK")       # явный профиль
sig = s.evaluate_entry(input, cfg)                  # → Signal (BUY/SELL/HOLD)
```

- Golden-эталон G-1: `tests/fixtures/legacy_golden_signals.json`;
  пересборка (только при СОЗНАТЕЛЬНОЙ смене версии индикаторов):
  `python -m tests.stage_a_golden_tools` из каталога `candidate`.

## 6. Атрибуция

- Каждый НОВЫЙ объект движка должен нести `strategy_id` и `config_hash`
  (`attribution.stamp`, контекст из `require_trading_ready`).
- Старые записи читаются безопасно: `legacy_attribution_view` даёт явные
  `None`/`False`; никакие значения не выдумываются; исторические файлы не
  перезаписываются, миграции нет.
- Отсутствие контекста для нового объекта — ошибка (fail-closed), а не
  тихая запись без атрибуции.
- Встраивание в production-поток (`research_trades.csv` и т.п.) — решение
  Этапа B; предложение зафиксировано в `IMPLEMENTATION_REPORT.md` §13.3.

## 7. Тесты

```bash
cd candidate
python -m pytest            # полный набор: 899 passed (baseline 771 + 128 Stage A)
python -m pytest tests      # канонический поднабор run_tests.ps1: 379 passed
```

Все тесты offline. Протокол и окружение — `TEST_RESULTS.txt`.
В окружении с пустыми заглушками (без pandas-ta-classic) тесты G-1,
требующие реальных индикаторов, честно SKIP; baseline-тесты screener/ADX
в таком окружении падают ДО Stage A (известные ошибки baseline, список —
`TEST_RESULTS.txt` §2).

## 8. Требования к запуску

- Без изменений относительно baseline: те же зависимости
  (`candidate/requirements.txt`). Для зелёного полного прогона в чистом
  окружении установите доступные из них (см. `TEST_RESULTS.txt` §1);
  `t-tech-investments` в публичном PyPI отсутствует — для него штатно
  действуют заглушки conftest.
- Никаких новых обязательных зависимостей Этап A не добавляет.

## 9. Дальнейшие шаги (владелец)

1. Независимая проверка Этапа A (ТЗ §17). Этап B НЕ начинался.
2. Решение по встраиванию атрибуции в журналы (Этап B) —
   `IMPLEMENTATION_REPORT.md` §13.3, §15.
3. Только после появления и ЯВНОГО выбора исследованной стратегии —
   заполнение `ACTIVE_STRATEGY` (см. §3).

## 10. Откат

`ROLLBACK_INSTRUCTIONS.md` — удаление 18 добавленных файлов возвращает
проект к baseline байт-в-байт.
