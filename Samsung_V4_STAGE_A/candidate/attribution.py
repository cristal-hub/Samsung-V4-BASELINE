# attribution.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.
# Атрибуция торговых объектов к стратегии и её конфигурации.
#
# НАЗНАЧЕНИЕ
#   Каждый НОВЫЙ объект, создаваемый движком (события, новые записи
#   ордеров, новые позиции, новые строки торгового CSV, записи
#   исследовательских журналов), должен нести:
#       strategy_id, config_hash
#   чтобы однозначно установить источник объекта.
#
# ОБРАТНАЯ СОВМЕСТИМОСТЬ (обязательство Этапа A):
#   * существующие исторические записи могут не иметь этих полей;
#   * старые записи НЕ переписываются, миграции НЕТ, исторические CSV
#     не меняются задним числом, выдуманные значения не подставляются;
#   * для старых объектов отсутствие полей обрабатывается явно и
#     безопасно (legacy_attribution_view: None/False, никакой фальши);
#   * для НОВЫХ объектов отсутствие атрибуции выявляется тестами и
#     НЕ маскируется фиктивными значениями (fail-closed).
#
# ГРАНИЦЫ ЭТАПА A (честно задокументировано в IMPLEMENTATION_REPORT.md):
#   * этот модуль — инфраструктура атрибуции нового движка; в производственный
#     поток main.py/execution.py/logger.py он Этапом A НЕ встраивается:
#     встраивание потребовало бы изменения схемы research_trades.csv
#     (авто-ротация шапки у пользователя) и правок механизма исполнения —
#     это зафиксировано как блокер с минимальным решением для Этапа B;
#   * production-файлы baseline (logger.py и др.) НЕ изменены.
#
# STRATEGY LOGIC: UNCHANGED. RESEARCH ONLY. NO LIVE ORDERS.

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping, Optional, Sequence


ATTRIBUTION_FIELDS = ("strategy_id", "config_hash")

# Предложение для Этапа B: добавить эти два поля В КОНЕЦ TRADE_FIELDS
# logger.py (существующий механизм авто-миграции шапки сохранит старый
# журнал как research_trades_<timestamp>.bak.csv). Этап A это изменение
# сознательно НЕ выполняет — см. шапку модуля и отчёт.
TRADE_ATTRIBUTION_FIELDS = ATTRIBUTION_FIELDS


class AttributionError(Exception):
    """Базовая ошибка атрибуции."""


class AttributionRequiredError(AttributionError):
    """Новый объект не может быть создан без атрибуции (fail-closed)."""


@dataclass(frozen=True)
class AttributionContext:
    """Пара (strategy_id, config_hash) активной конфигурации движка."""
    strategy_id: str
    config_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_id, str) or not self.strategy_id:
            raise AttributionError(
                "strategy_id атрибуции должен быть непустой строкой")
        if not isinstance(self.config_hash, str) or not self.config_hash:
            raise AttributionError(
                "config_hash атрибуции должен быть непустой строкой")

    def as_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "config_hash": self.config_hash,
        }


# ---------------------------------------------------------------------------
# Текущий контекст атрибуции движка (явно управляемый, без «тихих» умолчаний)
# ---------------------------------------------------------------------------

_current_context: Optional[AttributionContext] = None


def set_current_context(context: AttributionContext) -> None:
    """Явно установить текущий контекст атрибуции (после CONFIGURED)."""
    global _current_context
    if not isinstance(context, AttributionContext):
        raise AttributionError("ожидается AttributionContext")
    _current_context = context


def clear_current_context() -> None:
    """Явно снять текущий контекст атрибуции (UNCONFIGURED/CONFIG_ERROR)."""
    global _current_context
    _current_context = None


def get_current_context() -> Optional[AttributionContext]:
    """Текущий контекст или None (объекты без контекста не создаются)."""
    return _current_context


# ---------------------------------------------------------------------------
# Штампование НОВЫХ объектов (fail-closed, без фиктивных значений)
# ---------------------------------------------------------------------------

def stamp(record: Mapping[str, Any],
          context: Optional[AttributionContext] = None,
          *,
          overwrite: bool = False) -> dict:
    """Возвращает КОПИЮ record с добавленными strategy_id и config_hash.

    Правила:
      * контекст не передан и текущий контекст отсутствует ->
        AttributionRequiredError (никаких фиктивных значений);
      * если в record уже есть поля атрибуции с ДРУГИМИ значениями —
        ошибка (перезапись только при overwrite=True);
      * входной record не мутируется.
    """
    ctx = context if context is not None else get_current_context()
    if ctx is None:
        raise AttributionRequiredError(
            "новый объект требует атрибуции (strategy_id, config_hash): "
            "контекст не задан; фиктивные значения запрещены")
    result = dict(record)
    for name in ATTRIBUTION_FIELDS:
        ctx_value = getattr(ctx, name)
        if name in result and result[name] != ctx_value and not overwrite:
            raise AttributionError(
                f"поле {name} уже присутствует с другим значением; "
                "перезапись запрещена (overwrite=True для явного случая)")
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
    значений. Результат предназначен для чтения/анализа в памяти;
    исторические файлы этот модуль никогда не перезаписывает.
    """
    view: dict = {"has_attribution": record_has_attribution(record)}
    for name in ATTRIBUTION_FIELDS:
        value = record.get(name)
        view[name] = value if isinstance(value, str) and value else None
    return view


# ---------------------------------------------------------------------------
# Новые CSV-журналы движка (только для НОВЫХ записей; старые файлы не трогаем)
# ---------------------------------------------------------------------------

def append_attributed_csv_row(path: str,
                              row: Mapping[str, Any],
                              base_fieldnames: Sequence[str],
                              *,
                              delimiter: str = ";",
                              context: Optional[AttributionContext] = None
                              ) -> dict:
    """Дописывает в НОВЫЙ CSV-журнал движка строку с атрибуцией.

    Поля атрибуции добавляются В КОНЕЦ шапки (совместимо с существующими
    DictReader-читателями: старые читатели получают дополнительные ключи,
    базовые столбцы читаются как прежде). Отсутствие контекста — ошибка
    (fail-closed). Для исторических research_trades.csv функция НЕ
    применяется (production logger.py не изменён).
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


def read_csv_attribution_report(path: str,
                                *,
                                delimiter: str = ";"
                                ) -> List[dict]:
    """Читает CSV и возвращает для каждой строки legacy_attribution_view.

    Инструмент проверок обратной совместимости: старые записи без
    атрибуции читаются безопасно, с явными None; файл не изменяется.
    """
    views: List[dict] = []
    with open(path, "r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=delimiter):
            views.append(legacy_attribution_view(row))
    return views
