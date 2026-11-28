# attribution.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A (+ STAGE A.1 CORRECTIONS).
# Атрибуция торговых объектов к стратегии и её конфигурации.
#
# НАЗНАЧЕНИЕ
#   Каждый НОВЫЙ объект, создаваемый НОВЫМ движком (события, новые
#   виртуальные ордера, новые виртуальные позиции, новые строки
#   исследовательского CSV/JSONL), должен нести:
#       strategy_id, config_hash
#   чтобы однозначно установить источник объекта.
#
# ЕДИНЫЙ ЯВНЫЙ МЕХАНИЗМ ПЕРЕДАЧИ КОНТЕКСТА (Stage A.1, замечания №2 и №3)
#   Единственный источник атрибуции — ЯВНО переданный неизменяемый
#   AttributionContext (или StrategyConfig, из которого контекст выводится
#   методом AttributionContext.from_config). Глобального изменяемого
#   состояния НЕ СУЩЕСТВУЕТ: set_current_context / get_current_context /
#   clear_current_context и модульная переменная _current_context УДАЛЕНЫ
#   как обязательный источник атрибуции (замечание №3 аудита Stage A.1).
#   Причина: глобальное состояние при параллельной работе или переключении
#   стратегий может присвоить объекту контекст другой стратегии.
#
#   Правила создания НОВЫХ атрибутированных объектов (fail-closed):
#     * контекст не передан          -> AttributionRequiredError
#      (или TypeError при отсутствующем аргументе — ошибки равнозначны);
#     * фиктивные значения (UNKNOWN, пустые строки, случайные заглушки)
#       НЕ используются никогда;
#     * конфликт переданных полей атрибуции с контекстом -> объект НЕ
#       создаётся (AttributionError), состояние фабрики не искажается;
#     * входные записи не мутируются (возвращаются копии).
#
# ОБРАТНАЯ СОВМЕСТИМОСТЬ (обязательство Этапа A):
#   * существующие исторические записи могут не иметь этих полей;
#   * старые записи НЕ переписываются, миграции НЕТ, исторические CSV/JSONL
#     не меняются задним числом, выдуманные значения не подставляются;
#   * для старых объектов отсутствие полей обрабатывается явно и безопасно
#     (legacy_attribution_view / read_*_attribution_report: None/False);
#   * чтение старого объекта НИКОГДА не добавляет ему атрибуцию.
#
# ГРАНИЦА ЭТАПА A.1 (честно задокументировано, замечание №2 аудита):
#   ЭТОТ МОДУЛЬ — САМОСТОЯТЕЛЬНЫЙ ИНТЕРФЕЙС АТРИБУЦИИ НОВОГО ДВИЖКА.
#   Что РЕАЛИЗОВАНО и протестировано на Stage A/A.1:
#     * AttributionContext — неизменяемая пара (strategy_id, config_hash);
#     * AttributionFactory — фабрика атрибутированных объектов, привязанная
#       к одному контексту (явное внедрение зависимости; новые события —
#       new_event, новые виртуальные ордера — new_virtual_order, новые
#       виртуальные позиции — new_virtual_position, новые строки
#       исследовательского CSV/JSONL — append_csv_row/append_jsonl_row);
#     * stamp() — штампование произвольной записи с ЯВНЫМ контекстом;
#     * append_attributed_csv_row / append_attributed_jsonl_row — журналы
#       ТОЛЬКО новых записей движка;
#     * чтение старых записей без атрибуции (CSV и JSONL) — без миграции.
#   Чего Stage A/A.1 сознательно НЕ делает:
#     * НЕ встраивает атрибуцию в производственный поток baseline
#       (main.py / execution.py / logger.py / order_ledger.py не изменены):
#       встраивание потребовало бы изменения схемы research_trades.csv
#       (авто-ротация шапки у пользователя) и правок механизма исполнения —
#       зафиксировано как блокер с минимальным решением для Этапа B
#       (см. CORRECTIVE_IMPLEMENTATION_REPORT.md, раздел «Граница Этапа A»);
#     * НЕ выдаёт изолированный интерфейс за уже внедрённую производственную
#       атрибуцию: типы новых объектов атрибутируются ЧЕРЕЗ интерфейс
#       нового движка; подключение к будущим компонентам движка предусмотрено
#       архитектурно (AttributionFactory создаётся из EngineConfig.attribution
#       — см. engine_config.require_trading_ready) и выполняется на
#       следующих этапах.
#
# Параллельная работа: фабрики изолированы (у каждой свой неизменяемый
# контекст, никакой общей изменяемости); корректность при одновременной
# работе двух стратегий доказана тестами
# tests/test_stage_a1_attribution_explicit.py (в том числе потоками).
#
# STAGE A.2 (обязательная проверка соответствия config_hash фактической
# конфигурации): AttributionContext.from_config() принимает ТОЛЬКО
# StrategyConfig, у которой config_hash проверенно соответствует
# фактическим параметрам (гарантируется при создании StrategyConfig —
# strategy_api.__post_init__; здесь дополнительно перепроверяется через
# recompute_config_hash, defense-in-depth). Произвольные duck-typed
# объекты с полями strategy_id/config_hash больше НЕ принимаются: они
# не могут доказать соответствие хеша своей конфигурации, и контекст с
# несоответствующим хешем не может быть выпущен (AttributionError,
# fail-closed). Скрытых значений, fallback и автоматического исправления
# атрибуции НЕ введено.
# Тесты: tests/test_stage_a2_config_hash_integrity.py.
#
# STAGE A.2.1 (закрытие трёх оставшихся ограничений независимой проверки):
#
# Дефект №1 — прямое создание AttributionContext. Ранее публичный
# конструктор AttributionContext(strategy_id, config_hash) выпускал
# произвольный контекст БЕЗ проверки соответствия config_hash реальной
# StrategyConfig; _resolve_context принимал его как есть, и фабрика могла
# штамповать им новые объекты — обход проверки Stage A.2. Теперь:
#   * публичный конструктор AttributionContext БОЛЬШЕ НЕ создаёт контекст
#     из произвольной пары строк: единственный обычный путь получения
#     контекста — AttributionContext.from_config(проверенная StrategyConfig)
#     (конструктор требует внутренний приватный билет создания; любая
#     попытка обычного публичного создания — AttributionError, fail-closed);
#   * отсутствие подтверждённой конфигурации — fail-closed ошибка;
#   * никаких фиктивных значений и автоматической замены хеша;
#   * контекст остаётся НЕИЗМЕНЯЕМЫМ (frozen dataclass, операции записи
#     запрещены; dataclasses.replace тоже отклоняется — билет не передан);
#   * ВСЕ пути создания объектов (AttributionFactory, stamp, append_csv_row,
#     append_jsonl_row) используют только подтверждённый контекст:
#     _resolve_context принимает контекст точного типа AttributionContext
#     с маркером проверенного создания либо StrategyConfig (через
#     from_config); самодельный экземпляр, собранный в обход конструктора
#     и не имеющий маркера, отклоняется;
#   * deepcopy/pickle идут через тот же охраняемый конструктор (__reduce__)
#     и сохраняют статус проверенности;
#   * внутренний механизм (приватный билет) НЕ предоставляет обычному
#     потребителю публичного способа передать произвольную пару строк
#     (Python-интроспекция уровня object.__new__ сознательно не является
#     целью абсолютной защиты — по условию задачи).
#
# Дефект №2 — наследование StrategyConfig. Ранее from_config использовал
# isinstance(config, StrategyConfig) и перепроверку через
# config.recompute_config_hash(): подкласс мог переопределить
# recompute_config_hash (и даже __post_init__) и ослабить проверку.
# РЕШЕНИЕ (документируется как принятое):
#   * from_config принимает ТОЛЬКО ТОЧНЫЙ тип StrategyConfig
#     (type(config) is StrategyConfig): наследование НЕ поддерживается,
#     экземпляр любого подкласса отклоняется AttributionError независимо
#     от содержимого — обоснованной необходимости поддерживать наследование
#     нет, а подкласс не может гарантировать неизменность проверок;
#   * соответствие хеша перепроверяется ИСХОДНЫМ алгоритмом
#     strategy_api.compute_config_hash по фактическим
#     strategy_id/strategy_version/params/config_hash конфигурации —
#     переопределяемые методы подкласса НЕ используются как источник
#     проверки (несовпадение любого из четырёх полей -> AttributionError);
#   * формат config_hash перепроверяется validate_config_hash_format.
#
# Дефект №3 — изменяемый Enum.value: закрывается в strategy_api.py
# (рекурсивная _validate_enum_value при создании конфигурации и при прямом
# compute_config_hash); этот модуль выигрывает автоматически, т.к. принимает
# только полностью проверенную StrategyConfig.
#
# Тесты: tests/test_stage_a2_1_context_integrity.py.
#
# STRATEGY LOGIC: UNCHANGED. RESEARCH ONLY. NO LIVE ORDERS.

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, Union

from strategy_api import (
    StrategyConfig,
    StrategyContractError,
    compute_config_hash,
    validate_config_hash_format,
)


ATTRIBUTION_FIELDS = ("strategy_id", "config_hash")

# Предложение для Этапа B: добавить эти два поля В КОНЕЦ TRADE_FIELDS
# logger.py (существующий механизм авто-миграции шапки сохранит старый
# журнал как research_trades_<timestamp>.bak.csv). Этапы A и A.1 это
# изменение сознательно НЕ выполняют — см. шапку модуля и отчёт.
TRADE_ATTRIBUTION_FIELDS = ATTRIBUTION_FIELDS


class AttributionError(Exception):
    """Базовая ошибка атрибуции."""


class AttributionRequiredError(AttributionError):
    """Новый объект не может быть создан без явного контекста (fail-closed)."""


# ---------------------------------------------------------------------------
# Внутренний механизм создания контекста (Stage A.2.1, дефект №1)
# ---------------------------------------------------------------------------

# Приватный билет создания: КЛАСС-свидетель (имя с подчёркиванием,
# недоступен как часть публичного API; тождество проверяется оператором
# is, а не типом — пересоздать его извне НЕЛЬЗЯ). Использование именно
# класса (а не object()) принципиально: deepcopy/pickle восстанавливают
# ТИПЫ по ссылке с сохранением идентичности, поэтому охраняемое
# восстановление контекста (__reduce__) проходит проверку, а любая
# попытка подмены билета произвольным объектом — нет.
#
# Обычный публичный путь передачи произвольной пары строк
# (strategy_id, config_hash) закрыт: без билета конструктор отклоняет
# создание. Python-интроспекция уровня object.__new__/object.__setattr__
# сознательно НЕ является целью абсолютной защиты (по условию Stage
# A.2.1); против сборки «мимо конструктора» дополнительно работает
# маркер проверенного создания (_VERIFIED_MARKER), который
# _resolve_context проверяет у каждого контекста, пришедшего извне
# модуля.
class _ContextCreationTicket:
    """Приватный класс-свидетель создания AttributionContext (A.2.1).

    Экземпляры НЕ создаются и не нужны: билетом служит сам класс.
    """

    __slots__ = ()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(
            "_ContextCreationTicket — внутренний механизм attribution.py; "
            "экземпляры не создаются")


_CONTEXT_CREATION_TICKET = _ContextCreationTicket

# Маркер, выставляемый ТОЛЬКО охраняемым конструктором; проверяется при
# каждом входе контекста извне (stamp/factory/CSV/JSONL).
_VERIFIED_MARKER = "__stage_a2_1_verified_context__"


@dataclass(frozen=True, init=False)
class AttributionContext:
    """Неизменяемая пара (strategy_id, config_hash) активной конфигурации.

    Единственный источник атрибуции нового движка. Передаётся ЯВНО в
    функции создания объектов либо привязывается к AttributionFactory
    (явное внедрение зависимости).

    Создание (Stage A.2.1, дефект №1):
      * публичный конструктор НЕ принимает произвольную пару строк:
        без внутреннего приватного билета создания — AttributionError;
      * единственный обычный путь получения контекста —
        AttributionContext.from_config(проверенная StrategyConfig);
      * контекст создаётся ТОЛЬКО на основании проверенной StrategyConfig,
        чей config_hash проверенно соответствует фактическим параметрам;
      * неизменяемость сохранена: frozen dataclass; setattr/delattr
        отклоняются; dataclasses.replace отклоняется (билет не передан);
        deepcopy/pickle восстанавливаются через тот же охраняемый
        конструктор (__reduce__) и не теряют проверенность.
    """

    strategy_id: str
    config_hash: str

    def __init__(self, strategy_id: Any = None, config_hash: Any = None,
                 _creation_ticket: Any = None) -> None:
        # 1. Билет создания: любое обычное публичное создание с
        #    произвольными strategy_id/config_hash отклоняется.
        if _creation_ticket is not _CONTEXT_CREATION_TICKET:
            raise AttributionError(
                "прямое создание AttributionContext(strategy_id, "
                "config_hash) запрещено (Stage A.2.1): контекст создаётся "
                "ТОЛЬКО на основании проверенной StrategyConfig — "
                "AttributionContext.from_config(config); произвольная пара "
                "строк не может подтвердить соответствие config_hash "
                "реальной конфигурации (fail-closed)")
        # 2. Валидация полей (fail-closed, без умолчаний и заглушек).
        if not isinstance(strategy_id, str) or not strategy_id:
            raise AttributionError(
                "strategy_id атрибуции должен быть непустой строкой")
        if not isinstance(config_hash, str) or not config_hash:
            raise AttributionError(
                "config_hash атрибуции должен быть непустой строкой")
        try:
            validate_config_hash_format(config_hash)
        except StrategyContractError as exc:
            raise AttributionError(
                "config_hash атрибуции не соответствует формату SHA-256 "
                f"hexdigest: {exc}") from exc
        # 3. Запись только через object.__setattr__ (frozen dataclass) +
        #    маркер проверенного создания (не поле dataclass: не участвует
        #    в __eq__/__repr__/as_dict).
        object.__setattr__(self, "strategy_id", strategy_id)
        object.__setattr__(self, "config_hash", config_hash)
        object.__setattr__(self, _VERIFIED_MARKER, True)

    def __reduce__(self):
        # deepcopy/pickle восстанавливаются через ОХРАНЯЕМЫЙ конструктор:
        # копия/восстановление не теряют статус проверенного контекста
        # и не обходят создание.
        return (AttributionContext,
                (self.strategy_id, self.config_hash,
                 _CONTEXT_CREATION_TICKET))

    def as_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "config_hash": self.config_hash,
        }

    @classmethod
    def from_config(cls, config: Any) -> "AttributionContext":
        """ЕДИНЫЙ обычный путь получения контекста (Stage A.2/A.2.1).

        Принимается ТОЛЬКО точный тип StrategyConfig, чей config_hash
        проверенно соответствует фактическим параметрам.

        Stage A.2.1 (дефект №2 — наследование): РЕШЕНИЕ ДОКУМЕНТИРОВАНО.
          * Принимается ТОЛЬКО точный тип StrategyConfig
            (type(config) is StrategyConfig): обоснованной необходимости
            поддерживать наследование нет, а подкласс может переопределить
            recompute_config_hash и даже __post_init__, ослабив проверку;
            экземпляр любого подкласса отклоняется AttributionError
            независимо от содержимого (fail-closed);
          * соответствие хеша перепроверяется ИСХОДНЫМ алгоритмом
            strategy_api.compute_config_hash по фактическим полям
            strategy_id/strategy_version/params/config_hash —
            переопределяемые методы объекта НЕ используются как источник
            проверки; несовпадение любого из четырёх полей -> AttributionError;
          * формат config_hash перепроверяется validate_config_hash_format.

        Произвольные duck-typed объекты с полями strategy_id/config_hash
        НЕ принимаются (AttributionError, fail-closed). None/мусорные
        значения -> AttributionError. Скрытых значений, fallback и
        автоматического исправления атрибуции нет.
        """
        if config is None:
            raise AttributionError(
                "AttributionContext.from_config: конфигурация не передана")
        # Дефект №2: точный тип, а не isinstance — подкласс не может
        # провести свой ослабленный вариант проверки.
        if type(config) is not StrategyConfig:
            raise AttributionError(
                "AttributionContext.from_config: принимается ТОЛЬКО точный "
                "тип StrategyConfig (наследование не поддерживается: "
                "подкласс может переопределить recompute_config_hash и "
                "ослабить проверку config_hash); объект с ручными полями "
                "strategy_id/config_hash не может доказать соответствие "
                "и отвергается (фиктивные значения запрещены; получено "
                f"{type(config).__name__})")
        # Defense-in-depth: формат config_hash (64 hex-символа).
        try:
            validate_config_hash_format(config.config_hash)
        except StrategyContractError as exc:
            raise AttributionError(
                "AttributionContext.from_config: config_hash конфигурации "
                f"не соответствует формату SHA-256 hexdigest: {exc}") from exc
        # Defense-in-depth: перепроверка соответствия хеша ФАКТИЧЕСКИМ
        # параметрам конфигурации ИСХОДНЫМ алгоритмом (не переопределяемым
        # методом объекта): несовпадение любого из strategy_id,
        # strategy_version, params и config_hash -> отказ.
        try:
            expected_hash = compute_config_hash(
                config.strategy_id, config.strategy_version, config.params)
        except StrategyContractError as exc:
            raise AttributionError(
                "AttributionContext.from_config: конфигурация некорректна "
                f"({exc}); контекст не выпускается (fail-closed)") from exc
        if expected_hash != config.config_hash:
            raise AttributionError(
                "AttributionContext.from_config: config_hash конфигурации "
                "не соответствует её фактическим параметрам; контекст с "
                "несоответствующим хешем не выпускается, автоматическое "
                "исправление атрибуции запрещено (fail-closed)")
        # Контекст создаётся ТОЛЬКО здесь: через охраняемый конструктор
        # с внутренним билетом. Обычный публичный путь создания контекста
        # с произвольными строками не существует.
        return cls(strategy_id=config.strategy_id,
                   config_hash=config.config_hash,
                   _creation_ticket=_CONTEXT_CREATION_TICKET)


# ГЛОБАЛЬНОЕ СОСТОЯНИЕ УДАЛЕНО (Stage A.1, замечание №3 аудита).
# Ранее: _current_context + set_current_context()/get_current_context()/
# clear_current_context(). Сейчас единственный источник атрибуции —
# ЯВНО переданный контекст; функции создания объектов не обращаются ни
# к какому глобальному/потоковому состоянию.

def _resolve_context(
        context: Optional[Union[AttributionContext, StrategyConfig]]
) -> AttributionContext:
    """Единая нормализация контекста (fail-closed).

    AttributionContext принимается ТОЛЬКО если он проверенного создания
    (точный тип + маркер, выставляемый охраняемым конструктором):
    контекст, собранный в обход конструктора и не имеющий маркера,
    отклоняется. StrategyConfig (точный тип) преобразуется явно
    (from_config). None/пустые/самодельные значения ->
    AttributionRequiredError/AttributionError (никаких умолчаний,
    никаких фиктивных значений).
    """
    if isinstance(context, AttributionContext):
        # Маркер проверенного создания выставляет ТОЛЬКО охраняемый
        # конструктор; экземпляр, собранный в обход конструктора (например,
        # object.__new__ без восстановления), маркера не имеет и
        # отклоняется.
        if type(context) is AttributionContext and \
                getattr(context, _VERIFIED_MARKER, False) is True:
            return context
        raise AttributionError(
            "контекст атрибуции не подтверждён: AttributionContext без "
            "маркера проверенного создания не принимается; контекст "
            "получается ТОЛЬКО из проверенной StrategyConfig — "
            "AttributionContext.from_config(config) (fail-closed, "
            "Stage A.2.1)")
    if isinstance(context, StrategyConfig):
        return AttributionContext.from_config(context)
    raise AttributionRequiredError(
        "контекст атрибуции не передан: новый объект движка создаётся "
        "ТОЛЬКО с явным подтверждённым AttributionContext (или точным "
        "StrategyConfig); глобальный контекст удалён, фиктивные значения "
        "запрещены")


# ---------------------------------------------------------------------------
# Штампование НОВЫХ объектов (fail-closed, без фиктивных значений)
# ---------------------------------------------------------------------------

def stamp(record: Mapping[str, Any],
          context: Union[AttributionContext, StrategyConfig],
          *,
          overwrite: bool = False) -> dict:
    """Возвращает КОПИЮ record с добавленными strategy_id и config_hash.

    Правила (Stage A.1):
      * контекст ОБЯЗАТЕЛЕН и передаётся ЯВНО (AttributionContext или
        StrategyConfig): его отсутствие -> AttributionRequiredError;
        глобального источника атрибуции больше не существует;
      * если в record уже есть поля атрибуции с ДРУГИМИ значениями —
        объект не создаётся (AttributionError); перезапись только при
        явном overwrite=True;
      * входной record не мутируется.
    """
    if not isinstance(record, Mapping):
        raise AttributionError(
            f"record должен быть отображением (Mapping), получено "
            f"{type(record).__name__}")
    ctx = _resolve_context(context)
    result = dict(record)
    for name in ATTRIBUTION_FIELDS:
        ctx_value = getattr(ctx, name)
        if name in result and result[name] != ctx_value and not overwrite:
            raise AttributionError(
                f"поле {name} уже присутствует с другим значением; "
                "объект не создаётся; перезапись запрещена "
                "(overwrite=True для явного случая)")
        result[name] = ctx_value
    return result


def record_has_attribution(record: Mapping[str, Any]) -> bool:
    """True, если в записи присутствуют ОБА непустых поля атрибуции."""
    for name in ATTRIBUTION_FIELDS:
        value = record.get(name)
        if not isinstance(value, str) or not value:
            return False
    return True


def legacy_attribution_view(record: Mapping[str, Any]) -> dict:
    """Явное, безопасное представление атрибуции СТАРОЙ записи.

    Для исторических записей без полей атрибуции возвращает
    has_attribution=False и None — НЕ подставляя никаких выдуманных
    значений и НЕ добавляя атрибуцию к записи. Результат предназначен
    для чтения/анализа в памяти; исторические файлы этот модуль никогда
    не перезаписывает.
    """
    view: dict = {"has_attribution": record_has_attribution(record)}
    for name in ATTRIBUTION_FIELDS:
        value = record.get(name)
        view[name] = value if isinstance(value, str) and value else None
    return view


# ---------------------------------------------------------------------------
# Фабрика атрибутированных объектов нового движка (Stage A.1)
# ---------------------------------------------------------------------------

class AttributionFactory:
    """Фабрика атрибутированных объектов, привязанная к ОДНОМУ контексту.

    Архитектурная точка подключения для компонентов нового движка
    (Этап B+): компонент получает экземпляр фабрики из своей конфигурации
    (EngineConfig.attribution -> AttributionContext -> AttributionFactory)
    и создаёт через неё ВСЕ новые объекты:

      * new_event            — новый объект события (журнал JSONL);
      * new_virtual_order    — новый виртуальный ордер;
      * new_virtual_position — новая виртуальная позиция;
      * append_csv_row       — новая строка исследовательского CSV;
      * append_jsonl_row     — новая строка исследовательского JSONL;
      * stamp                — произвольная новая запись.

    Свойства:
      * ЯВНОЕ внедрение зависимости: контекст задаётся при создании
        фабрики (AttributionContext или StrategyConfig) и неизменяем;
      * НЕТ глобального состояния: фабрики независимы, две стратегии с
        разными контекстами не влияют друг на друга (в том числе при
        параллельной работе — доказано тестами);
      * исключение при создании объекта не оставляет «устаревшего»
        контекста: контекст фабрики неизменяем по построению;
      * конфликт атрибуции -> объект не создаётся (AttributionError).
    """

    __slots__ = ("_context",)

    def __init__(
        self, context: Union[AttributionContext, StrategyConfig]
    ) -> None:
        object.__setattr__(self, "_context", _resolve_context(context))

    @property
    def context(self) -> AttributionContext:
        """Неизменяемый контекст фабрики (один на всю жизнь фабрики)."""
        return self._context

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError(
            "AttributionFactory неизменяем: контекст не может быть заменён")

    def stamp(self, record: Mapping[str, Any],
              *, overwrite: bool = False) -> dict:
        """Новая атрибутированная запись (копия record + атрибуция)."""
        return stamp(record, self._context, overwrite=overwrite)

    def new_event(self, event: Mapping[str, Any]) -> dict:
        """НОВЫЙ объект события движка (strategy_id + config_hash)."""
        return self._new_attributed(event, "event")

    def new_virtual_order(self, order: Mapping[str, Any]) -> dict:
        """НОВЫЙ виртуальный ордер движка (strategy_id + config_hash)."""
        return self._new_attributed(order, "virtual_order")

    def new_virtual_position(self, position: Mapping[str, Any]) -> dict:
        """НОВАЯ виртуальная позиция движка (strategy_id + config_hash)."""
        return self._new_attributed(position, "virtual_position")

    def append_csv_row(self,
                       path: str,
                       row: Mapping[str, Any],
                       base_fieldnames: Sequence[str],
                       *,
                       delimiter: str = ";") -> dict:
        """Новая строка исследовательского CSV с атрибуцией.

        Для журналов НОВОГО движка; исторические CSV не трогаются.
        """
        return append_attributed_csv_row(
            path, row, base_fieldnames, context=self._context,
            delimiter=delimiter)

    def append_jsonl_row(self, path: str,
                         record: Mapping[str, Any]) -> dict:
        """Новая строка исследовательского JSONL с атрибуцией."""
        return append_attributed_jsonl_row(path, record, context=self._context)

    def _new_attributed(self, record: Mapping[str, Any],
                        kind: str) -> dict:
        if not isinstance(record, Mapping):
            raise AttributionError(
                f"{kind}: запись должна быть отображением (Mapping), "
                f"получено {type(record).__name__}")
        return self.stamp(record)


# ---------------------------------------------------------------------------
# Новые журналы движка (только для НОВЫХ записей; старые файлы не трогаем)
# ---------------------------------------------------------------------------

def append_attributed_csv_row(path: str,
                              row: Mapping[str, Any],
                              base_fieldnames: Sequence[str],
                              *,
                              context: Union[AttributionContext,
                                             StrategyConfig],
                              delimiter: str = ";"
                              ) -> dict:
    """Дописывает в НОВЫЙ CSV-журнал движка строку с атрибуцией.

    Контекст ОБЯЗАТЕЛЕН (явная передача; Stage A.1). Поля атрибуции
    добавляются В КОНЕЦ шапки (совместимо с существующими DictReader-читателями:
    старые читатели получают дополнительные ключи, базовые столбцы читаются
    как прежде). Отсутствие контекста — ошибка (fail-closed). Для
    исторических research_trades.csv функция НЕ применяется (production
    logger.py не изменён).
    """
    stamped = stamp(row, context)
    fieldnames: List[str] = list(base_fieldnames)
    for name in ATTRIBUTION_FIELDS:
        if name not in fieldnames:
            fieldnames.append(name)
    write_row = {name: stamped.get(name, "") for name in fieldnames}
    file_exists = os.path.isfile(path)
    with open(path, "a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, delimiter=delimiter)
        if not file_exists or os.path.getsize(path) == 0:
            writer.writeheader()
        writer.writerow(write_row)
    return write_row


def append_attributed_jsonl_row(path: str,
                                record: Mapping[str, Any],
                                *,
                                context: Union[AttributionContext,
                                               StrategyConfig],
                                encoding: str = "utf-8"
                                ) -> dict:
    """Дописывает в НОВЫЙ JSONL-журнал движка запись с атрибуцией.

    Контекст ОБЯЗАТЕЛЕН (явная передача; Stage A.1). Формат — одна JSON-
    строка на объект (аналог research_events.jsonl baseline, но для НОВЫХ
    журналов движка; старые файлы не трогаются). NaN/Infinity в записи
    отвергаются json-сериализацией (allow_nan=False, fail-closed).
    """
    stamped = stamp(record, context)
    line = json.dumps(stamped, ensure_ascii=False, allow_nan=False)
    with open(path, "a", encoding=encoding, newline="") as handle:
        handle.write(line + "\n")
    return stamped


def read_csv_attribution_report(path: str,
                                *,
                                delimiter: str = ";"
                                ) -> List[dict]:
    """Читает CSV и возвращает для каждой строки legacy_attribution_view.

    Инструмент проверок обратной совместимости: старые записи без
    атрибуции читаются безопасно, с явными None; файл не изменяется;
    атрибуция к записям не добавляется.
    """
    views: List[dict] = []
    with open(path, "r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=delimiter):
            views.append(legacy_attribution_view(row))
    return views


def read_jsonl_attribution_report(path: str,
                                  *,
                                  encoding: str = "utf-8"
                                  ) -> List[dict]:
    """Читает JSONL и возвращает для каждой записи legacy_attribution_view.

    Аналог read_csv_attribution_report для событий (JSONL): старые записи
    без атрибуции читаются безопасно, с явными None; файл не изменяется.
    """
    views: List[dict] = []
    with open(path, "r", encoding=encoding) as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            views.append(legacy_attribution_view(json.loads(stripped)))
    return views
