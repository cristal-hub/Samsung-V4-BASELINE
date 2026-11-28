# historical_engine/engine.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
#
# BacktestEngine: фасад детерминированного исторического симулятора.
# Компонует HistoricalDataFeed / EventEngine / StrategyRunner /
# HistoricalExecutionSimulator / RiskIntegration (Stage D) /
# PortfolioLedger / BacktestReport.
#
# Stage E.1 (Correction 3): при создании BacktestEngine выполняется ЯВНАЯ
# проверка совместимости конфигураций HistoricalDataFeed и BacktestEngine
# (все параметры, влияющие на интерпретацию исторических данных:
# expected_candle_interval_seconds, gap_policy, конфигурация календаря
# с часовым поясом). При несовместимости — fail-closed с диагностикой,
# перечисляющей КАЖДЫЙ различающийся параметр и ОБА значения; неявный
# выбор одной конфигурации вместо другой исключён.
#
# IS / VALIDATION / OOS (ТЗ Stage E §8): движок поддерживает РАЗДЕЛЬНЫЕ
# прогоны по SegmentSpec. КАЖДЫЙ сегмент — независимый прогон с нулевой
# позиции и начальным кэшем EngineConfig (позиции не переносятся через
# границу сегмента). Оптимизация параметров ОТСУТСТВУЕТ: движок не
# возвращает и не принимает «улучшенные» параметры; результаты OOS не
# могут автоматически менять параметры (архитектурно: отчёты — данные
# только для чтения; входные параметры прогона задаются ДО запуска).

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from strategy_api import Strategy, StrategyConfig

from .data_feed import HistoricalDataFeed
from .event_engine import EventEngine
from .execution import HistoricalExecutionSimulator
from .ledger import PortfolioLedger
from .models import (
    EngineConfig,
    EngineConfigError,
    SegmentSpec,
)
from .report import BacktestReportBuilder
from .risk_integration import RiskIntegration
from .strategy_runner import StrategyRunner


def validate_feed_engine_config_consistency(
        feed_config: EngineConfig,
        engine_config: EngineConfig) -> None:
    """Явная проверка совместимости конфигураций фида и движка (E.1).

    Сравниваются ТОЛЬКО параметры, влияющие на интерпретацию
    исторических данных (ТЗ Correction 3 §5.2):
      * expected_candle_interval_seconds;
      * gap_policy;
      * конфигурация календаря (наличие и SHA-256 конфигурации,
        включающий представление часового пояса).

    Часовой пояс: в текущей архитектуре EngineConfig НЕ содержит
    отдельной настройки часового пояса (метки свечей несут собственный
    tz); единственный элемент конфигурации, несущий часовой пояс, —
    торговый календарь, отпечаток которого включает представление пояса
    (календари с одинаковыми моментами, но разными поясами — НЕсовместимы).
    Несвязанные параметры (капитал, комиссии, риск-лимиты...) сознательно
    не сравниваются (ТЗ: «не сравнивать несвязанные параметры без
    технической необходимости»).

    При несовместимости — EngineConfigError с перечнем ВСЕХ различий и
    ОБЕИХ значений (fail-closed, без неявного выбора конфигурации).
    """
    differences: List[str] = []
    feed_interval = feed_config.expected_candle_interval_seconds
    engine_interval = engine_config.expected_candle_interval_seconds
    if feed_interval != engine_interval:
        differences.append(
            "expected_candle_interval_seconds: feed="
            f"{feed_interval!r} != engine={engine_interval!r}")
    if feed_config.gap_policy != engine_config.gap_policy:
        differences.append(
            "gap_policy: feed="
            f"{feed_config.gap_policy!r} != "
            f"engine={engine_config.gap_policy!r}")
    feed_calendar = feed_config.calendar
    engine_calendar = engine_config.calendar
    if (feed_calendar is None) != (engine_calendar is None):
        differences.append(
            "calendar: feed="
            f"{'ABSENT' if feed_calendar is None else 'PRESENT'} != "
            "engine="
            f"{'ABSENT' if engine_calendar is None else 'PRESENT'}")
    elif feed_calendar is not None and engine_calendar is not None:
        feed_sha = feed_calendar.calendar_sha256()
        engine_sha = engine_calendar.calendar_sha256()
        if feed_sha != engine_sha:
            differences.append(
                "calendar configuration (sha256, включая часовой пояс): "
                f"feed={feed_sha} != engine={engine_sha}")
    if differences:
        raise EngineConfigError(
            "конфигурации HistoricalDataFeed и BacktestEngine несовместимы "
            "(fail-closed, Correction 3): параметры интерпретации данных "
            "различаются: " + "; ".join(differences) +
            ". Несовместимые конфигурации создают риск неправильной "
            "интерпретации исторических данных; явного выбора одной "
            "конфигурации вместо другой нет — приведите конфигурации "
            "к одному виду.")


class BacktestEngine:
    """Детерминированный исторический симулятор (research only)."""

    def __init__(self, *,
                 strategy: Strategy,
                 strategy_config: StrategyConfig,
                 engine_config: EngineConfig,
                 feed: HistoricalDataFeed) -> None:
        if not isinstance(strategy, Strategy):
            raise EngineConfigError(
                "BacktestEngine требует стратегию контракта Stage A")
        if type(strategy_config) is not StrategyConfig:
            raise EngineConfigError(
                "BacktestEngine требует точный тип StrategyConfig")
        if type(engine_config) is not EngineConfig:
            raise EngineConfigError(
                "BacktestEngine требует точный тип EngineConfig")
        if type(feed) is not HistoricalDataFeed:
            raise EngineConfigError(
                "BacktestEngine требует точный тип HistoricalDataFeed")
        if strategy_config.strategy_id != strategy.strategy_id:
            raise EngineConfigError(
                "конфигурация принадлежит другой стратегии: "
                f"{strategy_config.strategy_id!r} != "
                f"{strategy.strategy_id!r}")
        # Stage E.1 (Correction 3): ЯВНАЯ проверка совместимости
        # конфигураций интерпретации данных фида и движка (fail-closed).
        validate_feed_engine_config_consistency(
            feed.engine_config, engine_config)
        self._strategy = strategy
        self._strategy_config = strategy_config
        self._cfg = engine_config
        self._feed = feed

    # --- компонование независимого прогона --------------------------------------

    def _build_components(self) -> Tuple[
            PortfolioLedger, HistoricalExecutionSimulator,
            StrategyRunner, EventEngine]:
        """Свежие компоненты для НЕЗАВИСИМОГО прогона (изоляция сегментов:
        ни состояние портфеля, ни состояние стратегии не переносятся)."""
        ledger = PortfolioLedger(initial_cash=self._cfg.initial_cash,
                                 figi=self._cfg.figi)
        risk = RiskIntegration(engine_config=self._cfg,
                               strategy_config=self._strategy_config)

        def levels_provider():
            position = ledger.position
            if position is None:
                return None
            return {"stop_price": position.stop_price,
                    "take_price": position.take_price}

        runner = StrategyRunner(
            strategy=self._strategy,
            strategy_config=self._strategy_config,
            feed=self._feed,
            engine_config=self._cfg,
            levels_provider=levels_provider,
        )
        simulator = HistoricalExecutionSimulator(
            engine_config=self._cfg, ledger=ledger, risk_integration=risk)
        event_engine = EventEngine(
            strategy=self._strategy,
            strategy_config=self._strategy_config,
            feed=self._feed,
            engine_config=self._cfg,
            ledger=ledger,
            simulator=simulator,
            runner=runner,
        )
        return ledger, simulator, runner, event_engine

    # --- прогоны -------------------------------------------------------------------

    def run_segment(self, segment: SegmentSpec) -> Dict[str, Any]:
        """Независимый прогон одного сегмента [start_index, end_index)."""
        if type(segment) is not SegmentSpec:
            raise EngineConfigError(
                "run_segment требует точный тип SegmentSpec")
        if segment.end_index > self._feed.length:
            raise EngineConfigError(
                f"граница сегмента {segment.end_index} вне данных "
                f"(длина {self._feed.length})")
        ledger, _simulator, _runner, event_engine = self._build_components()
        run_summary = event_engine.run(
            start_index=segment.start_index, end_index=segment.end_index)
        builder = BacktestReportBuilder(
            segment_label=segment.label,
            start_index=segment.start_index,
            end_index=segment.end_index,
            feed=self._feed,
            engine_config=self._cfg,
            strategy_config=self._strategy_config,
            ledger=ledger,
            events=event_engine.events,
            run_summary=run_summary,
        )
        return builder.build()

    def run_full(self) -> Dict[str, Any]:
        """Прогон всей серии как одного сегмента с меткой FULL."""
        return self.run_segment(
            SegmentSpec(label="FULL", start_index=0,
                        end_index=self._feed.length))

    def run_segments(self, segments: List[SegmentSpec]) -> Dict[str, Any]:
        """Независимые прогоны списка сегментов (IS/VALIDATION/OOS).

        Требования: сегменты внутри границ данных; перекрытия допускаются
        (каждый сегмент — независимый прогон), но для классической схемы
        IS/VALIDATION/OOS они не нужны. Возвращается бандл с отчётами и
        общим идентификатором; НИКАКИХ параметров из отчётов не
        извлекается и не подстраивается (ТЗ §8: запрет использования
        OOS-результатов для изменения параметров).
        """
        reports: List[Dict[str, Any]] = []
        for segment in segments:
            if type(segment) is not SegmentSpec:
                raise EngineConfigError(
                    "run_segments принимает только точный тип SegmentSpec")
            if segment.end_index > self._feed.length:
                raise EngineConfigError(
                    f"граница сегмента {segment.end_index} вне данных "
                    f"(длина {self._feed.length})")
            reports.append(self.run_segment(segment))
        bundle_id_source = {
            "engine_config_sha256": self._cfg.config_sha256(),
            "strategy_config_hash": self._strategy_config.config_hash,
            "data_sha256": self._feed.data_sha256,
            "segments": [
                {"label": s.label, "start_index": s.start_index,
                 "end_index": s.end_index} for s in segments],
        }
        from .models import canonical_json, sha256_hex
        return {
            "bundle_schema": "samsung_v4_stage_e_bundle_v1",
            "bundle_id": sha256_hex(canonical_json(bundle_id_source)),
            "reports": reports,
            "note": "Параметры стратегий НЕ оптимизируются движком; "
                    "отчёты IS/VALIDATION/OOS — данные только для чтения.",
        }

    # --- вспомогательное ---------------------------------------------------------------

    @property
    def strategy_config(self) -> StrategyConfig:
        return self._strategy_config

    @property
    def engine_config(self) -> EngineConfig:
        return self._cfg
