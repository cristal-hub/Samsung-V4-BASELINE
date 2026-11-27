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

**Статус этапа:** `STAGE 2.3.3 — EXIT PRICE SNAPSHOTS & MULTI-ATTEMPT
SLIPPAGE ACCOUNTING` (документ — версия 2.3.3: документационное
дополнение поверх версии 2.3.2; согласованные решения 2.3.1/2.3.2 НЕ
переписываются.
История версий: ред. 2.3.1 (ДВЕ критические коррекции аудита Stage 2.3):
(1) точка интеграции EmergencyExitController перенесена ДО точки отправки
первой закрывающей заявки — единый контролируемый маршрут выхода, прямой
вызов close_position из торгового цикла для защитных срабатываний удалён
из проекта (§6.2, §16, §17); (2) исправлено обоснование модели риска —
утверждение ред. 2.3 «фактическое входное проскальзывание уже содержится
в |exec_price - sl|» НЕВЕРНО при SL, рассчитанном от exec_price; полная
постановка — STAGE2_RISK_MODEL_FORMULAS.md (§7.4). Ред. 2.3.2 (ТРИ
коррекции аудита Stage 2.3.1): (1) устранено противоречие о статусе
close_position — ЕДИНСТВЕННЫЙ маршрут отправки уточнён разделением
сценариев A/B/C, инвариант ALL_BOT_SELL_SUBMISSIONS ⊆
EmergencyExitController.process_incidents() (§6.2, §16, §18);
(2) решения D-24/D-27 — обязательные без умолчаний: без письменно
принятого решения параметр UNCONFIGURED, этап H заблокирован (§16, §18);
(3) терминология фактической цены исполнения выхода унифицирована:
exit_exec_price для ВСЕХ типов выхода вместо stop_exec_price;
stop_execution_slippage_ps = max(0, sl_price - exit_exec_price) — только
для стоповых инцидентов (§7.4, §18). РЕД. 2.3.3 (Stage 2.3.3): добавлена
ЕДИНАЯ модель ценовых снимков закрытия — три уровня ценовых данных
(exit_decision_price фиксируется один раз; exit_attempt_snapshot перед
каждой попыткой; фактические исполнения — отдельно от снимков, только
подтверждения брокера), разделение проскальзывания
total_exit_slippage_ps / attempt_slippage_ps, восстановление ценовых
данных после перезапуска (R-10) и тесты ES-01…ES-14 (§6.2, §7.4, §16,
§19; маршрут отправки, FSM и политики НЕ изменяются). Правки
Stage 2.3/2.3.1/2.3.2 сохранены; разделы, не затронутые правками,
сохранены без изменений; перечень правок — STAGE2_3_3_CHANGELOG.md).

```
STAGE 2.3.3 — EXIT PRICE SNAPSHOTS & MULTI-ATTEMPT SLIPPAGE ACCOUNTING
DESIGN CORRECTIONS ONLY
SOURCE CODE: UNCHANGED
TRADING: NOT EXECUTED
T-INVEST API: NOT ACCESSED
GITHUB: READ-ONLY
NO LIVE ORDERS
FORCE_TRADE: NOT MIGRATED (решение владельца, Stage 2.2)
LEGACY PROFILES: NOT REQUIRED AS INITIAL CONFIGURATION (Stage 2.3)
EMERGENCY EXIT ARCHITECTURE — DESIGN ONLY
NO BROKER EXECUTION
NO PYTHON CODE CHANGES
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
| Документы Stage 2 | каталог `SAMSUNG_V4_STAGE2_IMPLEMENTATION_BLUEPRINT`, commit `c30af9d` (6 документов) | FACT |
| Документы Stage 2.1 | каталог `SAMSUNG_V4_STAGE2_1_CRITICAL_CORRECTIONS`, commit `f5db0d6` (7 документов) | FACT — проверено Stage 2.2: commit подтверждён на origin/main (fetch READ-ONLY + ls-tree) |
| Идентичность кода между commit (дополнение Stage 2.2) | `git diff 884cefd f5db0d6 -- candidate/ docs/` — пусто (0 изменений); все ссылки `файл:строка` редакций 2.0/2.1 действительны и для `f5db0d6` | FACT — проверено Stage 2.2 |
| Документы Stage 2.2 (дополнение Stage 2.3) | каталог `SAMSUNG_V4_STAGE2_2` на origin/main, commit `1f252dbc1f77d17bbe09e314714812176cc85c6b` (7 документов) | FACT — проверено Stage 2.3: `git fetch origin` READ-ONLY (обновлены ТОЛЬКО remote-tracking ссылки `f5db0d6..1f252db`); все 7 документов сверены с локальной копией побайтово (`git hash-object` — 7/7 MATCH) |
| Идентичность кода между commit (дополнение Stage 2.3) | `git diff 884cefd 1f252db -- candidate/ docs/` — пусто (0 изменений); все ссылки `файл:строка` редакций 2.0–2.2 действительны и для `1f252db` | FACT — проверено Stage 2.3 |

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

**Предусловие контракта evaluate_exit (Stage 2.2, исправление №2).**
Движок вызывает `evaluate_exit` ТОЛЬКО после шлюза валидности цены (§6.2):
`price` — валидное положительное конечное число, а `candles_df` — либо
лента `df_for_exit.get(figi)`, либо `None` при отсутствии ленты. Стратегия
НЕ обязана проверять цену на валидность и, по построению конвейера, НЕ
получает недействительную цену. Ответственность за валидацию цены —
НА движке, не на стратегии (стратегии не должны дублировать проверки
движка; повторная проверка допустима, но не является частью контракта).

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

### 6.2. Выходной конвейер: два списка выходов + шлюз валидности цены (исправлено Stage 2.1 и Stage 2.2)

**Исправление Stage 2.1 (замечание №1 проверки).** В редакции
2.0 стратегические выходы собирались в `to_close` ДО вызова check_all,
после чего следовал оператор `to_close = await monitor.check_all(...)` —
присваивание ПОЛНОСТЬЮ ОТБРАСЫВАЛО список стратегических выходов
(точка потери: main.py:5144 — присваивание результата check_all;
execution.py:986, 1022 — check_all строит и возвращает НОВЫЙ список).
Порядок инвертирован: сначала защитные выходы, затем стратегические
для оставшихся OPEN, объединение — ДОБАВЛЕНИЕМ списков, не присваиванием.

**Исправление Stage 2.2 (замечание №2 проверки).** Псевдокод шага 2б
редакции 2.1 обращался к ценам небезопасно; к реализации он НЕ
принимается:

```
# НЕПРИГОДНЫЙ образец (редакция 2.1) — НЕ реализовывать:
dec = owner.evaluate_exit(
    pos.view(),
    df_for_exit[pos.figi],     # KeyError, если ленты FIGI нет в словаре
    prices[pos.figi],          # KeyError, если FIGI нет в снимке цен
    owner.get_state(pos.figi))
pos.close_price_before_order = float(prices[pos.figi])   # тот же дефект
```

Оба прямых индексирования падают с KeyError на отсутствующем ключе, и
значение цены нигде не проверялось на валидность (None / 0 / отрицательное
/ NaN / ±Inf) до передачи в стратегию. Это не гипотетический сценарий —
контракт снимка цен (FACT, commit 884cefd):

- `get_last_prices` возвращает dict, в котором ФИЗИЧЕСКИ ОТСУТСТВУЮТ
  ключи FIGI, для которых брокер не дал цену (компоновка
  `if p.price is not None`, tinkoff_client.py:262-265); `{}` — при
  успешном пустом ответе (tinkoff_client.py:257); `None` — при ошибке API
  (tinkoff_client.py:256, 268);
- снимок `prices = {}` в цикле возможен штатно: main.py:5130-5133 при
  `prices is None` пишет `monitoring_error=True` и подставляет `{}`;
- защитный слой уже защищён: check_all применяет безопасный доступ
  `prices.get(pos.figi)` с проверкой `None / <= 0` и пропуском позиции
  (execution.py:994-997) — опасность существовала ТОЛЬКО в новом
  стратегическом шаге редакции 2.1;
- отдельная неполнота существующих проверок: сравнение `price <= 0` НЕ
  отсекает NaN и ±Inf (любое сравнение с NaN ложно), поэтому к проверкам
  `None/<= 0` добавляется `math.isfinite`. Прецеденты в коде:
  execution.py:1264 (`not math.isfinite(price) or price <= 0 -> None`),
  execution.py:1271-1288 (`_extract_commission`: NaN/±Inf -> None; 0.0 —
  ДОСТОВЕРНОЕ значение).

**Контракт шлюза валидности цены (PROPOSAL, Stage 2.2).** Один хелпер
движка, один и тот же код в шагах 2б и 2г:

```
def _valid_price(prices, figi):
    """Возвращает (price, None) либо (None, reason_code)."""
    if not prices:                              # None или {} — достоверно нет цен
        return None, "prices_empty"
    if figi not in prices:                      # get_last_prices МОЖЕТ опустить
        return None, "price_key_missing"        # ключ (tinkoff_client.py:262-265)
    raw = prices[figi]
    if raw is None:
        return None, "price_none"               # защита от нарушения контракта
    try:
        price = float(raw)
    except (TypeError, ValueError):
        return None, "price_not_finite"
    if not math.isfinite(price):
        return None, "price_not_finite"         # NaN / +Inf / -Inf
    if price <= 0:
        return None, "price_non_positive"       # 0 и отрицательные
    return price, None
```

Шлюз обязателен ДО вызова стратегии (требование исправления №2:
недействительная цена НЕ ДОЛЖНА достигать стратегии) и повторно на шаге
2г (защита в глубину для ОБОИХ списков — единый код проверки).

```
# шаг 2 trading_cycle (исправлено Stage 2.1 + Stage 2.2):

# 2а. ЗАЩИТНЫЕ выходы SL/TP/BE/TRAIL — ПЕРВЫМИ, контракт без изменений.
#     check_all сам применяет безопасный доступ к ценам
#     (execution.py:994-997: .get + None/<=0 -> monitoring_error + пропуск).
protective = await monitor.check_all(prices, extremes=..., atrs=...)

# 2б. СТРАТЕГИЧЕСКИЕ выходы — ТОЛЬКО для позиций, оставшихся OPEN,
#     ТОЛЬКО после шлюза валидности цены (Stage 2.2).
strategic = []
for pos in monitor.open_positions():           # helper E-2 (execution.py)
    price, price_err = _valid_price(prices, pos.figi)
    if price is None:                          # классы EP-1..EP-6 (таблица ниже)
        log_event("STRATEGY_EXIT_PRICE_INVALID", {
            "strategy_id": pos.strategy_id, "figi": pos.figi,
            "reason_code": price_err})
        continue          # решение НЕ принимается; НЕ pos-level UNCERTAIN
                          # (обоснование — таблица ниже); позиция остаётся
                          # OPEN, защита SL/TP не прерывается; заявка НЕ
                          # создаётся; повторная попытка в следующем цикле.
    df = df_for_exit.get(pos.figi)             # .get(), НЕ [..]: нет ленты ->
                                               # candles_df=None -> стратегия
                                               # ОБЯЗАНА вернуть HOLD (fail-
                                               # closed, STRATEGY_EXIT_DATA_MISSING)
    owner = strategies[pos.strategy_id]        # стратегия-автор позиции
    dec = owner.evaluate_exit(pos.view(), df, price, owner.get_state(pos.figi))
    log_event("STRATEGY_EXIT_DECISION", {      # reason_code в журнал
        "strategy_id": pos.strategy_id, "config_hash": config_hash,
        "decision": dec.type, "reason_code": dec.reason_code,
        "figi": pos.figi, "candle_time": dec.candle_time})
    if dec.type in {CLOSE_LONG, TIME_EXIT, STRATEGY_EXIT}:
        pos.state = PositionState.CLOSING      # та же маркировка, что 1017-1018
        pos.close_reason = dec.reason_code     # reason_code стратегии
        pos.close_price_before_order = price   # ВАЛИДИРОВАННАЯ цена
        strategic.append(pos)
    elif dec.type == PARTIAL_CLOSE:            # ОТЛОЖЕНО (D-7)
        raise EngineRefuse("partial_close_not_implemented")   # fail-closed

# 2в. ОБЪЕДИНЕНИЕ: добавление списков, НЕ присваивание; без дублирования.
#     ВСЕ причины сохраняются (Stage 2.3.1): pos.merged_close_reasons =
#     [защитные ...] + [стратегические ...] — защитное событие НЕ теряется
to_close = protective + [p for p in strategic
                         if p.state == PositionState.CLOSING]
# Инвариант INV-1 (assert в движке): пересечение списков пусто и
# len({p.figi for p in to_close}) == len(to_close).
# Корректность по построению:
#   - позиция из protective уже CLOSING -> не вошла в итерацию 2б;
#   - позиция, получившая стратегический CLOSING, не могла попасть в
#     protective: check_all уже выполнен (OPEN-фильтр execution.py:992
#     отработал до стратегического шага).
# Одна позиция закрывается МАКСИМУМ ОДИН раз за цикл в обоих направлениях.

# 2г. (ЗАМЕНА Stage 2.3.1) — передача решений контроллеру, БЕЗ заявок:
#     единый маршрут "Protective Stop Detection → Exit Decision /
#     EmergencyExitController → Exit Execution". Прямой вызов
#     close_position из цикла УДАЛЁН (аудит Stage 2.3: контроллер после
#     шага защитных выходов получал позицию, для которой рыночная SELL
#     УЖЕ отправлена (main.py:5152 → 2315), — гибридная последовательность
#     была недостижима; коррекция №1 ТЗ Stage 2.3.1).
for pos in to_close:
    price, price_err = _valid_price(prices, pos.figi)
    if price is None:                          # защита в глубину, включая
        pos.state = PositionState.UNCERTAIN    # NaN/±Inf (семантика
        client.uncertain_state = True          # main.py:5147-5151);
        continue                               # инцидент НЕ создаётся,
                                               # заявка НЕ отправляется
    controller.submit_exit_incident(           # ТОЛЬКО INTENT (персистенция
        pos,                                   # incident-намерения ДО любых
        reasons=pos.merged_close_reasons,      # действий) — НИКАКИХ заявок
        prices=prices)                         # на этом шаге

# 2д. (НОВЫЙ шаг Stage 2.3.1) — продвижение инцидентов: reconciliation →
#     первая попытка (лимитная для SL-инцидентов / для не-стоповых — ПО
#     РЕШЕНИЮ ВЛАДЕЛЬЦА D-24: ред. 2.3.2 — параметр ОБЯЗАТЕЛЬНЫЙ, без
#     письменно принятого решения UNCONFIGURED и этап H ЗАБЛОКИРОВАН,
#     умолчания НЕТ) → контроль исполнения → отмена/переустановка →
#     эскалация → подтверждение сверкой.
#     ВСЕ закрывающие заявки отправляются ТОЛЬКО здесь (контроллер) —
#     инвариант ред. 2.3.2: ALL_BOT_SELL_SUBMISSIONS ⊆
#     EmergencyExitController.process_incidents() (сценарии A/B/C — §16);
#     рыночная нога — через close_position как ИСПОЛНИТЕЛЬ внутри
#     контроллера (INTENT/_sell_block_reason сохраняются).
#     РЕД. 2.3.3: каждая попытка получает СОБСТВЕННЫЙ снимок цены
#     (exit_attempt_snapshot — НОВЫЙ attempt_id) непосредственно перед
#     INTENT/отправкой; старые снимки не переиспользуются; без валидного
#     снимка отправка не выполняется (fail-closed); фактические
#     исполнения хранятся ОТДЕЛЬНО от снимков (только подтверждения
#     брокера); модель ценовых данных — STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md §7а;
#     восстановление после перезапуска — R-10 (§6.5 того же документа).
controller.process_incidents(prices=prices)
```

**Семантика UNCERTAIN при недействительной цене — два уровня (Stage 2.2):**

| Шаг | Ситуация | Действие | Обоснование |
|---|---|---|---|
| 2б (оценка выхода) | цена FIGI отсутствует или невалидна | стратегия НЕ вызывается; событие STRATEGY_EXIT_PRICE_INVALID; позиция остаётся OPEN; заявки нет | состояние позиции ДОСТОВЕРНО известно (OPEN); перевод её в PositionState.UNCERTAIN исключил бы её из итерации check_all (фильтр `state != OPEN -> skip`, execution.py:992) и ОТКЛЮЧИЛ бы защиту SL/TP — единственный консервативный вариант: пропустить решение, СОХРАНИТЬ защиту, повторить в следующем цикле (тот же паттерн, что check_all execution.py:994-997) |
| 2г (передача в контроллер, ред. 2.3.1) | позиция УЖЕ решена к закрытию (любой список), цена на шаге передачи отсутствует или невалидна | СУЩЕСТВУЮЩИЙ механизм UNCERTAIN без изменений семантики (pos.state=UNCERTAIN + client.uncertain_state=True, main.py:5147-5151), дополненный math.isfinite; инцидент НЕ создаётся, заявка НЕ создаётся; reconciliation/восстановление сохраняются. Внутри контроллера при потере валидной цены в ходе инцидента действует политика D-22 | отправка SELL «вслепую» без валидной цены запрещена; исходная семантика UNCERTAIN предназначена именно для этого сценария |

Требования исправления №2 выполнены: (1) существование ключа проверяется
ДО вызова стратегии; (2) цена проверяется на валидное положительное
конечное число; (3) недействительная цена не достигает стратегии; (4) при
невозможности безопасно оценить/закрыть позицию действует UNCERTAIN-
механика (на шаге закрытия — существующая, на шаге оценки — пропуск
решения с сохранением защиты: обоснование в таблице выше); (5) заявка на
закрытие по недействительной цене не создаётся ни на одном шаге; (6)
последующие сверка (reconcile) и восстановление состояния сохранены без
изменений.

**Классы валидности цены (Stage 2.2; тесты EP-1..EP-7 —
STAGE2_TEST_MATRIX.md §1а):**

| Класс | Сценарий (входные данные шлюза) | Ожидаемое поведение конвейера |
|---|---|---|
| EP-1 | ключ FIGI отсутствует в prices (ШТАТНЫЙ случай: get_last_prices опускает FIGI без цены, tinkoff_client.py:262-265) | reason_code=price_key_missing; стратегия не вызвана; заявок нет; позиция OPEN; цикл продолжается |
| EP-2 | prices == {} (успешный ответ без цен) или prices is None (ошибка API -> {} + monitoring_error, main.py:5130-5133) | reason_code=prices_empty; заявки не создаются ни в одном списке; цикл не падает; monitoring_error=True |
| EP-3 | значение цены None (нарушение контракта адаптером — защита в глубину) | reason_code=price_none; как EP-1 |
| EP-4 | цена == 0 (0.0) | reason_code=price_non_positive; как EP-1 |
| EP-5 | цена < 0 (отрицательная) | reason_code=price_non_positive; как EP-1 |
| EP-6 | цена NaN / +Inf / -Inf (существующие проверки `<= 0` NaN НЕ отсекают) | reason_code=price_not_finite; как EP-1; на шаге 2г -> UNCERTAIN без заявки |
| EP-7 | цена валидна (положительное конечное число) | полный штатный путь: решение -> (при CLOSE_*) -> close_position с этой ценой |

Каждый из EP-1..EP-6 обязан доказывать: исключений НЕТ (цикл НЕ падает),
брокерских заявок НЕТ (в ledger не появляется SELL INTENT), событие с
reason_code записано, позиция остаётся в итерации защитной проверки.
EP-7 — контрольный положительный класс.

**Почему защитный выход идёт первым (приоритет защиты):**

1. Защиту нельзя отложить на цикл: SL/TP — безусловный слой движка,
   контракт check_all сохраняется (execution.py:978-1022 не меняется).
2. Приоритет при одновременном срабатывании реализуется ПОРЯДКОМ, а не
   логикой слияния: позиция, закрытая защитно (CLOSING), вообще не доходит
   до стратегической оценки — в журнале остаётся защитная причина
   (TP/SL/BE/TRAIL), стратегический reason_code не затирает её.
3. Стратегический выход НЕ теряется: для позиций, оставшихся OPEN,
   решение применяется в том же цикле (шаг 2б) и закрывается штатным
   close_position.

**Что сохраняется без изменений (проверено по коду commit 884cefd):**

- `close_position` (main.py:2224-2376): полное количество (2315),
  INTENT-before-send для SELL (2254-2280), запрет повторной SELL
  (_sell_block_reason: 738-767; проверка 2235-2252), state=None ->
  UNCERTAIN (2320-2326). РЕД. 2.3.1: close_position вызывается ТОЛЬКО
  контроллером (исполнитель рыночной ноги инцидента — единый маршрут,
  §16/§17); прямой вызов из торгового цикла для to_close УДАЛЁН из
  проекта (коррекция №1 аудита Stage 2.3; точка отправки первой SELL
  была main.py:5152 → 2315). РЕД. 2.3.2 (КОРРЕКЦИЯ №1 — устранение
  противоречия ред. 2.3.1): формулировка «и существующими механизмами
  В3/операторских закрытий» ИСПРАВЛЕНА — close_position НЕ является
  самостоятельным маршрутом отправки ни в одном сценарии:
  (а) механизм В3 заявок НЕ отправляет вообще — это обнаружение внешнего
  закрытия сверкой (main.py:1932-2011) и закрытие учёта
  (main.py:1462-1492); (б) команда оператора через интерфейс бота
  (сценарий C, §16) — программное действие и обязана проходить через
  Exit Incident и process_incidents(); (в) инвентаризация вызовов
  close_position по коду: единственный вызов main.py:5152 (удаляется
  этапом H). Инвариант ред. 2.3.2: ALL_BOT_SELL_SUBMISSIONS ⊆
  EmergencyExitController.process_incidents().
- Причина закрытия попадает в журнал автоматически: `pos.close_reason`
  (для стратегического выхода = reason_code стратегии) пишется в ledger
  INTENT как `close:{pos.close_reason}` (main.py:2271-2275) и в
  CSV-строку закрытия штатным process_closing (main.py:2835; вызов 5155).
- UNCERTAIN-обработка недоступной цены (5147-5151) распространяется на
  ОБА списка: позиция из `strategic` с недоступной ценой получает
  UNCERTAIN на шаге 2г, а не отправку «вслепую»; Stage 2.2 дополняет
  проверку `math.isfinite` (NaN/±Inf теперь тоже UNCERTAIN, не заявка).
- RECOVERY-позиции стратегическими выходами НЕ затрагиваются:
  evaluate_exit вызывается только для OPEN; запрет автозакрытия RECOVERY
  (main.py:151-153, 4684-4686) сохранён.
- Входной SELL-сигнал по-прежнему НЕ является закрытием LONG (§6.1):
  закрытие LONG инициируют только ExitDecision (шаг 2б) и защитные
  SL/TP (шаг 2а) — SELL из входного контракта в конвейер выхода не
  попадает.

**Семантика данных шага 2б.** `df_for_exit` — лента 5-мин свечей по FIGI
открытых позиций, строится один раз за цикл. Доступ — ТОЛЬКО через
`df_for_exit.get(figi)` (Stage 2.2): если ленту получить не удалось
(FIGI отсутствует в словаре), стратегия получает `candles_df=None` и
ОБЯЗАНА вернуть HOLD (fail-closed; событие STRATEGY_EXIT_DATA_MISSING).
Для legacy evaluate_exit всегда возвращает HOLD (владелец выходов —
SL/TP движка, §4.2); манифест legacy декларирует отсутствие потребности
в exit-свечах, движок вызывает evaluate_exit с `candles_df=None` — ноль
дополнительных запросов. Для будущих стратегий стоимость: максимум один
`get_historical_candles` на открытую позицию за цикл.

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
5. **Консистентность sizing↔SL/TP и контроль фактического риска** —
   единицы planned_stop_distance, ценовая база расчёта, влияние
   last_price vs exec_price, допустимое отклонение исполнения и
   поведение при превышении риск-бюджета определены ЯВНО в §7.4
   (дополнение Stage 2.1, замечание №3; торговая политика владельца не
   изобретается — варианты в OPEN_DECISIONS D-14/D-15). Наблюдаемость
   расхождения: событие STOP_SIZING_MISMATCH (не блокирует регистрацию
   подтверждённого исполнения — Дефект №7 main.py:4068-4084 сохраняется).
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

### 7.4. Единицы, ценовая база и модель расчётного риска с отдельным учётом проскальзывания при исполнении стопа (Stage 2.1–2.3; модель пересмотрена Stage 2.3)

Дополнение по замечанию №3 независимой проверки (Stage 2.1). Stage 2.2
(исправление №3) устранил неоднозначность члена `friction_actual`:
каждый член получил источник и единицы. Независимый аудит Stage 2.2
(коррекция №2) обнаружил КОНЦЕПТУАЛЬНУЮ ошибку модели: утверждение
редакции 2.2 «фактическое проскальзывание уже зафиксировано разностью
|exec_price - sl|» верно ТОЛЬКО для проскальзывания ВХОДА (смещение цены
заполнения входа относительно цены решения) и НЕ покрывает
проскальзывание при исполнении СТОПА: цена может перескочить через
стоп, ближайшая доступная цена может быть значительно хуже стоп-цены,
заявка может исполниться частично или не исполниться вовсе. Разница
между ценой входа и стопом является ПЛАНОВЫМ УБЫТКОМ сценария
«исполнение по стоп-цене» и НЕ является резервом на неблагоприятное
исполнение стопа. Stage 2.3 устраняет ошибку: модель разделяет три
величины в три момента времени и вводит ОТДЕЛЬНЫЙ резерв
неблагоприятного исполнения стопа (конфигурационная величина — D-16,
значение НЕ изобретается). Stage 2.3.1 (последующий аудит): утверждение
«верно ТОЛЬКО для проскальзывания ВХОДА» тоже НЕВЕРНО, когда SL
рассчитывается от exec_price — расстояние `|exec_price - sl|`
характеризует риск движения от входа до стопа, а не отклонение
исполнения от решения; четыре ценовые величины и исправленное
обоснование — STAGE2_RISK_MODEL_FORMULAS.md §2 и п. 3 ниже.

**Единицы planned_stop_distance.** Положительное число в ЦЕНОВЫХ ЕДИНИЦАХ
инструмента — рублей на ОДНУ акцию (шт. базового актива), НЕ проценты и
НЕ деньги на лот. Обоснование: только такие единицы делают формулу
`per_share_risk = planned_stop + friction` размерно корректной без
дополнительных множителей (friction тоже на акцию — risk_manager.py:125).
Пример: STOP_LOSS_PERCENT=0.012, last_price=200.0 -> planned_stop = 2.4.
Санитарный инвариант движка: `0 < planned_stop_distance < last_price`
(дистанция, сопоставимая с ценой или больше её, означает перепутанные
единицы — отказ входа, fail-closed; дополняет инварианты п. 4 §7.2).

**Ценовая база расчёта.** Дистанция формируется на МОМЕНТ РЕШЕНИЯ от
`last_price` — снимка `get_last_prices` (main.py:5128, 5278; база текущего
кода risk_manager.py:124). SL/TP при регистрации считаются от `exec_price`
(main.py:4072, 4808; risk_manager.py:238): так работает код сегодня —
контракт фиксирует это, а не меняет.

**Влияние last_price vs exec_price (два фактических эффекта):**

1. Дистанция стопа зафиксирована на момент решения; фактическая дистанция
   `|exec_price - sl|` отличается, если цена исполнения сместилась
   относительно last_price (движение цены между решением и заполнением).
   exec_price извлекается из отчётов брокера (main.py:4348, 4799, 5414,
   5458, 5474, 5539, 5598).
2. friction в sizing считается от last_price (risk_manager.py:125),
   фактическая комиссия — от exec_price (main.py:2464-2489,
   commission_source; execution.py:1271).

Оба эффекта сегодня существуют молча; контракт делает их НАБЛЮДАЕМЫМИ.

3. **(Stage 2.3; ОБОСНОВАНИЕ ИСПРАВЛЕНО Stage 2.3.1)** член
   `SLIPPAGE_PERCENT` планового friction (risk_manager.py:125) — плановое
   ожидание ВХОДНОГО проскальзывания (смещение цены заполнения входа
   относительно `last_price`), учитываемое В SIZING-ЗНАМЕНАТЕЛЕ. Он НЕ
   относится к проскальзыванию при исполнении стопа и в открытый
   расчётный риск (после регистрации) вторым членом НЕ добавляется.
   ИСПРАВЛЕНИЕ Stage 2.3.1: обоснование ред. 2.3 «фактическое входное
   смещение уже внутри `|exec_price - sl|`» НЕВЕРНО, когда SL
   рассчитывается от exec_price (main.py:4072 → risk_manager.py:238/246 —
   так работает код): тогда `|exec_price - sl| = exec_price * max(...)`
   характеризует риск ДВИЖЕНИЯ от фактической цены входа до стопа и
   содержит от входного проскальзывания только долю, пропорциональную
   стоп-проценту. Член НЕ добавляется по ДРУГОЙ причине: прогноз убытка
   при исполнении стопа измеряется ОТ фактической цены входа; входное
   проскальзывание — САМОСТОЯТЕЛЬНАЯ величина сравнения «исполнение vs
   решение» (`entry_slippage_ps = exec_price - decision_price`,
   публикуется отдельным полем); добавление её к сумме, начинающейся с
   exec_price, — двойной учёт. Полная постановка —
   STAGE2_RISK_MODEL_FORMULAS.md §2, §6 (правило DC-2), числовая
   демонстрация — §8 того же документа.

**Три величины риска — три момента времени (терминология Stage 2.3):**

| Величина | Момент | Состав | Поля журнала |
|---|---|---|---|
| **ESTIMATED RISK** — расчётный риск | ДО входа | прогноз убытка: плановое расстояние до стопа + плановые комиссии обеих сторон + ОТДЕЛЬНЫЙ резерв на неблагоприятное исполнение стопа | `estimated_risk_per_share`, `estimated_risk_total` |
| **OPEN ESTIMATED RISK** — открытый расчётный риск | ПОСЛЕ регистрации входа, до выхода | прогноз остаточного убытка при срабатывании стопа: фактическое расстояние `\|exec_price - sl\|` + фактическая/оценочная комиссия входа + оценочная комиссия выхода + ОТДЕЛЬНЫЙ резерв на неблагоприятное исполнение стопа | `open_risk_per_share`, `open_risk_total` |
| **REALIZED LOSS** — фактический убыток | ПОСЛЕ фактического выхода | фактический финансовый результат: реальные цены исполнения ВСЕХ частей заявки + фактические комиссии обеих сторон (существующий учёт закрытия, main.py:2464-2489) | `realized_loss_per_share`, `realized_loss_total` |

**Запреты терминологии (аудит Stage 2.2, коррекция №2.4):**

- прогнозируемый риск (до входа) и открытый расчётный риск (после входа)
  НЕ называются «actual risk» — слово «actual» резервируется за
  ФАКТИЧЕСКИ исполненными величинами (цена исполнения, комиссия);
  термин `actual_per_share_risk` редакции 2.2 ВЫВЕДЕН ИЗ УПОТРЕБЛЕНИЯ
  и заменён `open_per_share_risk`;
- расчётный риск с резервом — ПРОГНОЗ для наблюдаемости и лимитов, НЕ
  гарантированный предел убытка; предполагаемое проскальзывание
  НЕ выдаётся за гарантированный предел: гэп, остановка торгов,
  отказ брокера или неисполнение могут дать убыток, ПРЕВЫШАЮЩИЙ любую
  плановую оценку (ограничения — STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md
  §7);

**Формула расчётного риска ДО входа (Estimated risk; Stage 2.3):**

```
planned_stop_dist_ps     = planned_stop_distance          # цена/акцию — стратегия (§7.2)
planned_entry_comm_ps    = entry_ref_price * COMMISSION_PER_SIDE   # плановая комиссия входа, цена/акцию
planned_exit_comm_ps     = (entry_ref_price - planned_stop_dist_ps)
                           * COMMISSION_PER_SIDE          # плановая комиссия выхода:
                                                           # база — ожидаемая цена выхода
                                                           # у стопа (вход минус расстояние)
stop_slippage_reserve_ps = STOP_SLIPPAGE_RESERVE          # РЕЗЕРВ на неблагоприятное
                                                           # исполнение стопа, цена/акцию —
                                                           # КОНФИГУРАЦИОННАЯ величина (D-16);
                                                           # значение НЕ изобретается:
                                                           # до решения владельца член = 0
                                                           # с пометкой slippage_reserve_source=
                                                           # "unconfigured"
estimated_per_share_risk = planned_stop_dist_ps
                         + planned_entry_comm_ps
                         + planned_exit_comm_ps
                         + stop_slippage_reserve_ps       # цена/акцию
estimated_risk_total     = estimated_per_share_risk * planned_shares   # рублей
```

где `entry_ref_price` = `last_price` на момент решения (база sizing,
main.py:5278; risk_manager.py:124). `planned_shares` — плановое
количество акций рассчитанного размера позиции.

**Правила недопущения двойного учёта (Stage 2.3):**

1. Входное проскальзывание учитывается ОДИН раз — членом
   `SLIPPAGE_PERCENT` планового friction (risk_manager.py:125, входит в
   sizing); вторым членом в `estimated_per_share_risk` НЕ добавляется.
2. Выходное проскальзывание у стопа учитывается ОДИН раз — членом
   `STOP_SLIPPAGE_RESERVE`. Расстояние до стопа и резерв — РАЗНЫЕ члены:
   расстояние описывает плановый сценарий (исполнение по стоп-цене),
   резерв — неблагоприятный сценарий (исполнение хуже стоп-цены).
3. Комиссии — по одному разу на каждую сторону (вход и выход); замена
   плановых комиссий фактическими происходит ровно на границах
   исполнения (см. ниже).
4. `SLIPPAGE_PERCENT` и `STOP_SLIPPAGE_RESERVE` — независимые величины
   с РАЗНЫМИ носителями риска (вход/выход); объединение их в один член
   запрещено.

**Открытый расчётный риск ПОСЛЕ регистрации (Open estimated risk;
уточнение формулы Stage 2.2).** При регистрации подтверждённого
исполнения (main.py:4091-4105; точка применения находится под гейтом
`exec_price is not None and exec_price > 0` — main.py:4066) движок
вычисляет ВСЕ члены из однозначно определённых источников:

```
shares                = executed_lots * lot_size
  # executed_lots — подтверждённое исполнение (main.py:4103);
  # lot_size — из get_instrument_info (risk_manager.py:114-117, гейт
  # lot_size <= 0 -> блокировка ещё в sizing); shares > 0 по построению.

entry_commission_ps =
    entry_actual_commission / shares        # рублей на акцию
                                            # ЕСЛИ фактическая комиссия входа
                                            # получена от брокера:
                                            # pos.entry_actual_commission
                                            # (main.py:4105; извлечение из
                                            # состояния заявки —
                                            # execution.py:1271-1288, где 0.0 —
                                            # ДОСТОВЕРНЫЙ факт «комиссия
                                            # нулевая», а NaN/±Inf -> None);
  | exec_price * COMMISSION_PER_SIDE        # рублей на акцию
                                            # ИНАЧЕ (значение не подтверждено):
                                            # оценка моделью. НЕ ноль и НЕ
                                            # пропуск члена.

exit_commission_ps = sl_price * COMMISSION_PER_SIDE    # рублей на акцию
  # ОЦЕНКА выходной стороны на момент регистрации: позиция ещё открыта,
  # фактической выходной комиссии НЕ СУЩЕСТВУЕТ.
  # БАЗА ИЗМЕНЕНА Stage 2.3.1 (было exec_price — ред. 2.3): сценарий,
  # риск которого оценивается, — «исполнение по ЗАРЕГИСТРИРОВАННОМУ
  # стопу», поэтому комиссия выхода оценивается от СЦЕНАРНОЙ цены
  # выхода sl_price (та же база, что у плановой формулы до входа —
  # (decision_price - planned_stop_dist)). База exec_price завышала
  # оценку для BUY и не совпадала со сценарием прогноза (требование
  # соответствия величины её экономическому смыслу — §4.6 ТЗ 2.3.1).
  # При фактическом закрытии учёт ПЕРЕСЧИТЫВАЕТСЯ фактическим результатом
  # (main.py:2464-2489: фактическая комиссия с обеих сторон,
  # классификация commission_source actual/mixed/model); регистрационная
  # оценка НИКОГДА не считается итоговым P&L (запрет фиктивного P&L
  # сохраняется).

stop_slippage_reserve_ps = STOP_SLIPPAGE_RESERVE
  # ТОТ ЖЕ резерв, что в плановой формуле (D-16, цена/акцию).
  # Резерв покрывает неблагоприятное исполнение стопа В БУДУЩЕМ — оно НЕ
  # содержится ни в |exec_price - sl|, ни во входном проскальзывании
  # (коррекция №2 аудита Stage 2.2; уточнение ред. 2.3.1 —
  # STAGE2_RISK_MODEL_FORMULAS.md §2).

open_per_share_risk = |exec_price - sl|
                    + entry_commission_ps
                    + exit_commission_ps
                    + stop_slippage_reserve_ps   # руб./акцию
risk_budget         = balance * RISK_PER_TRADE   # рублей
open_risk_total     = open_per_share_risk * shares   # рублей
```

Двойной учёт входного проскальзывания исключён (Stage 2.3.1): член
`SLIPPAGE_PERCENT` в `open_per_share_risk` НЕ добавляется — НЕ потому,
что смещение «уже внутри |exec_price - sl|» (утверждение ред. 2.3
НЕВЕРНО при SL от exec_price — STAGE2_RISK_MODEL_FORMULAS.md §2), а
потому, что прогноз убытка при стопе определён ОТ фактической цены
входа; входное проскальзывание публикуется ОТДЕЛЬНЫМ полем
`entry_slippage_ps = exec_price - decision_price` и в сумму не входит
(правило DC-2). Член `friction_actual` редакции 2.2 разложен на явные
слагаемые: `entry_commission_ps + exit_commission_ps +
stop_slippage_reserve_ps`.

**Realized loss (после выхода; Stage 2.3).** Фактический убыток
вычисляет СУЩЕСТВУЮЩИЙ учёт закрытия (main.py:2464-2489): реальные цены
исполнения всех частей заявки (`avg_exec_price` — execution.py:788,
830; main.py:2754), фактические комиссии обеих сторон, классификация
`commission_source` (actual/mixed/model). Открытый расчётный риск
заменяется фактическим результатом ровно на границе фактического
закрытия; partial-исполнение не является закрытием — учёт продолжается
для остатка (механики partial-ветки main.py:5369-5471 сохранены;
аварийный выход — STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md, этапы E/F).

Происхождение комиссионных членов фиксируется в событии (поле
`risk_commission_source`): "actual" — обе части фактические; "mixed" —
фактическая входная + модельная выходная оценка; "model" — обе модельные
(классификация зеркальна commission_source учёта CSV — main.py:2484-2489);
происхождение резерва — полем `slippage_reserve_source`
("configured"/"unconfigured"). Результат пишется в журнал (поля
`estimated_risk_per_share`, `estimated_risk_total`, `open_risk_per_share`,
`open_risk_total`, `stop_sizing_deviation`, `risk_commission_source`,
`slippage_reserve_source`, `decision_price`, `exec_price`, `sl_price`,
`entry_slippage_ps`; после выхода — РЕД. 2.3.2 (КОРРЕКЦИЯ №3 —
терминология унифицирована, STAGE2_RISK_MODEL_FORMULAS.md §3):
`exit_decision_price` (цена на момент решения о выходе; РЕД. 2.3.3 —
первоначальная цена, записывается ОДИН раз при создании инцидента,
неизменяема — не меняется попытками, reconciliation'ом и перезапуском),
`exit_exec_price` (фактическая цена исполнения выхода — ЕДИНАЯ величина
для ВСЕХ типов выхода: SL/TP/BE/TRAIL/стратегический/аварийный;
средневзвешенная по всем подтверждённым частям),
`total_exit_slippage_ps` (= exit_decision_price - exit_exec_price;
относительно первоначального решения — РЕД. 2.3.3), attempt-метрики
попыток (`attempt_exit_exec_price` — средневзвешенная цена подтверждённых
исполнений попытки; `attempt_slippage_ps` = attempt_snapshot_price -
attempt_exit_exec_price; попытки без исполнений — NOT_APPLICABLE —
РЕД. 2.3.3), `stop_execution_slippage_ps = max(0, sl_price -
exit_exec_price)` — ТОЛЬКО для стоповых инцидентов (SL-триггер); для
остальных типов выхода поле = NOT_APPLICABLE, а не искусственно
рассчитанное значение, — в SIGNAL/EXIT-событиях и CSV. Термин ред. 2.3.1
`stop_exec_price` ВЫВЕДЕН ИЗ УПОТРЕБЛЕНИЯ (был некорректен как
универсальная цена закрытия для не-стоповых выходов); термин ред. 2.3.2
`exit_slippage_ps` ВЫВЕДЕН ИЗ УПОТРЕБЛЕНИЯ ред. 2.3.3 (заменён парой
total/attempt — STAGE2_RISK_MODEL_FORMULAS.md §3). ЦЕНОВЫЕ СНИМКИ
(РЕД. 2.3.3): каждая попытка получает собственный НЕИЗМЕНЯЕМЫЙ снимок
exit_attempt_snapshot непосредственно перед отправкой (attempt_id,
snapshot_price, price_source, price_valid; старый снимок не
переиспользуется; без валидного снимка отправка не выполняется —
fail-closed; STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md §7а). ЧАСТИЧНЫЕ
ИСПОЛНЕНИЯ ВЫХОДА: каждое подтверждённое исполнение хранится отдельно
(количество+цена, append-only, со связью attempt_id/order_request_id);
итоговая цена — средневзвешенная; цена отправленной заявки НЕ считается
ценой исполнения; цена отменённой заявки НЕ считается исполнением;
неизвестная цена исполнения НЕ заменяется ценой решения или ценой
заявки (прецедент В3: price_confirmed=False → CSV без P&L,
main.py:1975-2011 — STAGE2_RISK_MODEL_FORMULAS.md §5.5).
ЕДИНИЦЫ, ВРЕМЕННАЯ ТОЧКА РАСЧЁТА, ИСТОЧНИК КАЖДОГО ПАРАМЕТРА,
ОБРАБОТКА НЕИЗВЕСТНЫХ ЗНАЧЕНИЙ, ЗАПРЕТЫ ДВОЙНОГО УЧЁТА (МАТРИЦА
DC-0…DC-8), РАЗМЕРНАЯ КОРРЕКТНОСТЬ И ЧИСЛОВОЙ ПРИМЕР —
STAGE2_RISK_MODEL_FORMULAS.md (§4.6 ТЗ).
Согласование sizing и risk reporting (в т.ч. разница знаменателя sizing
и прогноза модели, вопрос включения резерва в sizing — D-28) —
STAGE2_RISK_MODEL_FORMULAS.md §7.
Регистрация подтверждённого исполнения НИКОГДА не блокируется контролем
(Дефект №7, main.py:4068-4084 — сохраняется).

Краевые случаи (fail-safe; регистрация не блокируется ни одним из них):

| Случай | Поведение |
|---|---|
| sl/tp не рассчитаны (RECOVERY-позиция: ошибка расчёта SL/TP или отсутствие свечей, main.py:4068-4084, 4086-4088) | контроль риска НЕ применяется; событие RISK_CONTROL_NOT_APPLICABLE {figi, cause: "no_sl_tp"}; регистрация НЕ блокируется |
| фактическая комиссия входа не получена (None) | член заменяется модельной оценкой `exec_price * COMMISSION_PER_SIDE`; risk_commission_source="model"; ноль НЕ подставляется (0.0 от брокера — достоверный факт и обрабатывается как факт, execution.py:1272-1275) |
| STOP_SLIPPAGE_RESERVE не сконфигурирован (решение D-16 не принято) | член = 0 с явной пометкой slippage_reserve_source="unconfigured"; оценка остаётся ПРОГНОЗОМ без резерва и НЕ выдаётся за предел убытка; произвольное числовое значение НЕ подставляется (мандат NO THRESHOLD IS OPTIMIZED) |
| NaN/±Inf в любом исходном члене | член трактуется как отсутствующий (прецедент execution.py:1276-1285) -> модельная оценка; при невозможности расчёта -> RISK_CONTROL_NOT_APPLICABLE; NaN в журнал не попадает |
| decision_price/exec_price/sl_price отсутствуют или некорректны (None/<=0/NaN — Stage 2.3.1, RM-14) | модель СООТВЕТСТВУЮЩЕЙ фазы не рассчитывается: нет фактов — нет прогноза; подстановка нуля или «удобного» значения запрещена; регистрационные механики не блокируются |
| shares <= 0 | невозможны по построению (гейты main.py:4066; risk_manager.py:114-117); assertion в движке |

**Допустимое отклонение цены исполнения.** На этапе D движок фиксирует
отклонение `stop_sizing_deviation = |actual_dist - planned_stop| /
planned_stop` (где `actual_dist = |exec_price - sl|`; деление на ноль
исключено инвариантом `planned_stop > 0`, §7.2 п. 4) в журнале БЕЗ
жёсткого лимита (режим наблюдения v1). Жёсткий допуск
(`max_execution_price_deviation` в engine.json, категория C) вводится
ТОЛЬКО после решения владельца D-14; молчаливого значения по умолчанию
нет (§10.1 п. 6).

**Поведение при превышении риск-бюджета.** Событие
`RISK_BUDGET_EXCEEDED` (поля estimated/open/planned/budget) пишется при
`open_risk_total > risk_budget`. Реакция в v1 — журналирование
(наименьшее вмешательство; сохраняет торговое поведение и мандат
STRATEGY LOGIC: UNCHANGED). Усиление — предупреждение оператору, запрет
новых входов по FIGI, сокращение позиции — ТОЛЬКО решение владельца
(D-15) с явными последствиями каждого варианта; автоматическое
сокращение позиции без решения владельца не проектируется. Превышение
открытого расчётного риска при ГЭПЕ (фактическая цена уже ниже стопа) —
сценарий аварийного выхода (PROTECTIVE_STOP_DETECTED с breach_depth,
STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md этап A; ред. 2.3.1 — событие
переименовано из STOP_GAP_BREACH), не часть этой политики.

---

## 8. Старая стратегия: `legacy_samsung_v4` (§3.5 ТЗ)

**ПРОЕКТ** (реализует условие C-4 Stage 1.1; ПЕРЕРАБОТАНО Stage 2.2 —
решение владельца о полном отказе от FORCE_TRADE).

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
2. Профили SANDBOX_TEST/TECH_CHECK/CONSERVATIVE — FACT: наборы параметров
   ОДНОЙ логики (config.py:88-117 переприсваивает 9 констант;
   strategy.py без ветвления по профилю). В проекте — вариантные наборы
   (`profiles.py`) внутри `legacy_samsung_v4`, значения НЕ меняются
   (таблица Stage 1 INVENTORY §2 сохраняется ЗА ВЫЧЕТОМ FORCE_TRADE).
   Профиль FORCE_TRADE НЕ переносится — ИСКЛЮЧЁН решением владельца
   (Stage 2.2, §2 STAGE2_2_CHANGELOG.md):
   - не мигрирует в новый движок и не является исполняемым режимом
     legacy;
   - его параметры НЕ влияют на конфигурацию, валидацию и исполнение
     новых стратегий;
   - совместимость нового движка с FORCE_TRADE НЕ требуется;
   - валидатор НЕ имеет для него (как и для любого профиля) исключений;
   - в исходном коде НИЧЕГО не изменяется (config.py:76-87 остаётся
     историческим фактом commit 884cefd, задокументированным Stage 1/2.1).
   **НОВЫЙ ДВИЖОК НЕ ТРЕБУЕТ ВЫБОРА СТАРОГО ПРОФИЛЯ (Stage 2.3,
   решение владельца — расширение решения Stage 2.2 о FORCE_TRADE на
   ВСЕ старые профили):** ни SANDBOX_TEST, ни TECH_CHECK, ни
   CONSERVATIVE не являются обязательными профилями нового движка,
   не определяют начальные параметры новой стратегии, не становятся
   стратегией по умолчанию и не блокируют переход к реализации новой
   архитектуры. Профили могут упоминаться ТОЛЬКО как исторические
   элементы исходного Samsung V4 и/или объекты регрессионного
   сравнения legacy-миграции (golden-тесты), если это действительно
   необходимо. Старый код допускается использовать для проверки
   механики, безопасности, исполнения и регрессии — НЕ как торговую
   стратегию-кандидата нового движка и НЕ как источник обязательных
   параметров. Выбор ПЕРВОЙ НОВОЙ стратегии — ОТДЕЛЬНОЕ будущее
   решение владельца ПОСЛЕ создания движка и исследования кандидатов
   (D-13, редакция Stage 2.3). Новые стратегии НЕ наследуют
   имена профилей legacy и НЕ строятся на значениях legacy-профилей:
   каждый params.json определяется собственной логикой стратегии и
   валидируется её собственной схемой (§10.1).
3. Позиции legacy в режиме INHERIT сопровождаются экземпляром
   `legacy_samsung_v4`; его «exit-правила» — сохранённые SL/TP/BE/TRAIL
   механики движка, НЕ новая оптимизация (Stage 1.1 §7).

---

## 9. BACKTEST и SANDBOX: три уровня и адаптеры (§4 ТЗ)

### 9.1. ExecutionAdapter — интерфейс исполнения (инвентаризация Stage 2.1)

**Исправление Stage 2.1 (замечание №5 проверки):** инвентаризация
выполнена заново по ВСЕМ точкам вызова клиента в main.py, execution.py
И risk_manager.py (риск-менеджер тоже зависит от клиента — в редакции
2.0 это не было показано) плюс карта всех публичных методов
tinkoff_client.py. Интерфейс объявляется полным только относительно
реально существующих точек вызова; методы без производственных вызовов
перечислены отдельно.

| Операция | Точки вызова (файл:строка, commit 884cefd) | Backtest-реализация |
|---|---|---|
| `get_last_prices(figis)` | main.py:1969, 5128; risk_manager.py:181 | цена свечи на момент решения |
| `get_historical_candles(figi, days, interval)` | main.py:3295 (_build_candles_df:3289; вызовы 1121, 4803, 5255) | окно истории из симулируемой ленты |
| `get_instrument_info(figi)` | main.py:1613, 2080, 4346, 4909, 4968, 5083, 5283; risk_manager.py:109, 165 | статическая таблица (lot, tick) |
| `get_positions()` | main.py:2042, 2862, 5070, 5228, 5401; risk_manager.py:149 | позиция симулятора (PositionData: лоты со знаком) |
| `get_account_balance()` | risk_manager.py:96 | баланс симулятора |
| `post_market_order(figi, qty, dir, order_id)` | main.py:2315 (SELL закрытия), 5327 (BUY входа) | исполнение по модели заполнения; order_id сохраняется даже при «потере ответа» |
| `get_sandbox_order_state(oid, type)` | main.py:716, 718, 2678, 2681, 4704, 5391, 5511, 5556; execution.py:1059, 1064 | статус симулируемой заявки |
| `cancel_order(oid, type)` | main.py:4385, 4474, 5379 | отмена |
| `get_sandbox_orders()` | main.py:5006 | список активных заявок |
| health-флаг: `is_uncertain()` / `uncertain_state` | client.is_uncertain() main.py:5181; присваивания uncertain_state по всему движку (напр. 5150, 5231, 5337, 5693); флаг определён tinkoff_client.py:681 | флаг симулятора (сценарии «неизвестно») |

Полнота инвентаризации:

- **Покрыты все производственные точки вызова** клиентских методов в
  main.py (список в таблице; получен полным grep'ом `client.` по файлу),
  execution.py (1059, 1064) и risk_manager.py (96, 109, 149, 165, 181).
  На этапе E RiskManager получает adapter вместо сырого клиента (те же
  5 методов доступа).
- **Методы клиента БЕЗ производственных вызовов** (определены в
  tinkoff_client.py, вызываются только тестами): `get_all_tradable_shares`
  (227), `get_positions_debug` (523), `get_sandbox_max_lots` (458; тесты
  tests/test_tinkoff_client.py:246-301). В интерфейс адаптера v1 НЕ
  включаются; появление производственного вызова = явное расширение ABC
  и контрактного теста K-1 (не молчаливое добавление).
- **screener.py НЕ входит в интерфейс**: скринер открывает СОБСТВЕННОЕ
  read-only SDK-соединение (`AsyncClient(config.TINKOFF_READONLY_TOKEN)`,
  screener.py:130; вызовы instruments.shares 131, get_all_candles 151) и
  не использует TinkoffClient. В backtest вселенная инструментов —
  фиксированный список без SDK.
- **Жизненный цикл соединения** (`__aenter__`/`__aexit__`/
  `_ensure_account`, tinkoff_client.py:193-226) остаётся у
  SandboxExecutionAdapter (делегирование); backtest-адаптер сетевых
  соединений не открывает (§9.6).

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

### 9.6. Классы заявок и изоляция backtest от брокера (Stage 2.1)

Дополнение по замечанию №4 независимой проверки. Архитектура разделяет
ТРИ класса заявок; смешение классов невозможно по построению:

| Класс | Где существует | Путь отправки | Кем создаётся |
|---|---|---|---|
| ВИРТУАЛЬНЫЕ заявки симулятора (BacktestOrder) | только внутри пакета `backtest/` (память прогона и файлы результатов) | fill-модель симулятора (backtest/fill_model.py, правила A-1…A-13) | BacktestExecutionAdapter |
| SANDBOX-заявки | контур T-Invest Sandbox | SandboxExecutionAdapter -> TinkoffClient -> sandbox endpoint (USE_SANDBOX=True) | движок в sandbox-режиме |
| LIVE-заявки | — | ЗАПРЕЩЕНЫ тройным запретом (config.validate 162-163; SandboxRequiredError tinkoff_client.py:182-184; assert_sandbox_only build_safety.py:78-83) + guard Режима A (build_safety.py:86-113) | не проектируются |

**Подтверждение (замечание №4):** backtest МОЖЕТ создавать, исполнять и
отменять виртуальные заявки внутри симулятора; backtest НЕ МОЖЕТ
отправить реальную брокерскую заявку. Проверки, обеспечивающие
разделение:

1. BacktestExecutionAdapter не содержит и не импортирует TinkoffClient/SDK — сетевого пути в пакете backtest/ нет (архитектурное правило
   пакета; проверяется импорт-тестом S-6).
2. Движку в backtest-режиме передаётся ТОЛЬКО BacktestExecutionAdapter;
   TinkoffClient в контуре прогона не создаётся, токен TINKOFF_API_TOKEN
   симулятору не передаётся (лента — из файлов).
3. Маркер `execution_model: "backtest_v1"` входит в config_hash и шапку
   всех журналов прогона (§9.4) — результат не может быть выдан за
   sandbox/live.
4. Sandbox-ветка сохраняет всю существующую защиту без изменений (§9.5):
   тройной запрет LIVE, guard Режима A/B (guard ставится на клиенте
   main.py:5659-5660).
5. Тест S-6 (STAGE2_TEST_MATRIX.md): попытка получить из
   backtest-контекста реальный клиент / отправить брокерскую заявку
   ОБЯЗАНА отклониться.

**Ограничения backtest v1 (явно, не преуменьшаются):** v1 НЕ моделирует
ликвидность (A-6), market impact (A-7), корпоративные события (A-11),
задержку данных (A-12). Результат прогона backtest v1 — проверка
совместимости, детерминизма и поведения механики стратегии и движка; он
НЕ является окончательной проверкой прибыльности и не может
использоваться как вердикт о доходности. Метки прогона включают оговорку
`backtest_v1_not_profitability_verdict` (§9.4, §10.4).

---

## 10. Конфигурация (§5 ТЗ)

### 10.1. Принципы (ПЕРЕРАБОТАНО Stage 2.2, замечание №1 проверки; ДОПОЛНЕНО Stage 2.3, коррекция №1 аудита Stage 2.2)

1. Выбор стратегии — одна настройка `ACTIVE_STRATEGY` (non-code файл:
   env или JSON запуска; Stage 1 STRATEGY_SWITCH §4).
2. Отдельные параметры стратегий, риск-менеджмента, исполнения —
   раздельные файлы/секции; движок не читает сигнальные константы из
   config.py (категории A–E Stage 1 STRATEGY_SWITCH §2).
3. **Валидация — по КОНКРЕТНОЙ выбранной стратегии и её эффективной
   конфигурации (Stage 2.2).** Валидатор применяет схему (`schema.py`)
   ИМЕННО выбранной стратегии к ЕЁ params.json (с учётом выбранного
   варианта); движковые категории (engine.json) валидируются общими
   правилами. Параметры НЕ выбранной стратегии не читаются и на старт не
   влияют. У валидатора НЕТ исключений ни для одного legacy-профиля
   (решение владельца Stage 2.2: параметры FORCE_TRADE не могут влиять
   на конфигурацию, валидацию и исполнение нового движка; наследование
   параметров старой стратегии новой стратегией ЗАПРЕЩЕНО; новая
   стратегия НЕ строится на значениях legacy-профиля — её params.json
   определяется собственной логикой).
4. **Правила валидации — ТОЛЬКО доказуемые из кода конкретной стратегии
   (таблица ниже); правил «на всякий случай» нет.** Кросс-правила
   объявляются в schema.py с пометкой, какой блок логики использует
   зависящие параметры; проверяются только зависимости РЕАЛЬНО
   используемых блоков (для legacy используются все перечисленные блоки
   — ADX-regime, MA, BB+RSI, объём, фильтр MA — поэтому применяются все
   правила; если будущая стратегия не использует подтверждение объёма,
   правила объёма к ней не применяются).
5. Критические параметры БЕЗ скрытых дефолтов; НЕТ getattr-fallback
   (сегодняшний паттерн main.py:1952-1953, 5139; execution.py:923, 1003 —
   в новом слое не воспроизводится).
6. Отказ запуска при некорректной конфигурации — со списком ВСЕХ ошибок
   разом (по образцу config.validate() config.py:147-163).
7. **Разделение понятий готовности данных и допуска сигнала (Stage 2.3,
   коррекция №1.2).** Валидация разделяет ЧЕТЫРЕ разных понятия:
   (а) **минимальная готовность данных** — достаточность ленты для
   расчёта режимов и индикаторов (runtime-свойство: стратегия ШТАТНО
   возвращает HOLD, пока данные не готовы — strategy.py:197-198,
   231-232; расхождение не является ошибкой конфигурации);
   (б) **минимальное количество свечей для допуска сигнала** —
   `MIN_CANDLES_FOR_SIGNAL`, порог допуска, объявленный самой стратегией;
   (в) **период прогрева индикатора** — длина ленты, необходимая КОНКРЕТНОМУ
   индикатору для выдачи значения (например, MA фильтра: TREND_FILTER_MA_PERIOD,
   strategy.py:231-237); прогрев МОЖЕТ быть длиннее допуска сигнала —
   это НЕ ошибка конфигурации;
   (г) **фактическая доступность конкретного индикатора** — runtime-свойство
   (NaN/пустая серия после расчёта — strategy.py:239, 277, 350).
8. **Единый контракт готовности (Stage 2.3):** стратегия НЕ выдает
   сигнал, пока все необходимые ей данные и индикаторы НЕ готовы; движок
   НЕ признаёт конфигурацию некорректной ТОЛЬКО из-за более длинного
   периода прогрева. Фактическая готовность проверяется по фактическому
   коду: в существующей стратегии все блоки самозащищены — дефицит свечей
   даёт HOLD, а не исключение или сигнал (strategy.py:197-198 — общий гейт;
   231-232 — фильтр MA; 258 — MA; 317 — BB+RSI; 58 и 81-88 — режим ADX;
   277/350 — NaN-проверки). Правило `MIN_CANDLES_FOR_SIGNAL >=
   TREND_FILTER_MA_PERIOD` ОТМЕНЕНО как правило валидации: оно смешивало
   допуск сигнала (б) с прогревом фильтра (в) и ложным образом
   отвергало работоспособную конфигурацию (аудит Stage 2.2, коррекция №1.2;
   эффект V-46 продолжается документироваться, НЕ «оптимизируется»).
   Единственная зона, где «длинный прогрев» МОЖЕТ стать ошибкой —
   физическая недостаточность окна данных (см. правило достаточности
   окна в таблице ниже и готовность на старте — §4.1 `on_start`,
   fail-closed по ФАКТИЧЕСКОЙ длине ленты без предположений о календаре
   сессий; статическая оценка бюджета свечей — ПРЕДУПРЕЖДЕНИЕ при
   загрузке, рекомендация Stage 1 PARAMETER_GAPS, без изобретения чисел).
9. **Единая таблица правил валидации (Stage 2.3, коррекция №1.3)** —
   единственный сводный перечень: параметр, допустимые значения,
   обязательные зависимости, причина ограничения, реакция на ошибку,
   соответствующий тест (таблица ниже после строк-оснований).
   Дублирующие формулировки правил в документах Stage 2.2 сверены и
   устранены (N-04 == N-12 по RSI; T-16 == таблица §10.1; G-5 == §10.3).

**Проверенные условия валидации legacy-стратегии (Stage 2.2, исправление
№1: каждая строка выведена из кода стратегии заново, а НЕ перенесена из
Stage 1; ссылки — commit 884cefd; назначение каждого правила —
предотвратить «мёртвую конфигурацию» (старт разрешён, сигналы невозможны)
либо инвертированную семантику):**

| Правило | Основание (код, FACT) | Что происходит при нарушении без валидации |
|---|---|---|
| MIN_CANDLES_FOR_SIGNAL >= MA_SLOW_PERIOD + 2 | strategy.py:258 (`len < MA_SLOW_PERIOD + 2 -> HOLD "Мало данных для MA"`) | сигналы MA никогда не формируются — мёртвая конфигурация |
| MIN_CANDLES_FOR_SIGNAL >= BB_PERIOD + RSI_PERIOD | strategy.py:317 (`len < BB_PERIOD + RSI_PERIOD -> HOLD "Мало данных для BB+RSI"`) | сигналы BB+RSI никогда не формируются |
| MIN_CANDLES_FOR_SIGNAL >= ADX_PERIOD + 1 | strategy.py:58 (`len < ADX_PERIOD + 1 -> UNKNOWN`) | режим всегда UNKNOWN -> все сигналы HOLD |
| MIN_CANDLES_FOR_SIGNAL >= ADX_PERIOD + ADX_HYSTERESIS_CANDLES | strategy.py:81-88 (regime требует ADX_HYSTERESIS_CANDLES не-NaN значений ADX после dropna: `len(recent) < ... -> UNKNOWN`) | режим может зависнуть в UNKNOWN на пограничной длине ленты |
| **(Stage 2.3: ПРАВИЛО ОТМЕНЕНО)** MIN_CANDLES_FOR_SIGNAL >= TREND_FILTER_MA_PERIOD — НЕ правило валидации | прогрев фильтра MA (strategy.py:231-232: `len < TREND_FILTER_MA_PERIOD -> False`) — РЕЖИМНАЯ готовность данных (§10.1 п. 7а/7в), не допуск сигнала; при дефиците свечей фильтр ШТАТНО возвращает False (сигнал HOLD) и СПОСОБЕН пропустить сигнал после накопления ленты; конфигурация MIN_CANDLES=60 < TREND_FILTER=100 — РАБОТОСПОСОБНА (движок ждёт готовности; известный эффект V-46 документируется, НЕ «оптимизируется») | (до Stage 2.3) ложный отказ старта для работоспособной конфигурации с более длинным прогревом — устранён коррекцией №1 |
| 0 < RSI_OVERSOLD <= RSI_OVERBOUGHT < 100 | strategy.py:353-372: BUY при `rsi_val < RSI_OVERSOLD`, SELL при `rsi_val > RSI_OVERBOUGHT` — СТРОГИЕ неравенства; при РАВЕНСТВЕ порогов (например 50/50) ветки не пересекаются (rsi не может быть одновременно <50 и >50) — конфигурация РАБОТОСПОСОБНА; при OVERSOLD <= 0 ветка BUY мертва (rsi < OS недостижимо при rsi >= 0); при OVERBOUGHT >= 100 ветка SELL мертва (rsi > OB недостижимо при rsi <= 100); при OVERSOLD > OVERBOUGHT семантика инвертирована (покупка при высоком RSI) | ИСПРАВЛЕНО Stage 2.2: правило Stage 1 HARDCODED §6 «RSI_OVERSOLD < RSI_OVERBOUGHT» было ИЗБЫТОЧНО строгим — оно отвергало работоспособное равенство порогов; корректное правило допускает равенство, отвергает инверсию и мёртвые границы |
| ADX_HYSTERESIS_CANDLES >= 1 | strategy.py:81-88: `tail(0)` -> пусто -> regime UNKNOWN навсегда; strategy.py:147-158: required=0 отменяет гистерезис (мгновенная смена режима) | мёртвая конфигурация (все HOLD) или потеря гистерезиса |
| VOLUME_CONFIRMATION_WINDOW >= 3 | strategy.py:439-445: `window = min(WINDOW, len)`; `window < 3 -> False "мало свечей"` | подтверждение объёма всегда False -> ВСЕ BUY/SELL отклоняются — мёртвая конфигурация |
| VOLUME_SPIKE_FACTOR >= 0 | strategy.py:458 (`last >= avg * FACTOR`); 0.0 -> подтверждение всегда True — ФАКТ кода, работоспособное значение | отрицательный FACTOR -> подтверждение всегда False -> все сигналы отклоняются |
| MA_FAST_PERIOD >= 1; MA_SLOW_PERIOD >= 1; BB_PERIOD >= 1; RSI_PERIOD >= 1; ADX_PERIOD >= 1; TREND_FILTER_MA_PERIOD >= 1 | ta.sma/ta.rsi/ta.adx/ta.bbands (strategy.py:234-237, 261-269, 320-329, 61-66); length < 1 -> вырожденный/ошибочный расчёт (ветки ошибок strategy.py:308-310, 387-389 дают HOLD) | мёртвая конфигурация |
| MA_FAST_PERIOD != MA_SLOW_PERIOD | strategy.py:274-275, 288-297: при равенстве периодов обе SMA идентичны (pf==ps, lf==ls) -> условие `pf < ps and lf > ls` недостижимо -> сигналы MA невозможны. (Замечание Stage 2.2: при FAST > SLOW сигналы формально возможны — точки пересечения двух SMA не зависят от того, какая названа «быстрой», — но именование инвертировано; правило фиксирует нижнюю границу: равенство запрещено как доказуемо мёртвая конфигурация) | мёртвая конфигурация при равенстве |
| 0 <= ADX_TREND_THRESHOLD <= 100 | strategy.py:92-95 (`value > ADX_TREND_THRESHOLD`); ADX определён в диапазоне [0;100] | вне диапазона — вырожденная семантика режима |
| TAKE_PROFIT_RATIO > 0 | risk_manager.py:244 (`tp = entry + dist * RATIO`), 257-258 (отбраковка tp <= 0) | TP на уровне входа или ниже |
| Дефицит свечей ленты | strategy.py:197-198 (`len < min_candles_required -> HOLD "Недостаточно данных"`) — деградация ШТАТНАЯ, без исключения; CANDLES_LOOKBACK_DAYS проверяется кросс-правилом достаточности (Stage 1 HARDCODED §6) как feasibility-условие конфигурации | не отказ старта: runtime-поведение определено |
| **(Stage 2.3)** Достаточность окна данных: фактическая длина ленты на старте >= всех потребностей прогрева выбранной стратегии (MAX(MIN_CANDLES_FOR_SIGNAL, MA_SLOW+2, BB+RSI, ADX+1, ADX+ADX_HYSTERESIS, TREND_FILTER_MA_PERIOD)) | `on_start` (§4.1) проверяет ФАКТИЧЕСКУЮ ленту (без предположений о календаре); при недостатке — отказ старта (fail-closed); статическая оценка бюджета «CANDLES_LOOKBACK_DAYS × свечей/день» (Stage 1 PARAMETER_GAPS:59) — ТОЛЬКО ПРЕДУПРЕЖДЕНИЕ при загрузке (точная дневная ёмкость зависит от календаря биржи; числовых порогов НЕ изобретается) | (если пропустить) мёртвая конфигурация: окно физически не накапливает нужные свечи — режимы/индикаторы никогда не рассчитаются |

Проверка ТИПОВ и ДИАПАЗОНОВ — по схеме каждой стратегии. Правила выше НЕ
изобретают новых торговых значений и НЕ меняют ни одного порога (мандат
NO THRESHOLD IS OPTIMIZED): валидатор отвечает только на вопрос
«конфигурация работоспособна и непротиворечива», а не «какие значения
выбирать». Поведение pandas_ta_classic при вырожденных параметрах
(BB_STD_DEV <= 0, length < 1 в рантайме) кодом НЕ доказуемо — НЕ
валидируется как «мёртвая конфигурация», вынесено в V-9
(STAGE2_OPEN_DECISIONS.md).

**Единая таблица правил валидации (Stage 2.3, коррекция №1.3 — сводный
перечень; реакции критических ошибок — fail-closed, отказ старта со
списком ВСЕХ ошибок разом):**

| Параметр | Допустимые значения | Обязательные зависимости | Причина ограничения | Реакция на ошибку | Тест |
|---|---|---|---|---|---|
| RSI_OVERSOLD | 0 < OS <= OB < 100 | нет | строгие неравенства strategy.py:355/371: равные пороги (напр. 50/50) не пересекаются — работоспособно; инверсия OS > OB — покупка при высоком RSI (инвертированная семантика); OS <= 0 — ветка BUY мертва (rsi >= 0); OB >= 100 — ветка SELL мертва (rsi <= 100) | OS > OB / OS <= 0 / OB >= 100 -> отказ старта; OS == OB -> ПРИНИМАЕТСЯ | T-16, N-12 |
| RSI_OVERBOUGHT | см. выше | см. выше | см. выше | см. выше | T-16, N-12 |
| MIN_CANDLES_FOR_SIGNAL | int >= 1 | >= MA_SLOW+2 (strategy.py:258); >= BB+RSI (317); >= ADX+1 (58); >= ADX+ADX_HYSTERESIS (81-88); НЕ связан жёстко с TREND_FILTER_MA_PERIOD (отменено Stage 2.3); фактическая длина ленты на старте >= MAX(все потребности прогрева) | согласование объявленного допуска с потребностями блоков логики (иначе допуск декларативно бессмыслен); TREND_FILTER — прогрев фильтра (готовность), а не допуск — жёсткое правило смешивало понятия | отказ старта (кросс-правила) / отказ старта по фактической готовности on_start | T-16, N-04 |
| MA_FAST_PERIOD / MA_SLOW_PERIOD | >= 1; FAST != SLOW | MIN_CANDLES >= MA_SLOW+2 | length < 1 — вырожденный расчёт (strategy.py:261-269, 308-310); равенство -> идентичные серии -> `pf < ps and lf > ls` недостижимо (274-297) | отказ старта | T-16 |
| BB_PERIOD / RSI_PERIOD | >= 1 | MIN_CANDLES >= BB+RSI | length < 1 — вырожденный расчёт (strategy.py:320-329) | отказ старта | T-16 |
| ADX_PERIOD | >= 1 | MIN_CANDLES >= ADX+1; >= ADX+ADX_HYSTERESIS | length < 1 — вырожденный расчёт (strategy.py:61-66) | отказ старта | T-16 |
| ADX_HYSTERESIS_CANDLES | >= 1 | — | 0 -> tail(0) пусто -> режим UNKNOWN навсегда (strategy.py:81-88, 147-158) | отказ старта | T-16 |
| ADX_TREND_THRESHOLD | 0..100 | — | ADX определён в [0;100]; `value > THRESHOLD` (strategy.py:92-95) | отказ старта | T-16 |
| TREND_FILTER_MA_PERIOD | >= 1 | прогрев: фактическая длина ленты >= периода (runtime, NOT config-error); предупреждение по бюджету окна | прогрев фильтра — готовность данных (§10.1 п. 7в); дефицит свечей = HOLD, не ошибка | отказ старта только при length < 1 или недостаточном фактическом окне (on_start) | T-16, T-17 |
| VOLUME_CONFIRMATION_WINDOW | >= 3 | — | `window < 3 -> False` — все сигналы отклоняются (strategy.py:439-445) | отказ старта | T-16 |
| VOLUME_SPIKE_FACTOR | >= 0 | — | отрицательный -> подтверждение всегда False (strategy.py:458); 0.0 -> всегда True — ФАКТ, работоспособно | отказ старта (отрицательный) | T-16 |
| TAKE_PROFIT_RATIO | > 0 | — | `tp = entry + dist * RATIO` (risk_manager.py:244); tp <= 0 отбраковывается (257-258) | отказ старта | T-16 |
| ACTIVE_STRATEGY | задан явно; присутствует в реестре | — | нет значения по умолчанию; неизвестное имя -> отказ (аналог config.py:118-119) | отказ старта | N-01, N-02 |
| неизвестные ключи params.json / engine.json | отсутствуют | — | строгая схема; опечатка = ошибка | отказ старта | N-03 |
| CANDLES_LOOKBACK_DAYS | int >= 1; фактическое окно >= потребностей прогрева (on_start) | все индикаторы выбранной стратегии | физическая недостаточность окна = мёртвая конфигурация | отказ старта по факту (on_start); статическая оценка — ПРЕДУПРЕЖДЕНИЕ | T-17 |

Примечание Stage 2.3: правила связаны с тестами ОДНОЗНАЧНО; в документах
комплекта не осталось дублирующих формулировок с другой семантикой
(N-04 приведён к N-12 и T-16: равенство RSI-порогов принимается,
инверсия и мёртвые границы отвергаются; TREND_FILTER исключён из
жёстких кросс-правил MIN_CANDLES).

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
      profiles.py                # SANDBOX_TEST/TECH_CHECK/CONSERVATIVE
                                 # (FORCE_TRADE НЕ переносится — Stage 2.2)
      schema.py                  # схема: имя, тип, единицы, диапазон, кроссы
```

### 10.3. Пример итоговой конфигурации (§5 ТЗ; ПЕРЕРАБОТАНО Stage 2.2)

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

`strategies/legacy_samsung_v4/params.json` — ПЕРЕРАБОТАНО Stage 2.3
(решение владельца: выбор старого профиля НЕ требуется, D-13 ред. 2.3;
Stage 2.2: FORCE_TRADE полностью исключён, §2 STAGE2_2_CHANGELOG.md).
Пример ниже иллюстрирует СТРУКТУРУ файла legacy-стратегии на
исторических значениях варианта CONSERVATIVE (config.py:108-117, FACT)
— как ИЛЛЮСТРАЦИЯ СТРУКТУРЫ И ПОКРЫТИЯ СХЕМЫ, а НЕ как принятое
решение о торговом поведении и НЕ как начальная конфигурация нового
движка; выбор первой торговой стратегии нового движка — будущее
решение владельца (D-13, редакция Stage 2.3):

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

(значения — точные константы config.py:64-73 и 121 (база) и
config.py:108-117 (CONSERVATIVE); сами параметры НЕ менялись; известный
задокументированный эффект: MIN_CANDLES=60 < TREND_FILTER=100 — сигналы
при длине ленты [60;100) отклоняются фильтром MA, V-46 — документируется,
не исправляется. Stage 2.3: это сочетание НЕ является ошибкой валидации
— §10.1, правило готовности данных).

Правила профиля legacy (ПЕРЕРАБОТАНО Stage 2.3):

1. **FORCE_TRADE ИСКЛЮЧЁН решением владельца (Stage 2.2):** профиль НЕ
   переносится в profiles.py, НЕ является исполняемым режимом legacy, его
   параметры НЕ участвуют в конфигурации/валидации/исполнении нового
   движка, совместимость с ним НЕ требуется. Golden-тест идентичности
   FORCE_TRADE (G-5 редакции 2.1) УДАЛЁН — вместе с ним устранено
   противоречие «профиль как якорь совместимости» vs «профиль как
   вариантный набор». Ни одно требование комплекта Stage 2.3 больше НЕ
   опирается на значения config.py:78-87 (они остаются FACT-историей
   исходного кода и НЕ переносятся в проект).
2. profiles.py содержит ТОЛЬКО оставшиеся три варианта (SANDBOX_TEST —
   config.py:88-97, TECH_CHECK — 98-107, CONSERVATIVE — 108-117), значения
   НЕ меняются.
3. **НОВЫЙ ДВИЖОК НЕ ТРЕБУЕТ ВЫБОРА ПРОФИЛЯ (Stage 2.3):** поле
   `profile` в params.json legacy — ОПЦИОНАЛЬНЫЙ маркер исторического
   варианта для регрессионного сравнения (golden-тесты), НЕ обязательная
   настройка старта движка. Начальная конфигурация нового движка
   определяется ЯВНЫМ `ACTIVE_STRATEGY` + params.json выбранной стратегии
   (fail-closed: отсутствие значения = отказ старта, §10.1 п. 1-3);
   требование «выбрать один из старых профилей» исключено из архитектуры;
   старые профили НЕ являются стратегией по умолчанию и НЕ блокируют
   переход к реализации. Golden-тест G-5 (ред. 2.3): перенос значений
   ВСЕХ трёх вариантов == константам config.py:88-117 (байт-в-байт);
   выбор для старта НЕ требуется (TEST_MATRIX §2).
4. Выбор ПЕРВОЙ НОВОЙ стратегии — ОТДЕЛЬНОЕ будущее решение владельца
   ПОСЛЕ создания движка и исследования кандидатов (D-13, редакция
   Stage 2.3); профиль — параметр ОДНОЙ legacy-логики, а не выбор
   стратегии; новые стратегии НЕ наследуют имена и значения профилей
   legacy (§10.1 п. 3; §8 п. 2).
5. Валидатор НЕ имеет исключений для профилей legacy (§10.1 п. 3):
   эффективная конфигурация ЛЮБОГО варианта обязана проходить общую схему
   этой стратегии; параметры отброшенного FORCE_TRADE не могут влиять на
   валидацию (решение владельца Stage 2.2).

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
STAGE 2.1: CORRECTIONS APPLIED (5 замечаний, см. STAGE2_1_CHANGELOG.md)
STAGE 2.2: CLEANUP APPLIED (3 замечания + решение FORCE_TRADE,
см. STAGE2_2_CHANGELOG.md)
STAGE 2.3: FINAL CORRECTIONS APPLIED (4 коррекции аудита Stage 2.2,
см. STAGE2_3_CHANGELOG.md)
EMERGENCY EXIT ARCHITECTURE — DESIGN ONLY
NO BROKER EXECUTION
```

---

## 14. Сводка правок Stage 2.2

| # | Замечание проверки / решение владельца | Где исправлено |
|---|---|---|
| 1 | Конфигурация и валидация не были привязаны к конкретной выбранной стратегии; условия валидации индикаторов и количества свечей не были перепроверены по коду; правило RSI Stage 1 было избыточно строгим (отвергало работоспособное равенство порогов) | §10.1 переписан: валидация по конкретной стратегии и её эффективной конфигурации; таблица проверенных условий с выводом из кода (strategy.py:58, 81-88, 197-198, 231-232, 258, 274-297, 317, 353-372, 439-458; risk_manager.py:244, 257); исправление RSI-правила (равенство порогов работоспособно, инверсия отвергается); зависимости кросс-правил — только для реально используемых блоков; НЕТ исключений для legacy-профилей; наследование параметров старой стратегии новой запрещено; §10.3: пример без FORCE_TRADE, правила профиля переписаны |
| 2 | Небезопасный доступ к ценам в выходном конвейере: `prices[pos.figi]` / `df_for_exit[pos.figi]` (KeyError на отсутствующем ключе — штатный случай: get_last_prices опускает FIGI без цены, tinkoff_client.py:262-265) и отсутствие проверки валидности цены (None/0/отрицательная/NaN/±Inf) до передачи в стратегию | §6.2 переписан: единый шлюз `_valid_price` (наличие ключа -> float -> math.isfinite -> > 0) ДО вызова стратегии и повторно на шаге закрытия (защита в глубину, дополняет 5147-5151 проверкой isfinite); UNCERTAIN-семантика двух уровней (оценка: пропуск решения + сохранение защиты; закрытие: существующий UNCERTAIN без заявки); `df_for_exit.get()`; таблица классов EP-1..EP-7; тесты TEST_MATRIX §1а |
| 3 | Член `friction_actual` в формуле фактического риска (редакция 2.1 §7.4) не был определён | §7.4 переписан: однозначная формула с определением КАЖДОГО члена и его источника: shares = executed_lots*lot_size; entry_commission_ps = фактическая комиссия входа / shares (execution.py:1271-1288, main.py:4105; 0.0 — достоверный факт) либо оценка exec_price*COMMISSION_PER_SIDE; exit_commission_ps = оценка exec_price*COMMISSION_PER_SIDE (пересчитывается при закрытии, main.py:2464-2489); запрет двойного учёта проскальзывания; risk_commission_source; краевые случаи (RECOVERY, отсутствие комиссии, NaN/±Inf) — fail-safe без блокировки регистрации |
| 4 | Решение владельца Stage 2.2: ПОЛНЫЙ ОТКАЗ ОТ FORCE_TRADE (отмена исправления №2 Stage 2.1) | §8 п. 2 (профиль не мигрирует, не исполняется, параметры не влияют на новый движок, совместимость не требуется); §10.2 (profiles.py без FORCE_TRADE); §10.3 (пример и правила профиля переписаны; G-5 редакции 2.1 удалён, заменён тестом переноса выбранного профиля); §6.2/§7.4/§10.1 не содержат FORCE_TRADE-исключений; D-13 переформулировано; шапка и статус (§0, §13) обновлены; проверка отсутствия противоречий — STAGE2_2_CHANGELOG.md §4 |

Полный перечень правок во всех документах — STAGE2_2_CHANGELOG.md.

---

## 15. Сводка правок Stage 2.3 (финальные корректировки по аудиту Stage 2.2)

| # | Коррекция аудита Stage 2.2 | Где исправлено |
|---|---|---|
| 1 | Единые и корректные правила валидации конфигурации: противоречие N-04↔N-12 (равенство RSI-порогов); правило MIN_CANDLES >= TREND_FILTER не является универсальным обязательным; разделение готовности данных / допуска сигнала / прогрева индикаторов / фактической доступности; единый контракт готовности | §10.1 переполнен: пп. 7-9 (разделение понятий, единый контракт, единая таблица правил); строка TREND_FILTER заменена строкой «ПРАВИЛО ОТМЕНЕНО»; добавлены правило достаточности окна данных и Единая таблица правил валидации (параметр/допустимые значения/зависимости/причина/реакция/тест); TEST_MATRIX: T-16 переписан, N-04 исправлен, добавлен T-17 |
| 2 | Корректная модель расчётного риска с отдельным учётом проскальзывания при исполнении стопа: разница «цена входа − стоп» НЕ является резервом на проскальзывание выхода; Estimated risk / Open estimated risk / Realized loss разделены; запрет термина «actual risk» для прогнозов; без двойного учёта входного проскальзывания; резерв — конфигурационная величина (D-16), значение НЕ изобретается | §7.4 переписан: три величины в три момента времени; формула Estimated risk (до входа) с членом STOP_SLIPPAGE_RESERVE; открытый расчётный риск переименован (open_risk_*); правила недопущения двойного учёта; запреты терминологии и толкования; краевые случаи дополнены «резерв не сконфигурирован»; TEST_MATRIX: T-15 переписан; OPEN_DECISIONS: D-16 |
| 3 | Полное исключение обязательного выбора legacy-профилей как начальной конфигурации нового движка; D-13 переопределено | §8 п. 2 дополнен блоком «НОВЫЙ ДВИЖОК НЕ ТРЕБУЕТ ВЫБОРА СТАРОГО ПРОФИЛЯ»; §10.3 правила переписаны (поле profile — опциональный маркер регрессионного сравнения; пример — иллюстрация структуры); G-5 переписан (перенос ВСЕХ трёх вариантов, выбор НЕ требуется); OPEN_DECISIONS: D-13 (ред. 2.3) |
| 4 | Архитектура гибридного аварийного выхода (обязательная новая часть): EmergencyExitController, этапы A–F, защита от дублирующих SELL, частичные исполнения, восстановление после перезапуска, события, ограничения, параметры политики в OPEN DECISIONS, проверка возможностей T-Invest по коду | НОВЫЙ документ STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md (полный проект); §15 настоящего документа (сводка + интеграция); TEST_MATRIX §8 (EE-01…EE-17); OPEN_DECISIONS: F-22…F-28, P-15, D-17…D-23, V-10; FILE_CHANGE_MAP: M-7, §3.8, расширение адаптера; ROADMAP: этап H |

Полный перечень правок во всех документах — STAGE2_3_CHANGELOG.md.
**ПРИМЕЧАНИЕ Stage 2.3.1:** правки №2 и №4 этой таблицы УТОЧНЕНЫ
последующим аудитом Stage 2.3 — точка интеграции контроллера перенесена
ДО первой закрывающей заявки (коррекция №1), обоснование модели риска
исправлено и дополнено четырьмя ценовыми величинами (коррекция №2,
STAGE2_RISK_MODEL_FORMULAS.md). Сводка правок 2.3.1 — §17; перечень —
STAGE2_3_1_CHANGELOG.md.

---

## 16. Аварийный выход: EmergencyExitController (Stage 2.3.1, коррекция №1 — сводка)

**Полный проект — STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md (полная новая
редакция 2.3.1).** Здесь — место компонента в архитектуре и связь с
остальными разделами.

- **Проблема:** цена прошла ниже стопа (в т.ч. гэпом), защитный выход
  (check_all, execution.py:978-1022 — программный поллинг цены, БЕЗ
  биржевого стоп-ордера — подтверждено кодом) не исполнился, и движок
  продолжал бы бесконтрольно удерживать позицию. Наличие программного
  Stop Loss НЕ гарантирует исполнение по цене стопа.
- **КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ Stage 2.3.1 (точка интеграции):** в ред. 2.3
  контроллер включался ПОСЛЕ шага защитных выходов (M-7) — к этому
  моменту торговый цикл уже отправлял рыночную SELL
  (main.py:5144 → 5152 → 2315), и гибридная последовательность
  «лимитная попытка → эскалация» была недостижима для своего главного
  сценария. В ред. 2.3.1 контроллер — ЕДИНСТВЕННЫЙ маршрут отправки
  закрывающих заявок, интегрированный ДО точки отправки первой заявки:
  шаг 2г цикла передаёт решения контроллеру (ТОЛЬКО INTENT, без заявок),
  новый шаг 2д продвигает инциденты и отправляет ВСЕ закрывающие заявки
  (см. §6.2 этой редакции). Прямой вызов close_position из цикла для
  защитных срабатываний УДАЛЁН из проекта.
- **Компонент:** `EmergencyExitController` (НОВЫЙ модуль `emergency_exit.py`,
  PROPOSAL) — владеет ИСПОЛНЕНИЕМ закрытия уже открытой позиции:
  reconciliation, контролируемая попытка, эскалация, подтверждение; НЕ
  генерирует торговые сигналы и НЕ меняет стратегию; НЕ отменяет
  защитные обнаружения других слоёв.
- **Единый контракт Stop Loss:** обычное пересечение стопа, гэп ниже
  стопа, резкое движение через несколько уровней, повторное получение
  цены ниже стопа и восстановление цены выше стопа обрабатываются ОДНИМ
  Exit Incident одним контроллером; различие сценариев — атрибуты
  инцидента (breach_kind/breach_depth из наблюдаемых данных), а НЕ
  разные маршруты; числовой порог гэпа НЕ изобретается
  (STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md §4).
- **Логика (пять этапов A–E):** обнаружение → INTENT-before-send →
  reconciliation (ЗАПРЕТ дублирующей SELL) → контролируемая попытка
  ЛИМИТНОЙ заявкой (SL-инциденты) / рыночная первым действием (не-стоповые
  причины, D-24) → эскалация к РЫНОЧНОЙ заявке на подтверждённый остаток
  (после отмены/разрешения судьбы лимитной) → подтверждение закрытия
  ТОЛЬКО через сверки (сумма исполнений == остаток И get_positions ноль).
- **Конечный автомат инцидента:** 13 состояний
  (STOP_DETECTED, EXIT_DECIDED, EXIT_INTENT_PERSISTED, RECONCILING,
  LIMIT_EXIT_PENDING, LIMIT_EXIT_PARTIAL, LIMIT_EXIT_CANCEL_PENDING,
  ESCALATION_READY, MARKET_EXIT_PENDING, MARKET_EXIT_PARTIAL,
  EXIT_CONFIRMED, EXIT_FAILED, UNCERTAIN) с полной таблицей
  допустимых/запрещённых переходов и правилом перезапуска
  «сначала reconciliation» (STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md §6).
- **Модель ценовых снимков (РЕД. 2.3.3):** три уровня ценовых данных
  инцидента — (1) `exit_decision_price`: первоначальная цена решения,
  записывается ОДИН раз при создании инцидента, НЕ изменяется при
  попытках, НЕ перезаписывается после reconciliation, сохраняется после
  перезапуска; (2) `exit_attempt_snapshot`: отдельный снимок рыночной
  цены непосредственно перед КАЖДОЙ попыткой отправки (LIMIT и MARKET),
  собственный attempt_id на попытку, снимки неизменяемы, старый снимок
  НЕ переиспользуется, без валидного снимка отправка НЕ выполняется
  (fail-closed); (3) фактические исполнения — ТОЛЬКО из подтверждений
  брокера, append-only, хранятся отдельно от снимков, со связью
  incident_id → attempt_id → order_request_id. Расчёт:
  `exit_exec_price` — средневзвешенная по всем подтверждённым
  исполнениям; `total_exit_slippage_ps = exit_decision_price -
  exit_exec_price`; `attempt_slippage_ps = attempt_snapshot_price -
  attempt_exit_exec_price`; `stop_execution_slippage_ps` — без
  изменений (только стоповые инциденты); двойной учёт исключён
  DC-7/DC-8; восстановление после перезапуска — R-10
  (STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md §6.5, §7а;
  STAGE2_RISK_MODEL_FORMULAS.md §3, §5.6; тесты ES-01…ES-14 —
  STAGE2_TEST_MATRIX.md §11).
- **Связь с существующими механизмами:** INTENT-before-send и защита от
  повторной SELL (`_sell_block_reason`, main.py:738-767;
  SELL_DUPLICATE_BLOCKED, main.py:2244) переиспользуются; per-order
  cursor и partial-ветки (main.py:5369-5471) сохраняются; UNCERTAIN-
  семантика (main.py:5147-5151) — обязательная реакция на неизвестное
  состояние; защитные SL/TP и стратегические выходы не конкурируют —
  несколько причин объединяются в ОДИН инцидент со сохранением ВСЕХ
  причин (защитное событие не теряется).
- **Возможности T-Invest (FACT, commit 884cefd):** клиент поддерживает
  ТОЛЬКО рыночные заявки (`post_market_order` — tinkoff_client.py:555;
  лимитных и биржевых стоп-заявок в коде НЕТ). Лимитная заявка этапа C
  требует РАСШИРЕНИЯ адаптера на этапе реализации — существующий код
  гибридный механизм НЕ поддерживает (заявлено явно, не приписывается
  существующему коду). Полная таблица «реализовано / предстоит
  реализовать» — STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md §5.
- **Параметры политики — НЕ изобретаются:** время ожидания, политика
  лимитной цены (начальная + переустановки), число попыток, условие
  эскалации, правила повтора при отказе, поведение при недоступности
  котировок/брокера, порядок попыток для не-стоповых причин (D-24),
  поведение при восстановлении цены выше стопа (D-27) — вынесены
  в OPEN DECISIONS (D-17…D-24, D-26, D-27) как решения владельца;
  произвольные значения по умолчанию НЕ устанавливаются. РЕД. 2.3.2
  (КОРРЕКЦИЯ №2): D-24/D-26/D-27 — ОБЯЗАТЕЛЬНЫЕ решения владельца БЕЗ
  умолчаний: формулировка ред. 2.3.1 «без решения действует вариант (а)
  как умолчание проекта» УДАЛЕНА как противоречащая обязательности;
  без письменно принятого решения параметр UNCONFIGURED, этап H НЕ МОЖЕТ
  БЫТЬ активирован, контроллер не подставляет вариант молча, запуск
  завершается явной диагностикой отсутствующего решения
  (STAGE2_OPEN_DECISIONS.md §3а — конфигурационная защита; тесты
  CD-01…CD-06 — STAGE2_TEST_MATRIX.md §10).
- **Единственный маршрут отправки — сценарии A/B/C (РЕД. 2.3.2,
  КОРРЕКЦИЯ №1):** инвариант ALL_BOT_SELL_SUBMISSIONS ⊆
  EmergencyExitController.process_incidents(). Сценарий A — любая
  программная SELL бота (SL/TP/BE/TRAIL/стратегический/аварийный выход,
  внутренняя команда закрытия) — через Exit Incident и
  process_incidents(); close_position — исполнитель рыночной ноги внутри
  контроллера, НЕ самостоятельный маршрут. Сценарий B — ручная продажа
  оператора через брокера — внешнее действие, заявок бота НЕТ,
  обнаружение через reconciliation (В3, main.py:1932-2011), подтверждение
  только после двойной сверки; при активном инциденте —
  reconciliation (T-07 EXIT_CONFIRMED). Сценарий C — команда оператора
  из Telegram/интерфейса бота — программное действие: ТОЛЬКО создание
  инцидента обработчиком (OPERATOR_CLOSE_REQUESTED), отправка —
  process_incidents(); прямой SELL из обработчика запрещён. Запреты:
  SELL из торгового цикла / из check_all() / из Telegram-обработчика /
  второй исполнитель / подтверждение ручного закрытия до reconciliation
  — STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md §3 (запреты №6-10), §3а;
  тесты EE-21…EE-27 (STAGE2_TEST_MATRIX.md §8 ред. 2.3.2).
- **Ограничения (обязательное описание):** даже единый контролируемый
  маршрут НЕ гарантирует ограничение убытка стоп-ценой (нет покупателей,
  остановка торгов, гэп, отказ брокера, задержка котировок, отказ
  рыночной заявки, частичное исполнение).
- **События и тесты:** полный перечень событий
  (PROTECTIVE_STOP_DETECTED … EMERGENCY_EXIT_CONFIRMED) и тест-матрица
  EE-01…EE-20 — STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md §10, §13 и
  STAGE2_TEST_MATRIX.md §8.

---

## 17. Сводка правок Stage 2.3.1 (критические корректировки по аудиту Stage 2.3)

| # | Коррекция аудита Stage 2.3 | Где исправлено |
|---|---|---|
| 1 | Точка интеграции EmergencyExitController: контроллер описывался как механизм, запускаемый ПОСЛЕ защитного выхода check_all() — по факту кода к этому моменту рыночная SELL уже отправлена (check_all → main.py:5144 → 5152 → post_market_order 2315), гибридная последовательность «лимит → рынок» недостижима | ЕДИНЫЙ контролируемый маршрут выхода: §6.2 (шаг 2г — передача решений контроллеру ТОЛЬКО с INTENT, БЕЗ заявок; новый шаг 2д process_incidents — ЕДИНСТВЕННАЯ точка отправки закрывающих заявок; прямой вызов close_position из цикла удалён); STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md — полная новая редакция (§2 факт-последовательность, §3 единый маршрут и запрещённые схемы, §4 единый контракт Stop Loss, §6 FSM, §7 этапы A–E, §8 идемпотентность, §9 интеграция); FILE_CHANGE_MAP: M-7 переопределён; ROADMAP: этап H перепроектирован; TEST_MATRIX: §8 → EE-01…EE-20 |
| 2 | Модель риска: утверждение «фактическое входное проскальзывание уже содержится в \|exec_price - sl\|» неверно при SL, рассчитанном от exec_price; смешение «расстояние до стопа» и «входное проскальзывание» | §7.4 исправлен: обоснование исключения SLIPPAGE_PERCENT заменено (пп. 3, абзац после open-формулы), база оценочной комиссии выхода — sl_price (сценарная цена), добавлены поля decision_price/exec_price/sl_price/entry_slippage_ps и краевой случай отсутствующих цен; НОВЫЙ документ STAGE2_RISK_MODEL_FORMULAS.md: четыре ценовые величины, семь независимых составляющих, три модели с единицами/источниками/временем, матрица недопущения двойного учёта DC-0…DC-6, согласование sizing ↔ risk reporting (D-28), числовой пример с декомпозициями; TEST_MATRIX: T-15 переписан, §9 RM-01…RM-14; OPEN_DECISIONS: D-25, D-28 |
| 3 | Согласованность всех затронутых документов (одинаковые состояния/события/правила, корректные перекрёстные ссылки, устаревшие утверждения ред. 2.3 устранены) | BluePrint §6.2/§7.4/§15(примечание)/§16/§17; TEST_MATRIX (T-14, T-15, §8, §9); OPEN_DECISIONS (F-29…F-33, P-12/P-15 ред. 2.3.1, D-18 расширена, D-24…D-28, §5); TRACEABILITY (§2.10); FILE_CHANGE_MAP (M-7, §3.8); ROADMAP (этап H); STAGE2_3_CHANGELOG.md (приложение II); перечень правок — STAGE2_3_1_CHANGELOG.md |

---

## 18. Сводка правок Stage 2.3.2 (финальные корректировки согласованности по аудиту Stage 2.3.1)

Узкая корректировка: согласованные решения Stage 2.3.1 НЕ переписываются;
исправлены ТОЛЬКО три противоречия (STAGE2_3_2_CHANGELOG.md — полный
перечень; STAGE2_3_2_AUDIT_CLOSURE_TABLE.md — доказательства закрытия).

| # | Противоречие ред. 2.3.1 (аудит Stage 2.3.1) | Где исправлено в этом документе |
|---|---|---|
| 1 | ЕДИНСТВЕННАЯ точка отправки закрывающих SELL противоречила формулировке «close_position может использоваться для операторских закрытий вне инцидентов» (два маршрута отправки) | §6.2 (комментарий шага 2д + блок «Что сохраняется без изменений»): сценарии A/B/C, инвариант ALL_BOT_SELL_SUBMISSIONS ⊆ process_incidents(); close_position — исполнитель рыночной ноги внутри контроллера, НЕ маршрут; В3 — обнаружение без заявок (FACT main.py:1932-2011); сценарий C — только создание инцидента. Полный проект — STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md §3 (запреты №6-10), §3а |
| 2 | D-24/D-27 объявлены обязательными ДО этапа H, но снабжены умолчанием «без решения действует вариант (а) как умолчание проекта» | §6.2 (шаг 2д), §16 (параметры политики): умолчание удалено; UNCONFIGURED + блокировка этапа H + явная диагностика старта (STAGE2_OPEN_DECISIONS.md §3а; тесты CD-01…CD-06). Сопутствующе устранён тот же дефект D-26 |
| 3 | `stop_exec_price` использовался как универсальная фактическая цена закрытия для TP/BE/TRAIL/стратегических выходов | §7.4 (поля журнала после выхода): `exit_exec_price` — единая фактическая цена исполнения для ВСЕХ типов выхода; `exit_decision_price`; `exit_slippage_ps` для всех выходов; `stop_execution_slippage_ps = max(0, sl_price - exit_exec_price)` — только стоповые инциденты, иначе NOT_APPLICABLE; частичные исполнения — правила §5.5 RMF. Полная постановка — STAGE2_RISK_MODEL_FORMULAS.md §3/§5.2/§5.5 |

---

## 19. Сводка правок Stage 2.3.3 (модель ценовых снимков и много-попытковое проскальзывание)

Документационное дополнение Stage 2.3.3 (ТЗ «EXIT PRICE SNAPSHOTS &
MULTI-ATTEMPT SLIPPAGE ACCOUNTING»): согласованные решения
2.3.1/2.3.2 НЕ переписываются; маршрут отправки, FSM, политики и
ограничения НЕ изменяются. Добавлено (STAGE2_3_3_CHANGELOG.md — полный
перечень; STAGE2_3_3_AUDIT_CLOSURE_TABLE.md — доказательства закрытия):

| # | Добавление ред. 2.3.3 | Где |
|---|---|---|
| 1 | Три уровня ценовых данных: `exit_decision_price` (записывается один раз, неизменяема) / `exit_attempt_snapshot` (перед каждой попыткой, неизменяемые записи) / фактические исполнения (отдельно от снимков, только подтверждения брокера, append-only) | STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md §7а; порядок работы с ценовыми данными (14 шагов) — §7а.4; fail-closed при невозможности получить цену — §7а.5 |
| 2 | Разделение проскальзывания: `total_exit_slippage_ps` (относительно первоначального решения; >0 — неблагоприятное, <0 — лучше решения) / `attempt_slippage_ps` (по попытке; без исполнений — NOT_APPLICABLE); `exit_slippage_ps` (ред. 2.3.2) ВЫВЕДЕН ИЗ УПОТРЕБЛЕНИЯ; `stop_execution_slippage_ps` — без изменений | STAGE2_RISK_MODEL_FORMULAS.md §3, §5.6; настоящий документ §7.4 |
| 3 | Запрет двойного учёта: DC-8 (не суммировать total/attempt/stop-поля между собой; не добавлять к realized_loss; общая и пер-попытковая статистика без двойного учёта) | STAGE2_RISK_MODEL_FORMULAS.md §6; §8 (контроль шага 8) |
| 4 | Восстановление ценовых данных после перезапуска (R-10): цена решения, ВСЕ снимки, связи incident_id → attempt_id → order_request_id, ВСЕ исполнения; запрет повторного создания отправленной попытки; запрет использования старого снимка; неизвестная связь — БЕЗ произвольной атрибуции (attempt_id=UNKNOWN, fail-closed) | STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md §6.5, §8 (I-13…I-16) |
| 5 | Тест-кейсы ES-01…ES-14 (входные условия / ожидаемое событие / ожидаемое состояние / PASS-FAIL; проектные — не запускались) | STAGE2_TEST_MATRIX.md §11; FILE_CHANGE_MAP §3.7; ROADMAP этап H |
| 6 | События `EXIT_DECISION_PRICE_RECORDED` / `EXIT_ATTEMPT_SNAPSHOT_RECORDED` / `EXIT_ATTEMPT_SNAPSHOT_UNAVAILABLE`; поля attempt_id/attempt_number в LIMIT_SENT/MARKET_SENT; новые поля в CONFIRMED | STAGE2_EMERGENCY_EXIT_ARCHITECTURE.md §10 |
| 7 | Персистенция: раздел `emergency_incidents` — exit_decision_price, attempts[] (снимки), executions[] (append-only) | FILE_CHANGE_MAP M-5; аварийный выход этапа H |

```
STAGE 2.3.3 — EXIT PRICE SNAPSHOTS & MULTI-ATTEMPT SLIPPAGE ACCOUNTING
DESIGN CORRECTIONS ONLY
SOURCE CODE: UNCHANGED
TRADING: NOT EXECUTED
T-INVEST API: NOT ACCESSED
GITHUB: READ-ONLY
NO LIVE ORDERS
STRATEGY LOGIC: UNCHANGED
RESEARCH ONLY
NO THRESHOLD IS OPTIMIZED
NO FILTER IS INSTALLED
EMERGENCY EXIT ARCHITECTURE — DESIGN ONLY
NO BROKER EXECUTION
NO PYTHON CODE CHANGES
```
