# STAGE2_IMPLEMENTATION_BLUEPRINT.md

## SAMSUNG V4 — STAGE 2: проект реализации архитектуры независимых стратегий

**Мандаты (обязательные формулировки, унаследованы от Stage 1 / Stage 1.1):**

```
STRATEGY LOGIC: UNCHANGED
RESEARCH ONLY
NO THRESHOLD IS OPTIMIZED
NO FILTER IS INSTALLED
NO LIVE ORDERS
```

**Статус этапа:**

```
STAGE 2 — DESIGN ONLY
SOURCE CODE: UNCHANGED
TRADING: NOT EXECUTED
T-INVEST API: NOT ACCESSED
GITHUB: READ-ONLY
```

Stage 2 — исключительно проектирование. Ни один `.py`-файл не изменён,
ни один файл исходного проекта не создан и не удалён, торговый робот не
запускался, заявки не создавались и не отменялись, T-Invest API не
вызывался, GitHub-репозиторий не изменялся (никаких commit / branch /
PR / issues). Все содержимое разделов 3–11 — **ПРОЕКТ (PROPOSAL)**:
интерфейсы, структуры и правила, предлагаемые к будущей реализации.
Все утверждения о текущем коде — FACT и снабжены ссылками
`файл:строка` (полный перечень — STAGE2_SOURCE_TRACEABILITY.md).

**Категории доказательности (наследуются от Stage 1.1):**

- **FACT** — подтверждено исходным кодом commit `884cefd…` или документом
  Stage 1 / Stage 1.1 (указан файл:строка);
- **INFERENCE** — логический вывод из FACT;
- **PROPOSAL** — проектное решение Stage 2 (НЕ существует в коде);
- **UNKNOWN** — вопрос, который нельзя решить в рамках проектирования.

Тесты на Stage 2 не запускались; утверждения «тесты прошли» в документах
Stage 2 отсутствуют. Никакой механизм не объявлен «работающим» без
реализации.

---

## 0. Источники и проверка версий

| Предмет | Значение | Статус |
|---|---|---|
| Репозиторий | https://github.com/cristal-hub/Samsung-V4-BASELINE.git | FACT |
| Исходный код для анализа | `884cefd6f12a99f6adc14b5ed4c9eeda21d32e04` | FACT — SHA получен локально через `git rev-parse`, совпадает |
| Документы Stage 1 | каталог `SAMSUNG_V4_STAGE1_ARCHITECTURE_AUDIT`, commit `c4092213d1bc88735fa248b185cd1dc1e865bb87` (9 документов) | FACT |
| Документы Stage 1.1 | каталог `SAMSUNG_V4_STAGE1_1_ARCHITECTURE_ADDENDUM`, commit `c2cc7dd` (HEAD, 6 документов: ADDENDUM, CHANGELOG, VERIFICATION_MATRIX, 3 исправленные версии) | FACT |
| Идентичность кода между commit | `git diff 884cefd HEAD -- candidate/ docs/` — пусто (0 изменений); документы добавлялись только новыми каталогами | FACT |
| Рабочее дерево аудита | локальный READ-ONLY клон на commit `884cefd`; код не изменялся, `git status` чист | FACT |

Метод Stage 2: самостоятельное построчное чтение `strategy.py` (465 строк),
`risk_manager.py` (262), `execution.py` (1756, ключевые зоны: позиции,
check_all, per-order cursor, BE/TRAIL), `main.py` (5737, ключевые зоны:
цикл, входы, регистрация BUY, close_position, persistence, recovery),
`config.py` (162), `order_ledger.py` (603, контракты), `screener.py` (197),
`telegram_bot.py` (140), `safe_start.py` (274), `build_safety.py` (123),
`enable_sandbox_execution.py` (70), `tinkoff_client.py` (681, контракты
методов) + построчное чтение всех 15 документов Stage 1 / Stage 1.1.
Каждый ключевой вывод Stage 1.1 (матрица V-01…V-48) независимо перепроверен
по исходному коду; расхождений с Stage 1.1 не обнаружено (см.
STAGE2_SOURCE_TRACEABILITY.md §2). Статический анализ только; код не
запускался; pytest не выполнялся (результаты «789 passed» из
docs/INSTALLATION_RU.md §4 цитируются как задокументированный факт
владельца, не как собственный прогон Stage 2).

---

## 1. Цель и границы проекта

**Цель (§1 ТЗ Stage 2):** подготовить детальный, практически применимый
проект реализации архитектуры, в которой Samsung V4 становится
исполнительной платформой независимых торговых стратегий:

- выбор активной стратегии — одна настройка `ACTIVE_STRATEGY`;
- добавление новой стратегии не требует переписывания торгового движка;
- состояние изолировано по паре `(strategy_id, FIGI)`;
- вход и выход — явные типизированные контракты (SELL не является
  универсальной командой закрытия LONG);
- риск-менеджер учитывает фактическую дистанцию стопа стратегии;
- исторический тестер и песочница — два независимых адаптера исполнения
  над общей логикой стратегии и риск-политикой;
- существующая инфраструктура (учёт, сверка, восстановление, безопасность)
  сохраняется.

**Границы:** проект не реализуется (§11 ТЗ). Результат позволяет
разработчику приступить к Этапу A (STAGE2_IMPLEMENTATION_ROADMAP.md) без
повторного исследования архитектуры (§13 ТЗ). Порядок этапов, отличный от
предложенного ТЗ (A–G), обоснован в roadmap §2.

**Отношение к Stage 1.1.** Вердикт Stage 1.1 — NOT READY FOR
IMPLEMENTATION PLANNING с условиями C-1…C-7. Техническое задание Stage 2
является решением владельца перейти к проектированию; настоящий blueprint
фиксирует по каждому условию C-1…C-7 принятый в проекте вариант (таблица
в §12) и переносит всё, что осталось не решённым, в
STAGE2_OPEN_DECISIONS.md. Ни одно условие не «замалчивается».

---

## 2. Текущая архитектура — опорные факты (FACT)

Краткая опорная сводка; полная карта — CURRENT_ARCHITECTURE_MAP.md (Stage 1),
полная трассировка — STAGE2_SOURCE_TRACEABILITY.md.

### 2.1. Как устроено сегодня

| Факт | Источник |
|---|---|
| Один экземпляр `StrategyManager` на процесс, обслуживает все FIGI | main.py:5663, 5723-5729 (вызов 5725), 5237, 5260 |
| Runtime-состояние стратегии (ADX regime/hysteresis) — уровень экземпляра, не сбрасывается между FIGI; «та же свеча» распознаётся глобально | strategy.py:34-43, 100, 118-127, 188-190 |
| Сигнальный контракт: `get_signal() -> (BUY\|SELL\|HOLD, reason)` | strategy.py:177-219 |
| `SELL` при отсутствии позиции игнорируется («шорт запрещён»); `SELL` НЕ закрывает существующую LONG | main.py:5270-5276 |
| Выходы из позиции: только SL/TP (причины TP/SL/BE/TRAIL), оператор/внешнее закрытие (В3), штатное полное закрытие | execution.py:978-1022 (1011-1020); main.py:2224-2228, 2315, 1932-2011 |
| Безубыток/трейлинг существуют, но выключены (`BE_TRAIL_ENABLED=False`) | config.py:50; execution.py:913-966, 1003 |
| Частичное закрытие позиции в коде отсутствует | grep по `partial_close/PARTIAL_CLOSE/close_partial` — 0 совпадений |
| Входы — только LONG (движок long-only); зеркальные SHORT-ветки — только учётные | main.py:5270-5276; execution.py:953-966, 1008-1010 |
| Позиции хранятся по ключу FIGI; `TrackedPosition` не имеет `strategy_id` | execution.py:364, 242-346 |
| Sizing: `per_share_risk = base_risk + friction`; при ATR: `max(base_risk, atr_risk) + friction`; база — глобальные константы, НЕ фактический стоп стратегии | risk_manager.py:124-132, 137 |
| SL/TP: та же база и ATR-кап; SL/TP от `exec_price`, sizing от `last_price` | risk_manager.py:238-244; main.py:4072, 4808 vs 5278 |
| Hard caps движка: лимит сделок/день, доля на инструмент, тотальная экспозиция | risk_manager.py:91-92, 142-145, 198-201 |
| Профили FORCE_TRADE/SANDBOX_TEST/TECH_CHECK/CONSERVATIVE — переприсвоение 9 констант одной логики | config.py:76-119; strategy.py без ветвления по профилю |
| Учёт/восстановление: state.json (позиции + риск + open_orders), order_ledger.jsonl (append-only), В2/В3, startup_recovery | main.py:1144-1238, 2018-2223, 4831-5108; order_ledger.py |
| Безопасность: тройной запрет LIVE + guard Режима A/B (заявки физически блокируются по умолчанию) | config.py:147-163; tinkoff_client.py:182-184; build_safety.py:78-113 |
| Runtime-состояние стратегии не персистится (после рестарта режим определяется заново) | main.py:1144-1171; strategy.py:102-114 |

### 2.2. Что это означает для проекта

1. **Изоляция состояния (§3.2 ТЗ)** — текущее состояние violates требование:
   сигнал FIGI B зависит от того, что происходило с FIGI A (Stage 1.1 §1.3,
   сценарии 1–4). Проект обязан ввести состояние per-`(strategy_id, FIGI)`.
2. **Контракт выхода (§3.3 ТЗ)** — контракт `evaluate_exit` не существует;
   проект вводит его, не трогая существующие защитные выходы (SL/TP, В3).
3. **Согласование стопов (§3.4 ТЗ)** — сегодня связь sizing↔SL/TP держится
   на совпадении глобальных констант; для новой стратегии с собственным
   стопом это рвётся. Проект вводит контракт «фактическая стоп-дистанция →
   sizing» (Stage 1.1 §2.3, условие C-3).
4. **Backtest (§4 ТЗ)** — стратегия уже чиста от сети (FACT: strategy.py
   использует только config и pandas; данные — готовый DataFrame,
   main.py:5260); главный «утечки» — прямые `datetime.now()` в main.py и
   отсутствие интерфейса исполнения. Проект вводит ExecutionAdapter и
   детерминированную event-driven модель симулятора.

---

## 3. Целевая архитектура: три уровня и адаптеры

**ПРОЕКТ** (уточнение схемы Stage 1.1 §6.3.4; четыре слоя свернуты в три
уровня ТЗ Stage 2 §4 + отдельный брокерский адаптер):

```
                ┌────────────────────────────────────────────┐
                │ 1. STRATEGY LAYER                          │
                │  strategies/<strategy_id>/                 │
                │  - сигналы входа (EntryDecision)           │
                │  - политика выхода (ExitDecision)          │
                │  - SL/TP-уровни (compute_exit_levels)      │
                │  - плановая стоп-дистанция                 │
                │  - состояние per-(strategy_id, FIGI)       │
                │  - политика BE/TRAIL (on_extremes)         │
                └──────────────────┬─────────────────────────┘
                                   │ явные контракты (§4, §6)
                ┌──────────────────▼─────────────────────────┐
                │ 2. RISK LAYER (общий, стратегиенезависимый)│
                │  - sizing по фактической стоп-дистанции    │
                │    per_share_risk = max(base, atr) + fric  │
                │  - hard caps: экспозиция, доля, день       │
                │  - инварианты уровней (sl>0, tp>sl)        │
                │  - вето/уменьшение размера входа           │
                └──────────────────┬─────────────────────────┘
                                   │ приказы (orders), не сигналы
                ┌──────────────────▼─────────────────────────┐
                │ 3. EXECUTION LAYER (общий движок)          │
                │  INTENT-before-send, опрос, partial fill,  │
                │  UNCERTAIN, close_position, reconcile В2/В3 │
                │  защитные SL/TP (check_all)                │
                └──────────────────┬─────────────────────────┘
                    ExecutionAdapter (интерфейс, §9.1)
                 ┌──────────────────┴──────────────────┐
    ┌────────────▼─────────────┐          ┌────────────▼─────────────┐
    │ Historical Backtest      │          │ T-Invest Sandbox Adapter │
    │ Simulator                │          │ (TinkoffClient как есть; │
    │ (детерминированная       │          │  guard Режима A/B)       │
    │ event-driven модель, §9) │          └──────────────────────────┘
    └──────────────────────────┘
```

**Принцип разделения решений (§3.3 ТЗ):**

| Решение | Владелец | Основание |
|---|---|---|
| Вход: HOLD / OPEN_LONG / OPEN_SHORT* / CANCEL_ENTRY | Стратегия | сигнальная функция; движок никогда не изобретает вход |
| Выход: HOLD / CLOSE_LONG / PARTIAL_CLOSE* / TIME_EXIT / STRATEGY_EXIT | Стратегия (политика) | exit-контракт `evaluate_exit`; SL/TP остаются защитным слоем движка |
| SL/TP-уровни | Стратегия (расчёт) + движок (инварианты) | `compute_exit_levels`; проверка sl>0, tp>sl — движок (сегодня risk_manager.py:257-258) |
| BE/TRAIL перенос SL | Стратегия (политика) при жёстких ограничениях движка | «SL никогда не ослабляется» — execution.py:920 сохраняется |
| Размер позиции | Риск-менеджер (по стоп-дистанции стратегии) | §7; стратегия не может обходить hard caps |
| Вето входа/лимиты | Риск-менеджер | risk_manager.py:91-92, 142-145, 198-201 сохраняются |
| Исполнение и отмены | Execution Layer | INTENT-before-send, fail-closed, UNCERTAIN — без изменений |
| Защитные SL/TP-выходы | Движок (Execution Layer) | check_all execution.py:978-1022 — стратегия не может их отключить |

(*) `OPEN_SHORT` валиден ТОЛЬКО если манифест движка декларирует
`allow_short_entry=true` — сегодня движок long-only (FACT main.py:5270-5276);
по умолчанию capability выключена (§4.4). `PARTIAL_CLOSE` отложен: механизм
частичного закрытия отсутствует (FACT), требует отдельного проектирования
учёта (Stage 1.1 F-3.8) — см. STAGE2_OPEN_DECISIONS.md D-7.

---

## 4. Контракт стратегии (§3.1 ТЗ)

**ПРОЕКТ.** Имена методов наследуют исправленную версию Stage 1.1
(STRATEGY_SWITCH §3), которая подбирала их по фактическим точкам вызова
кода. Контракт дополняет: `get_state()/set_state()` (изоляция состояния),
`EntryDecision/ExitDecision` (типизированные решения), манифест
возможностей.

### 4.1. Базовый интерфейс

```python
# strategy_api.py  (ПРОЕКТ: файла не существует)

class DecisionType(str, Enum):
    # --- входные решения (контракт get_signal) ---
    HOLD          = "HOLD"            # не входить / продолжать удержание
    OPEN_LONG     = "OPEN_LONG"       # вход в LONG
    OPEN_SHORT    = "OPEN_SHORT"      # ТОЛЬКО при engine.allow_short_entry=True
    CANCEL_ENTRY  = "CANCEL_ENTRY"    # отозвать собственное незавершённое намерение входа
                                      # (применимо: заявка в состоянии NEW/PARTIALLYFILL
                                      #  ещё не зарегистрирована как позиция)
    # --- решения по открытой позиции (контракт evaluate_exit) ---
    CLOSE_LONG    = "CLOSE_LONG"      # закрыть LONG-позицию целиком
                                      # (для long-only движка; алиас прежнего
                                      #  CLOSE_POSITION из Stage 1.1 §3.3)
    PARTIAL_CLOSE = "PARTIAL_CLOSE"   # закрыть часть (ОТЛОЖЕНО: учёт не спроектирован)
    TIME_EXIT     = "TIME_EXIT"       # выход по времени (конец сессии / max_hold)
    STRATEGY_EXIT = "STRATEGY_EXIT"   # выход по условию стратегии


class EntryDecision:                  # ПРОЕКТ: dataclass
    type: DecisionType                 # HOLD | OPEN_LONG | OPEN_SHORT | CANCEL_ENTRY
    reason_code: str                   # машиночитаемая причина ("ma_cross_up")
    reason_text: str                   # человекочитаемое описание
    candle_time: Optional[str]         # время решения (index[-1] свечей)
    planned_stop_distance: Optional[float]   # дистанция стопа для sizing (§7)
    audit: dict                        # снимок входных данных решения,
                                       # strategy_id, config_hash (§6 Stage 1)

class ExitDecision:                   # ПРОЕКТ: dataclass
    type: DecisionType                 # HOLD | CLOSE_LONG | PARTIAL_CLOSE |
                                       # TIME_EXIT | STRATEGY_EXIT
    reason_code: str                   # напр. "strategy_exit_ma_down"
    reason_text: str
    quantity: Optional[int]            # для PARTIAL_CLOSE (лот); None = всё
    candle_time: Optional[str]
    audit: dict                        # strategy_id, config_hash, состояние


class StrategyManifest:               # ПРОЕКТ: декларация возможностей
    strategy_id: str                   # стабильный id, напр. "legacy_samsung_v4"
    strategy_version: str              # версия логики
    params_version: str                # версия значений
    requires: frozenset                # напр. {"candles_5min", "intraday_extremes"}
    supported_sides: frozenset         # {"LONG"}; {"LONG","SHORT"} — только при
                                       # allow_short_entry=True у движка
    engine_capabilities_required: dict # напр. {"allow_short_entry": False}


class EngineContext:                  # ПРОЕКТ: доступ движка для стратегии
    clock() -> datetime                # ЕДИНСТВЕННЫЙ источник времени (T-1.3 Stage 1)
    candles_provider(figi, days, interval) -> pd.DataFrame
    instrument_info(figi) -> dict      # lot, tick — только статика
    config_snapshot -> Mapping         # замороженная конфигурация (иммутабельна)


class StrategyBase(ABC):              # ПРОЕКТ: интерфейс, не существует в коде
    manifest: StrategyManifest
    params: Mapping                    # валидированные схемой, иммутабельные

    def __init__(self, params: Mapping, context: EngineContext) -> None: ...

    def on_start(self, candles_provider) -> None:
        """Проверка готовности данных (аналог MIN_CANDLES_FOR_SIGNAL,
        strategy.py:32). Ошибки -> отказ старта (fail-closed)."""

    # === ВХОД: точное соответствие существующей сигнатуре ===
    def get_signal(self, candles_df, last_price: float,
                   drop_incomplete: bool) -> EntryDecision:
        """Совместимость: текущая функция возвращает (str, str)
        (strategy.py:177-182); движок вызывает её в main.py:5260.
        На переходный период движок принимает и (str, str), и
        EntryDecision (адаптер legacy, §4.3)."""

    # === ВЫХОД: новый контракт (не существует в коде) ===
    def evaluate_exit(self, position_view, candles_df, price: float,
                      state) -> ExitDecision:
        """position_view — read-only проекция TrackedPosition
        (entry_price, initial_sl_price, initial_tp_price, mae/mfe,
        opened_at, direction, quantity). НЕ позволяет стратегии менять
        учёт. state — runtime-состояние стратегии по паре (id, figi)."""

    # === УРОВНИ И СТОП ===
    def compute_exit_levels(self, entry_price: float, direction: str,
                            candles_df) -> tuple[Optional[float], Optional[float]]:
        """Перенос rm.calculate_sl_tp (risk_manager.py:233-259).
        Места вызова сохраняются: main.py:4072, 4808."""

    def get_planned_stop_distance(self, last_price: float,
                                  candles_df) -> float:
        """Фактическая стоп-дистанция на момент sizing (§7).
        Общий RiskManager обязан использовать ИМЕННО её."""

    # === СОСТОЯНИЕ (изоляция per-(strategy_id, FIGI), §5) ===
    def get_state(self, figi: str) -> dict: ...
    def set_state(self, figi: str, state: dict) -> None: ...
        """Сериализуемый dict runtime-состояния. Для legacy:
        _last_regime, _regime_streak, _last_regime_candidate,
        _last_regime_candle_time (strategy.py:34-43)."""

    # === ОПОЦИОНАЛЬНЫЕ ТОЧКИ ===
    def on_position_opened(self, position_view) -> None: ...
    def on_extremes(self, position_view, candle_high, candle_low,
                    atr) -> Optional[float]:
        """Точка BE/TRAIL: сегодня _update_sl (execution.py:913-966).
        Возврат None = не менять. Движок гарантирует: SL только
        ужесточается (инвариант execution.py:920)."""

    def get_diagnostics(self) -> dict:
        """Сегодня last_adx_value/_last_regime/_regime_streak
        (strategy.py:42-43) читаются в main.py:1055-1064."""
```

### 4.2. Примеры контрактов методов

**Пример 1 — вход (legacy-логика, эквивалент текущего поведения):**

```python
def get_signal(self, candles_df, last_price, drop_incomplete) -> EntryDecision:
    prepared = self._prepare_dataframe(candles_df, drop_incomplete)
    if prepared is None or len(prepared) < self.params["min_candles_for_signal"]:
        return EntryDecision(DecisionType.HOLD, "not_enough_data",
                             "Недостаточно данных", _t(prepared), None, self._audit())
    regime = self._market_regime(prepared, figi_state=self.get_state(FIGI_KEY))
    if regime == "TREND":
        sig, why = self._ma_crossover(prepared)          # логика 1:1 strategy.py:253-310
    elif regime == "RANGE":
        sig, why = self._bb_rsi(prepared)                # логика 1:1 strategy.py:312-389
    else:
        return EntryDecision(DecisionType.HOLD, "regime_unknown",
                             "Режим не определён", _t(prepared), None, self._audit())
    if sig in {"BUY", "SELL"} and not self._volume_ok(prepared)[0]:
        return EntryDecision(DecisionType.HOLD, "volume_rejected", why,
                             _t(prepared), None, self._audit())
    if sig == "BUY":
        return EntryDecision(DecisionType.OPEN_LONG, "entry_long", why,
                             _t(prepared),
                             self.get_planned_stop_distance(last_price, prepared),
                             self._audit())
    # SELL не является закрытием LONG: движок игнорирует его при отсутствии
    # позиции (поведение main.py:5270-5276 сохранено явно).
    return EntryDecision(DecisionType.HOLD, "sell_no_short", "Шорт запрещён",
                         _t(prepared), None, self._audit())
```

**Пример 2 — выход (новый контракт; для legacy вернёт HOLD — legacy не
принимает стратегических решений о выходе, его выходы — SL/TP движка,
Stage 1.1 F-3.10):**

```python
def evaluate_exit(self, pv, candles_df, price, state) -> ExitDecision:
    # legacy_samsung_v4: выходы определяются SL/TP движка
    # (execution.py:978-1022); стратегическое решение о выходе не вводится,
    # чтобы не менять торговый результат (мандат STRATEGY LOGIC: UNCHANGED).
    return ExitDecision(DecisionType.HOLD, "engine_sl_tp_owner",
                        "Выход управляется SL/TP движка", None, self._audit())

# Пример будущей стратегии с собственным выходом:
def evaluate_exit(self, pv, candles_df, price, state) -> ExitDecision:
    if self._ma_crossed_down(candles_df):
        return ExitDecision(DecisionType.STRATEGY_EXIT, "ma_cross_down",
                            "MA(9/21) ↓ — выход", None, _t(candles_df), self._audit())
    if self._max_hold_expired(pv.opened_at, self.context.clock()):
        return ExitDecision(DecisionType.TIME_EXIT, "max_hold",
                            "Превышено максимальное время удержания",
                            None, _t(candles_df), self._audit())
    return ExitDecision(DecisionType.HOLD, "hold", "Условий выхода нет",
                        None, _t(candles_df), self._audit())
```

### 4.3. Переходная совместимость

Движок на переходный период принимает оба вида результата `get_signal`:
кортеж `(BUY|SELL|HOLD, reason)` от legacy-адаптера и `EntryDecision` от
новых стратегий. Нормализация — в одном месте (`strategy_api.normalize_signal`).
Это позволяет мигрировать strategy.py в `legacy_samsung_v4` построчно
(R3.2 Stage 1) без единовременной переписывания вызовов.

### 4.4. Возможности движка и сторонность позиций

- Движок декларирует capabilities: `{"allow_short_entry": False,
  "allow_partial_close": False, "candles_5min": True,
  "intraday_extremes": True}` (FACT-обоснование: long-only main.py:5270-5276;
  partial close отсутствует; свечи 5-мин main.py:3297).
- Стратегия в манифесте объявляет `supported_sides` и required-capabilities.
- Несовпадение = отказ старта (fail-closed, §5.4 ТЗ Stage 2).
- `OPEN_SHORT`/`CLOSE_SHORT` не проектируются на Stage 2; учётные
  зеркальные ветки execution.py:953-966 остаются как есть (адопция SHORT
  при внешнем закрытии — существующее поведение).

---

## 5. Изоляция состояния по инструментам (§3.2 ТЗ)

**ПРОЕКТ** (реализует условие C-1 Stage 1.1 — вариант «предпочтительно»).

### 5.1. Структура состояния

```
state.json:
{
  ...существующие разделы (positions, risk, open_orders, ...) без изменений...,
  "strategy_state": {
      "<strategy_id>": {
          "strategy_version": "...",
          "instruments": {
              "<figi>": {
                  "runtime_state": { ... },          # dict стратегии
                  "last_processed_candle_time": "...",  # защита от повтора
                  "updated_at_utc": "..."
              }
          }
      }
  },
  "config_snapshot": { ... },                          # §10.4
  "config_hash": "sha256:..."
}
```

- Ключ изоляции — ровно `(strategy_id, FIGI)` (§3.2 ТЗ). Состояние одного
  инструмента физически не может попасть в расчёт сигнала другого:
  стратегия получает `state` только для своей пары.
- **Альтернатива (экземпляр стратегии на каждый FIGI)** — сохранена как
  допустимая, но отклонена в проекте: дублирует конфигурацию и
  телеметрию на N экземпляров, усложняет восстановление/сохранение
  (последствия для state.json и reconcile) и не даёт преимуществ при
  already-серилизуемом состоянии. Решение владельца — D-2 в
  STAGE2_OPEN_DECISIONS.md.
- Существующие разделы state.json (позиции/риск/заявки) НЕ меняются —
  совместимость восстановления (main.py:1192-1238) сохраняется; новый
  раздел отсутствует в старом файле -> трактуется как пустое состояние
  (тот же паттерн совместимости, что execution.py:318-333).

### 5.2. Правила обработки свечей

| Правило | Проект | Основание |
|---|---|---|
| Сохранение | `strategy_state` пишется в конце каждого `trading_cycle` штатным `_save_state` (main.py:1144-1171) — та же атомарная запись tmp+os.replace | существующий механизм |
| Восстановление после перезапуска | `_load_state` восстанавливает `strategy_state` ДО первого цикла; стратегия получает состояние ПРАВИЛЬНОЙ пары (id, figi) | требования §3.2 ТЗ |
| Независимость от порядка обработки | вызов сигнала для FIGI получает и изменяет ТОЛЬКО свой срез состояния; порядок `top_instruments` (сортировка по волатильности, screener.py:196-197) больше не влияет на результат | устраняет Stage 1.1 §1.3 сценарии 1, 2, 4 |
| Пропущенные свечи | обработка идёт по фактической последней свече ленты; пропуск свечей не «переигрывается» — гистерезис считает УНИКАЛЬНЫЕ свечи подряд по своему срезу; разрыв последовательности виден в `last_processed_candle_time` и журнале | сохранение семантики «уникальная свеча» (strategy.py:118-127) в пределах пары |
| Защита от повторной обработки | свеча с `time == last_processed_candle_time` обрабатывается идемпотентно: кандидат ADX вычисляется, серия подтверждений НЕ инкрементируется (это точное воспроизведение ветки strategy.py:118-127, но в пределах пары (id, figi)) | Stage 1.1 V-07, но per-pair |
| Конфликт версии | несовпадение `strategy_version` в state и манифесте -> входы запрещены до подтверждения оператора (аналог config_hash-защиты §10.4) | §8 Stage 1 STRATEGY_SWITCH |

### 5.3. Что происходит с «глобальной меткой свечи»

Сегодня `candle_time == self._last_regime_candle_time` сравнивается
глобально (strategy.py:100, 118) — инструмент B получает режим,
вычисленный по данным инструмента A (Stage 1.1 §1.3 сценарий 1). В проекте
метка хранится в срезе пары; сравнение — только внутри пары. Поведение
одиночной стратегии на одиночном FIGI НЕ меняется (эталон для golden-теста).

---

## 6. Единый контракт входа и выхода (§3.3 ТЗ)

**ПРОЕКТ.** Точка интеграции — торговый цикл main.py:5236-5310.

### 6.1. Входной конвейер (изменения в цикле входов)

```
for inst in top_instruments:                       # main.py:5237 (без изменений)
    ...фильтры цены/позиции/реестра (5239-5253 без изменений)...
    df = await _build_candles_df(client, figi)     # 5255 без изменений
    dec = strategy.get_signal(df, price, drop_incomplete=True)   # 5260: стратегия
                                                                  # пары (id, figi)
    if dec.type == HOLD:      ... журналирование как сегодня (5262-5268) ...
    if dec.type == OPEN_LONG:
        lots = rm.calculate_position_size(             # 5278: sizing по стоп-дистанции
            figi, price, df,
            planned_stop_distance=dec.planned_stop_distance)   # §7
        ...INTENT-before-send, post, partial branch — 5300-5471 БЕЗ ИЗМЕНЕНИЙ...
    if dec.type == OPEN_SHORT:  # недостижимо: allow_short_entry=False ->
                                # движок отклоняет на валидации манифеста
    if dec.type == CANCEL_ENTRY: # движение: poll_open_orders отменяет
                                 # незавершённый BUY этой пары (5379-5391
                                 # переиспользуется; см. D-8)
```

- `SELL` (и `HOLD` с reason «sell_no_short») при отсутствии позиции —
  поведение «шорт запрещён» сохранено (main.py:5270-5276); журнал
  STRATEGY_SELL_IGNORED сохраняется.
- **Существующая позиция по FIGI полностью блокирует входной блок
  (5244)** — инвариант «не более одной активной позиции на FIGI на
  процесс» сохраняется; позиция всегда принадлежит ровно одной стратегии
  (`pos.strategy_id`, §11.2).

### 6.2. Выходной конвейер (новая точка в check_all-контуре)

```
# шаг 2 trading_cycle (main.py:5135-5152) дополняется ПЕРЕД check_all:
for pos in monitor.open_positions():
    owner = strategies[pos.strategy_id]            # стратегия-автор позиции
    dec = owner.evaluate_exit(pos.view(), df_by_figi[pos.figi],
                              prices[pos.figi],
                              owner.get_state(pos.figi))
    if dec.type in {CLOSE_LONG, TIME_EXIT, STRATEGY_EXIT}:
        pos.close_reason = dec.reason_code          # аудит: причина из решения
        to_close.append(pos)
    elif dec.type == PARTIAL_CLOSE:                 # ОТЛОЖЕНО (D-7)
        raise EngineRefuse("partial_close_not_implemented")   # fail-closed
# затем штатно: to_close = await monitor.check_all(prices, ...)  # 5144
# защитные SL/TP движка работают как прежде и имеют приоритет исполнения:
# check_all помечает CLOSING по TP/SL/BE/TRAIL (execution.py:1011-1020),
# close_position отправляет SELL всем количеством (main.py:2315).
```

- Стратегический выход и защитный SL/TP могут сработать в одном цикле:
  объединение `to_close` без дублирования (позиция уже CLOSING -> пропуск),
  причина — та, что сработала первой в порядке шагов (защитный check_all
  сохраняет свой контракт; стратегический выход фиксирует свой reason_code).
- `close_position` НЕ меняется: полному количеству, INTENT-before-send,
  запрет повторной SELL (main.py:2235-2252).
- Что НЕ меняется ни при каких условиях: SL/TP, BE/TRAIL-механика движка,
  В2/В3 внешнее закрытие, запрет автоматического закрытия RECOVERY
  (main.py:151-153).

### 6.3. Распределение решений (сводка)

См. таблицу в §3. Дополнение по аудиту: каждое решение (вход и выход)
пишется в `research_events.jsonl` с полями `strategy_id`, `config_hash`,
`decision_type`, `reason_code`, `candle_time` — расширение шапки
log_event (logger.py:180-192), совместимое с существующей записью.

---

## 7. Единый риск-менеджмент: контракт стоп-дистанции (§3.4 ТЗ)

**ПРОЕКТ** (реализует условие C-3 Stage 1.1).

### 7.1. Фактическая формула сегодня (FACT — risk_manager.py:124-137)

```
risk_amount     = balance * RISK_PER_TRADE                          # стр. 104
base_risk       = last_price * max(STOP_LOSS_PERCENT,
                                   MIN_STOP_LOSS_PERCENT)           # стр. 124
friction        = last_price * (COMMISSION_PER_SIDE*2 + SLIPPAGE_PERCENT)  # 125
per_share_risk  = base_risk + friction                              # 126
если ATR:  atr_risk = min(ATR*ATR_STOP_MULTIPLIER,
                          last_price*MAX_ATR_STOP_PERCENT)          # 128-131
           per_share_risk = max(per_share_risk, atr_risk + friction) # 132
           (≡ max(base_risk, atr_risk) + friction)
lots            = int(risk_amount / (per_share_risk * lot_size))    # 137
```

Stage 1.1 подтвердил: запись Stage 1 `max(base_risk, atr_risk + friction)`
была неточна; фактический код эквивалентен
`per_share_risk = max(base_risk, atr_risk) + friction` (Stage 1.1 §5).

### 7.2. Целевой контракт (PROPOSAL)

```
calculate_position_size(figi, last_price, candles_df,
                        planned_stop_distance: float) -> int
```

1. Стратегия передаёт `planned_stop_distance` в денежном выражении на акцию
   (поле `EntryDecision.planned_stop_distance`, §4.1). Для legacy это
   `entry * max(STOP_LOSS_PERCENT, MIN_STOP_LOSS_PERCENT)`, при наличии ATR
   поднятая до `min(ATR*ATR_STOP_MULTIPLIER, entry*MAX_ATR_STOP_PERCENT)` —
   байт-в-байт то же, что risk_manager.py:124-132/238-243 даёт сегодня.
2. RiskManager использует ИМЕННО эту дистанцию:
   `per_share_risk = planned_stop + friction` (без ATR-дубля: ATR-ветка
   уходит в стратегию как часть её дистанции; движок сохраняет
   `MAX_ATR_STOP_PERCENT` как верхний инвариант ДВИЖКА — см. п. 4).
3. friction сохраняет семантику: `last_price * (COMMISSION_PER_SIDE*2 +
   SLIPPAGE_PERCENT)` (risk_manager.py:125).
4. Hard caps движка остаются обязательными и не обходятся стратегией:
   `MAX_TRADES_PER_INSTRUMENT_PER_DAY` (91-92), `MAX_POSITION_SHARE_PER_
   INSTRUMENT` (142-145), `MAX_TOTAL_EXPOSURE` (198-201), а также
   инварианты уровней: `planned_stop > 0`, `sl > 0`, для BUY `sl < entry`,
   `tp > sl` (сегодня risk_manager.py:257-258 — переносится в движок без
   изменения семантики). Нарушение -> размер 0 / отказ входа (fail-closed).
5. **Консистентность sizing↔SL/TP проверяется движком** (новое):
   при регистрации исполнения (main.py:4072) фактическая дистанция
   `|exec_price - sl|` сравнивается с `planned_stop_distance`, учтённой в
   sizing; расхождение сверх допуска -> событие
   `STOP_SIZING_MISMATCH` в журнал (не блокирует регистрацию
   подтверждённого исполнения — Дефект №7 main.py:4068-4084 сохраняется).
   Известный сегодня нюанс `last_price` vs `exec_price` (Stage 1.1 §2.1
   FACT) становится наблюдаемым.
6. Аудит: в SIGNAL-событие добавляются `planned_stop_distance`,
   `stop_source` ("strategy"|"engine"), `per_share_risk`, `friction`.
7. **Минимальный шаг цены и размер лота** (§3.4 ТЗ): размер позиции —
   целое число ЛОТОВ (инвариант `get_positions` — лоты; сегодня
   risk_manager.py:137 `int(risk_amount / (per_share_risk * lot_size))`,
   lot_size из `get_instrument_info` — tinkoff_client.py:270-301);
   уровни SL/TP округляются до тика инструмента (tick из той же
   статической таблицы; в backtest — правило A-8, §9.2). Дробный размер
   невозможен; округление ВНИЗ сохраняет ограничение риска.

### 7.3. Разделение «стратегический стоп» и «ограничения безопасности»

| Уровень | Что определяет | Что НЕ может |
|---|---|---|
| Стратегия | дистанцию и уровни своего стопа/тейка; политику BE/TRAIL | обходить hard caps; задавать sl<=0; ослаблять SL (execution.py:920) |
| Risk Layer | размер, лимиты, экспозицию, вето | изобретать сигналы/выходы; менять уровни стратегии |
| Execution Layer | защитные SL/TP-выходы, механику закрытия, UNCERTAIN | интерпретировать сигналы; «улучшать» решения |

---

## 8. Старая стратегия: `legacy_samsung_v4` (§3.5 ТЗ)

**ПРОЕКТ** (реализует условие C-4 Stage 1.1).

1. Текущая логика переносится в `strategies/legacy_samsung_v4/`
   (построчная миграция strategy.py, R3.2 Stage 1) с идентификатором
   `legacy_samsung_v4` и статусом:
   - **FROZEN** — правки логики/значений запрещены;
   - **regression/compatibility only** — используется для golden-тестов
     эквивалентности и сравнения поведения старой/новой архитектуры;
   - не участвует в рейтинге/поиске прибыльности новых стратегий;
   - НЕ является default: конфигурация не содержит значения
     `ACTIVE_STRATEGY` по умолчанию — отсутствие явного значения =
     отказ старта (fail-closed, §10). Использование legacy для
     миграционных прогонов — всегда явное решение оператора;
   - параметры не оптимизируются (мандат NO THRESHOLD IS OPTIMIZED).
2. Профили FORCE_TRADE/SANDBOX_TEST/TECH_CHECK/CONSERVATIVE —
   FACT: наборы параметров ОДНОЙ логики (config.py:76-119 переприсваивает
   9 констант; strategy.py без ветвления по профилю). В проекте —
   вариантные наборы (`profiles.py`) внутри `legacy_samsung_v4`,
   значения НЕ меняются (таблица Stage 1 INVENTORY §2 сохраняется).
   Новые стратегии НЕ наследуют имена профилей.
3. Позиции legacy в режиме INHERIT сопровождаются экземпляром
   `legacy_samsung_v4`; его «exit-правила» — сохранённые SL/TP/BE/TRAIL
   механики движка, НЕ новая оптимизация (Stage 1.1 §7).

---

## 9. BACKTEST и SANDBOX: три уровня и адаптеры (§4 ТЗ)

### 9.1. ExecutionAdapter — интерфейс исполнения (PROPOSAL)

Точный набор операций текущего клиента (FACT-таблица Stage 1 T-4,
проверена по коду):

| Операция | Live-реализация (файл:строка) | Backtest-реализация |
|---|---|---|
| `get_last_prices(figis)` | tinkoff_client.py:253-268 | цена свечи на момент решения |
| `get_historical_candles(figi, days, interval)` | 240-251 | окно истории из симулируемой ленты |
| `get_instrument_info(figi)` | 270-301 | статическая таблица (lot, tick) |
| `get_positions()` | 315-435 | позиция симулятора (PositionData: лоты со знаком) |
| `get_account_balance()` | 303-313 | баланс симулятора |
| `post_market_order(figi, qty, dir, order_id)` | 555-599 | исполнение по модели заполнения; order_id сохраняется даже при «потере ответа» |
| `get_sandbox_order_state(oid, type)` | 601-644 | статус симулируемой заявки |
| `cancel_order(oid, type)` | 646-679 | отмена |
| `get_sandbox_orders()` | 437-456 | список активных заявок |

Требование fail-closed сохраняется в ОБЕИХ реализациях: `None` =
состояние неизвестно, `{}` = достоверно пусто (tinkoff_client.py:315-319).
Симулятор обязан уметь возвращать «неизвестно» по сценарию — иначе
защитные механизмы движка не проверяются реалистично.

### 9.2. Правила моделирования исторического тестера (§4 ТЗ, A-1…A-13)

Каждое допущение — явный параметр конфигурации симулятора, входит в
config_hash; «по умолчанию не определено» = отказ старта (нет скрытых
дефолтов).

| # | Допущение (§4 ТЗ) | Модель v1 (PROPOSAL) | Правило |
|---|---|---|---|
| A-1 | Комиссия | модельная ставка (по умолчанию `COMMISSION_PER_SIDE`); поддерживает фактическую/модельную замену как live (main.py:2464-2489) | списывается с обеих сторон сделки |
| A-2 | Проскальзывание | фиксированная доля `SLIPPAGE_PERCENT`, применяется против стратегии | цена заполнения ухудшается на slippage |
| A-3 | Bid/ask spread | модельная доля или фиксированный спред из статической таблицы инструментов | заполнение по неблагоприятной стороне |
| A-4 | Гэпы | если уровень SL/TP внутри гэпа — заполнение по цене ОТКРЫТИЯ бара, не по уровню | исключает нереальные исполнения по уровню |
| A-5 | Частичное исполнение | явная модель: доля заполнения за бар (конфигурируется); учёт через существующие ветки partial (main.py:5369-5471) | незаполненный остаток отменяется, как в live |
| A-6 | Ликвидность | v1: НЕ моделируется (явно `liquidity_model: none`); ограничение объёма — опция будущего этапа | явное отсутствие модели, не скрытое |
| A-7 | Market impact | v1: НЕ моделируется (явно `market_impact_model: none`) | явное отсутствие модели |
| A-8 | Шаг цены (tick size) | округление цен до тика из статической таблицы | цены приказов и заполнений кратны тику |
| A-9 | Лотность | кратность лотам (инвариант лотов `get_positions`) | как live |
| A-10 | Торговые сессии | календарь MOEX; события вне сессии не обрабатываются | как live-цикл не работает вне сессии |
| A-11 | Корпоративные события | v1: ВНЕ модели (явно); делистинг -> позиция передаётся оператору (аналог RECOVERY-политики) | задокументированное ограничение |
| A-12 | Задержка данных | v1: данные доступны на момент бара (явно `data_delay_model: none`) | задокументированное ограничение |
| A-13 | Конфликт SL и TP внутри одной свечи | **КОНСЕРВАТИВНОЕ ПРАВИЛО (инвариант)** | см. 9.3 |

### 9.3. Консервативное правило внутри одной свечи (инвариант, не опция)

Если OHLC-свеча показывает, что внутри одной свечи достигнуты и SL, и TP,
а последовательность движения цены неизвестна, симулятор считает, что
ПЕРВЫМ сработал неблагоприятный для стратегии уровень (SL). Выбор
более выгодного порядка задним числом ЗАПРЕЩЁН. Замечание о текущем
live-коде (FACT): при точечном опросе цены `price >= tp` и `price <= sl`
для BUY не могут быть истинны одновременно (execution.py:1005-1010);
неоднозначность возникает только при внутрибарном моделировании — правило
определяет её разрешение и гарантирует, что backtest не завышает
результаты.

### 9.4. Детерминизм и воспроизводимость

- Вход: зафиксированная лента 5-мин свечей (та же гранулярность, что live:
  MAE/MFE и экстремумы live берутся из 5-мин свечей — execution.py:884-888;
  T-5.3 Stage 1).
- Фиксированный порядок событий бара: открытие -> внутрибарные уровни
  (SL/TP по правилу A-13) -> закрытие; решения — функции только от уже
  увиденных данных (заглядывание в будущее запрещено).
- Та же последовательность шагов цикла, что live (main.py:5115-5619):
  SL/TP -> closing -> poll_open_orders -> promote_recovery -> reconcile ->
  входы.
- Источник времени — инъекция `EngineContext.clock()` (T-1.3 Stage 1;
  прямые `datetime.now(timezone.utc)` в main.py — верифицированный
  Stage 2 список: 645, 854, 1500, 1935, 1957, 1988, 2269, 3033, 3074,
  5292 и др. — заменяются в реализуемом этапе E).
- Воспроизводимость: одинаковые данные + конфигурация + версия модели ->
  байт-в-байт одинаковый результат (события, заявки, CSV-строки); версия
  модели исполнения входит в config_hash и шапку журналов.
- Симулятор НЕ выдаёт себя за копию брокера: результаты маркируются
  `execution_model: "backtest_v1"`; сравнение с live — только по-шаговое
  по журналам событий (main.py:1055-1064), не «равенство P&L».

### 9.5. T-Invest Sandbox Adapter

- `TinkoffClient` НЕ изменяется; он оборачивается в
  `SandboxExecutionAdapter` (реализация ExecutionAdapter делегированием).
- Вся существующая защита сохраняется: тройной запрет LIVE
  (config.validate config.py:162-163; SandboxRequiredError
  tinkoff_client.py:182-184; assert_sandbox_only build_safety.py:78-83) и
  guard Режима A (build_safety.py:86-113) — заявки физически блокируются
  по умолчанию; Режим B — только явной процедурой (маркер + env).
- Общая логика стратегии и риск-политика — ИДЕНТИЧНЫЫ для backtest и
  sandbox (те же модули, та же конфигурация категории A/B); различается
  только адаптер исполнения и источник свечей.

---

## 10. Конфигурация (§5 ТЗ)

### 10.1. Принципы

1. Выбор стратегии — одна настройка `ACTIVE_STRATEGY` (non-code файл:
   env или JSON запуска; Stage 1 STRATEGY_SWITCH §4).
2. Отдельные параметры стратегий, риск-менеджмента, исполнения —
   раздельные файлы/секции; движок не читает сигнальные константы из
   config.py (категории A–E Stage 1 STRATEGY_SWITCH §2).
3. Строгая валидация: типы, диапазоны (только доказуемые из кода),
   кросс-проверки (HARDCODED §6 Stage 1: MIN_CANDLES_FOR_SIGNAL ≥
   max(MA_SLOW+2, BB+RSI, ADX+1, TREND_FILTER_MA); RSI_OVERSOLD <
   RSI_OVERBOUGHT; CANDLES_LOOKBACK_DAYS обеспечивает MIN_CANDLES 5-мин
   свечей; ADX_HYSTERESIS_CANDLES ≥ 1; VOLUME_CONFIRMATION_WINDOW ≥ 3;
   TAKE_PROFIT_RATIO > 0).
4. НЕТ скрытых дефолтов для критических параметров; НЕТ
   getattr-fallback (сегодняшний паттерн main.py:1952-1953, 5139;
   execution.py:923, 1003 — в новом слое не воспроизводится).
5. Отказ запуска при некорректной конфигурации (по образцу
   config.validate() config.py:147-163, с перечнем всех ошибок разом).

### 10.2. Структура файлов (PROPOSAL)

```
candidate/
  runtime.env                    # ACTIVE_STRATEGY, STRATEGY_SWITCH_POLICY,
                                 # SAMSUNG_V4_BUILD_MODE (не хранит секретов;
                                 # токены остаются в .env вне репозитория)
  engine.json                    # категория C/D: риск-капы, исполнение,
                                 # скринер, тайминги, Telegram
  backtest.json                  # допущения A-1…A-13 симулятора
  strategies/
    __init__.py                  # STRATEGY_REGISTRY (явный dict)
    legacy_samsung_v4/
      strategy.py                # логика (перенос strategy.py 1:1)
      params.json                # категория A (база 9/21/100, 20/2, 14/30/70...)
      profiles.py                # FORCE_TRADE/SANDBOX_TEST/TECH_CHECK/CONSERVATIVE
      schema.py                  # схема: имя, тип, единицы, диапазон, кроссы
```

### 10.3. Пример итоговой конфигурации (§5 ТЗ)

`runtime.env`:

```
ACTIVE_STRATEGY=legacy_samsung_v4
STRATEGY_SWITCH_POLICY=BLOCK
SAMSUNG_V4_BUILD_MODE=SAFE_START
```

`engine.json` (категории C/D — значения соответствуют текущим FACT):

```json
{
  "risk": {
    "risk_per_trade": 0.01,
    "min_stop_loss_percent": 0.005,
    "stop_loss_percent": 0.012,
    "take_profit_ratio": 2.0,
    "atr_stop_multiplier": 1.5,
    "atr_period_intraday": 20,
    "max_atr_stop_percent": 0.03,
    "max_position_share_per_instrument": 0.2,
    "max_total_exposure": 0.6,
    "max_trades_per_instrument_per_day": 5,
    "commission_mode": "TRADER",
    "commission_per_side": 0.0005,
    "slippage_percent": 0.0002
  },
  "execution": {
    "trading_cycle_seconds": 30,
    "candles_lookback_days": 2,
    "candle_interval": "5min",
    "api_retry_count": 3,
    "api_retry_delay_seconds": 5,
    "api_request_timeout_seconds": 10,
    "api_call_delay_seconds": 0.03,
    "reconcile_confirm_min_age_seconds": 30,
    "be_trail_enabled": false,
    "be_trigger_r": 1.0,
    "trail_atr_period": 14,
    "trail_atr_multiplier": 3.0
  },
  "screener": {
    "top_volatile_instruments_count": 10,
    "volatility_period_days": 30,
    "volatility_refresh_hours": 24,
    "min_daily_turnover_rub": 10000000
  }
}
```

`strategies/legacy_samsung_v4/params.json` (категория A, вариант
CONSERVATIVE; значения = config.py:108-117, FACT):

```json
{
  "profile": "CONSERVATIVE",
  "params": {
    "ma_fast_period": 9,
    "ma_slow_period": 21,
    "trend_filter_ma_period": 100,
    "bb_period": 20,
    "bb_std_dev": 2,
    "rsi_period": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "min_candles_for_signal": 60,
    "adx_period": 14,
    "adx_trend_threshold": 25,
    "adx_hysteresis_candles": 2,
    "volume_spike_factor": 1.5,
    "volume_confirmation_window": 20
  }
}
```

### 10.4. Фиксация и защита конфигурации

1. Снапшот эффективной конфигурации (движок + стратегия + вариант +
   допущения backtest) строится при старте; `config_hash` = SHA256
   канонического JSON; пишется в `state.json` и печатается в журнал.
2. Конфигурация иммутабельна в рантайме (MappingProxyType).
3. При рестарте: несовпадение `config_hash` при наличии активных позиций ->
   входы запрещены до явного подтверждения оператора (аналог
   «state.json отсутствует — входы запрещены», main.py:5691-5696).
4. Каждая сделка/заявка/событие несёт `strategy_id` + `config_hash`
   (logger.py шапка, CSV-колонки, RECORD_FIELDS реестра,
   `TrackedPosition.strategy_id`).

---

## 11. Сохранение работоспособности (§6 ТЗ)

### 11.1. Совместимость по подсистемам

| Подсистема | Статус в проекте | Что именно |
|---|---|---|
| T-Invest API / клиент | СОХРАНЯЕТСЯ БЕЗ ИЗМЕНЕНИЙ | `tinkoff_client.py` целиком (fail-closed контракт, sandbox-only, идемпотентность order_id); новый adapter лишь оборачивает |
| Менеджер позиций (ExecutionMonitor) | АДАПТИРУЕТСЯ МИНИМАЛЬНО | + поле `TrackedPosition.strategy_id` (в конец dataclass, asdict-совместимо execution.py:303-306); ключ `positions[figi]` и инвариант «1 позиция на FIGI» НЕ меняются; check_all/apply_close_execution/per-order cursor — без изменений |
| Журнал заявок (OrderLedger) | АДАПТИРУЕТСЯ МИНИМАЛЬНО | `RECORD_FIELDS` + `strategy_id` В КОНЕЦ (практика append-в-конец уже применялась — order_ledger.py:73-83; старые записи читаются); append-only, INTENT-before-send, блокировки figi_blocks_buy — без изменений |
| Частичные исполнения | СОХРАНЯЕТСЯ БЕЗ ИЗМЕНЕНИЙ | partial-ветка main.py:5369-5471, poll_open_orders 4254-4537, register_executed_buy 3433-4240 — движок не переписывается |
| Восстановление после перезапуска | АДАПТИРУЕТСЯ МИНИМАЛЬНО | `_load_state/_save_state` + раздел `strategy_state` (§5.1); startup_recovery, В2/В3, RECOVERY-политика (запрет автозакрытия main.py:151-153) — без изменений |
| Telegram | СОХРАНЯЕТСЯ БЕЗ ИЗМЕНЕНИЙ | команды /start /stop /status управляют trading.flag (main.py:847-868, telegram_bot.py:52-107); опционально: /status выводит ACTIVE_STRATEGY |
| Система безопасности | СОХРАНЯЕТСЯ БЕЗ ИЗМЕНЕНИЙ | build_safety.py (Режим A/B, guard, sandbox-only), config.validate, SandboxRequiredError; backtest-сборка наследует guard (заявки физически невозможны) |
| Текущие тесты | СОХРАНЯЮТСЯ | 789 тестов (docs/INSTALLATION_RU.md §4 — факт владельца) прогоняются после каждого этапа; conftest-изоляция (conftest.py:187-227) переиспользуется; новые тесты — ДОБАВЛЯЮТСЯ, не заменяют |

### 11.2. Что сохраняется / адаптируется / выносится (сводка)

- **Без изменений (доказательство необходимости переписывания отсутствует):**
  INTENT-before-send (main.py:5300-5325), per-order cursor
  (execution.py:656-861), reconcile/В2/В3/startup_recovery
  (main.py:2018-2223, 4831-5108), fail-closed get_positions
  (tinkoff_client.py:315-435), тройной запрет LIVE, guard, атомарные записи
  state/CSV (main.py:1165-1167; logger.py), запрет фиктивного P&L,
  trading.flag, скринер (параметризация без смены логики).
- **Адаптируется (точечные правки):** main.py (создание стратегии через
  реестр 5663; вызов сигнала per-pair 5260; stop-distance в sizing 5278;
  exit-хук перед check_all 5135-5152; clock-инъекция), execution.py
  (+strategy_id), order_ledger.py (+strategy_id в конец), config.py
  (категории, валидатор; PROFILE-ветвление уходит в profiles.py legacy),
  logger.py (+strategy_id/config_hash в шапку).
- **Выносится в отдельные модули:** сигнальная логика ->
  `strategies/legacy_samsung_v4/strategy.py` (фасад в strategy.py на
  переходный период); SL/TP-расчёт -> контракт стратегии
  (`compute_exit_levels`), в risk_manager остаётся делегирование;
  профильные наборы -> `profiles.py`; интерфейс исполнения ->
  `execution_adapter.py`; симулятор -> `backtest/`.

Полное обоснование «почему не полный переписанный проект»: десять защитных
механизмов с proven-историей (Stage 1 CURRENT_ARCHITECTURE_MAP §7) не
имеют причин для переписывания; их сохранение — требование Stage 1.1 C-6 и
настоящего §6 ТЗ.

---

## 12. Связь с условиями C-1…C-7 Stage 1.1

| Условие Stage 1.1 | Как закрыто в проекте Stage 2 |
|---|---|
| C-1 модель изоляции состояния | принят предпочтительный вариант `state.strategy[id].instruments[figi].runtime_state` (§5.1); альтернатива задокументирована, решение-подтверждение — D-2 |
| C-2 exit-контракт | принят: типизированные решения §4.1/§4.2; SHORT-входы gated (движок long-only); различение SHORT-entry vs CLOSE_LONG — типами DecisionType |
| C-3 контракт стоп-дистанции | принят: `planned_stop_distance` -> sizing (§7.2); hard caps сохранены |
| C-4 статус legacy_samsung_v4 | принят: FROZEN, regression/compatibility only, не default (§8); профили — наборы параметров |
| C-5 допущения backtest A-1…A-13 + консервативное правило | приняты: §9.2–§9.3; версии «не моделируется» — явные |
| C-6 исправленные документы Stage 1 как актуальная редакция | использованы как основа (исправленные PARAMETER_USAGE_MAP / STRATEGY_SWITCH / BACKTEST_COMPATIBILITY_REQUIREMENTS); roadmap-дополнения R-S1.1-a…f интегрированы в этапы A–G |
| C-7 открытые вопросы Stage 1 | перенесены в STAGE2_OPEN_DECISIONS.md (Q-01, Q-03, Q-08, N-01, N-04 и др. — с рекомендациями) |

---

## 13. Итоговый статус проекта

- Все требования §3 ТЗ (3.1–3.5) покрыты конкретными контрактами;
  §4 — правилами моделирования и разделением слоёв; §5 — структурой
  конфигурации и примером; §6 — таблицей совместимости; §7 — картой
  изменений файлов; §8 — этапами A–G с PASS/FAIL/откатом; §9 — матрицей
  тестирования; §10 — разделением «подтверждено/предложение/владелец/проверка».
- Ключевые неопределённости, которые проектирование устранить не может,
  перечислены в STAGE2_OPEN_DECISIONS.md (раздел D — решения владельца,
  раздел V — дополнительная проверка). Они НЕ блокируют начало Этапа A
  (контракты/конфигурация без смены поведения), но БЛОКИРУЮТ этапы,
  которым соответствуют (указано в roadmap, колонка «зависимости»).
- Реализация не начиналась. Никакой код не написан и не изменён.

```
SOURCE CODE: UNCHANGED
TRADING: NOT EXECUTED
T-INVEST API: NOT ACCESSED
GITHUB: READ-ONLY
STAGE 2: DESIGN ONLY
```
